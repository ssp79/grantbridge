"""Password hashing, login, lockout, and account management."""

import sqlite3

import pytest

from grantbridge import auth
from grantbridge.db import connect
from grantbridge.validation import ValidationError

PASSWORD = "correct horse battery staple"


def test_password_stored_only_as_argon2id_hash(fresh_db):
    auth.sign_up("Alice@Example.org", PASSWORD, "Alice Org")
    with connect() as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored.startswith("$argon2id$")
    # The plaintext appears nowhere in the database file.
    assert PASSWORD.encode() not in fresh_db.read_bytes()
    raw = sqlite3.connect(fresh_db)
    for (table,) in raw.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        for row in raw.execute(f"SELECT * FROM {table}"):
            assert PASSWORD not in " ".join(map(str, row))


def test_same_password_gets_different_salts():
    auth.sign_up("a@example.org", PASSWORD, "A")
    auth.sign_up("b@example.org", PASSWORD, "B")
    with connect() as conn:
        hashes = [r[0] for r in conn.execute("SELECT password_hash FROM users")]
    assert hashes[0] != hashes[1]


def test_login_normalizes_email_and_checks_password():
    created = auth.sign_up("Alice@Example.org", PASSWORD, "Alice Org")
    assert auth.log_in("  alice@example.ORG ", PASSWORD) == created
    with pytest.raises(auth.AuthError, match="Email or password is incorrect"):
        auth.log_in("alice@example.org", "wrong password here")


def test_unknown_email_gets_same_message_as_wrong_password():
    with pytest.raises(auth.AuthError, match="Email or password is incorrect"):
        auth.log_in("nobody@example.org", PASSWORD)


def test_duplicate_email_rejected():
    auth.sign_up("a@example.org", PASSWORD, "A")
    with pytest.raises(auth.AuthError):
        auth.sign_up("A@example.org", PASSWORD, "A again")


@pytest.mark.parametrize("bad", ["short", "a" * 20, "x" * 200])
def test_weak_or_oversized_passwords_rejected(bad):
    with pytest.raises(ValidationError):
        auth.sign_up("a@example.org", bad, "A")


def test_lockout_after_repeated_failures():
    auth.sign_up("a@example.org", PASSWORD, "A")
    for _ in range(auth.MAX_FAILED_LOGINS):
        with pytest.raises(auth.AuthError, match="incorrect"):
            auth.log_in("a@example.org", "definitely wrong 1")
    # Even the right password is refused while locked.
    with pytest.raises(auth.AuthError, match="Too many failed attempts"):
        auth.log_in("a@example.org", PASSWORD)


def test_successful_login_resets_failure_count():
    auth.sign_up("a@example.org", PASSWORD, "A")
    for _ in range(auth.MAX_FAILED_LOGINS - 1):
        with pytest.raises(auth.AuthError):
            auth.log_in("a@example.org", "definitely wrong 1")
    auth.log_in("a@example.org", PASSWORD)
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.log_in("a@example.org", "definitely wrong 1")  # not locked


def test_change_password_requires_current_password():
    user = auth.sign_up("a@example.org", PASSWORD, "A")
    with pytest.raises(auth.AuthError):
        auth.change_password(user.id, "not my password", "brand new passphrase")
    auth.change_password(user.id, PASSWORD, "brand new passphrase")
    assert auth.log_in("a@example.org", "brand new passphrase") == user


def test_delete_account_requires_password_and_removes_everything():
    user = auth.sign_up("a@example.org", PASSWORD, "A")
    with pytest.raises(auth.AuthError):
        auth.delete_account(user.id, "wrong password!!")
    auth.delete_account(user.id, PASSWORD)
    assert auth.get_user(user.id) is None
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0] == 0

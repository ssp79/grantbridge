"""Account creation, login, and password changes.

Passwords are hashed with Argon2id via argon2-cffi (random per-password salt,
library-default cost parameters). Plaintext passwords are never stored or logged.

Course-demo scope, not production authentication: there is no email
verification, no password reset by email, and no HTTPS of its own. Brute force
is slowed by a per-account lockout only (no per-IP rate limiting).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from grantbridge import validation
from grantbridge.db import connect, now_iso

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15

_hasher = PasswordHasher()  # Argon2id by default
# Verified against when the email is unknown, so both paths take similar time.
_DUMMY_HASH = _hasher.hash("grantbridge-timing-equalizer")


class AuthError(Exception):
    """A user-facing authentication failure. Messages never reveal which part was wrong."""


@dataclass(frozen=True)
class User:
    id: int
    email: str
    session_epoch: int = field(default=0, compare=False)  # sessions started under an older epoch are ended


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def sign_up(email: str, password: str, org_name: str) -> User:
    clean_email = validation.email(email)
    clean_password = validation.new_password(password, clean_email)
    clean_org = validation.text(org_name, "Organization name", 200, required=True)

    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (clean_email,)).fetchone():
            raise AuthError("Could not create an account with that email. Try logging in instead.")
        created = now_iso()
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (clean_email, hash_password(clean_password), created),
        )
        user_id = cur.lastrowid
        conn.execute(
            "INSERT INTO organizations (user_id, name, updated_at) VALUES (?, ?, ?)",
            (user_id, clean_org, created),
        )
    return User(id=user_id, email=clean_email)


def log_in(email: str, password: str) -> User:
    generic = AuthError("Email or password is incorrect.")
    try:
        clean_email = validation.email(email)
    except validation.ValidationError:
        raise generic from None
    if not password or len(password) > validation.PASSWORD_MAX:
        raise generic

    with connect() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, failed_logins, locked_until, session_epoch FROM users WHERE email = ?",
            (clean_email,),
        ).fetchone()

        if row is None:
            _verify(_DUMMY_HASH, password)
            raise generic

        now = datetime.now(timezone.utc)
        if row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > now:
            raise AuthError(
                f"Too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes."
            )

        if not _verify(row["password_hash"], password):
            failures = row["failed_logins"] + 1
            locked_until = None
            if failures >= MAX_FAILED_LOGINS:
                locked_until = (now + timedelta(minutes=LOCKOUT_MINUTES)).isoformat(timespec="seconds")
                failures = 0
            conn.execute(
                "UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                (failures, locked_until, row["id"]),
            )
            # Commit before raising: connect() rolls back on exceptions, which would
            # silently undo the failure count and disable the lockout.
            conn.commit()
            raise generic

        new_hash = row["password_hash"]
        if _hasher.check_needs_rehash(new_hash):
            new_hash = hash_password(password)
        conn.execute(
            "UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = ?, "
            "password_hash = ? WHERE id = ?",
            (now_iso(), new_hash, row["id"]),
        )
        return User(id=row["id"], email=row["email"], session_epoch=row["session_epoch"])


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    with connect() as conn:
        row = conn.execute(
            "SELECT email, password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None or not _verify(row["password_hash"], current_password or ""):
            raise AuthError("Current password is incorrect.")
        clean = validation.new_password(new_password, row["email"])
        # A new password also ends every other session of the account.
        conn.execute(
            "UPDATE users SET password_hash = ?, session_epoch = session_epoch + 1 WHERE id = ?",
            (hash_password(clean), user_id),
        )


def log_out_everywhere(user_id: int) -> None:
    """End every session of this account, on every device, at its next page action."""
    with connect() as conn:
        conn.execute("UPDATE users SET session_epoch = session_epoch + 1 WHERE id = ?", (user_id,))


def get_user(user_id: int) -> User | None:
    with connect() as conn:
        row = conn.execute("SELECT id, email, session_epoch FROM users WHERE id = ?", (user_id,)).fetchone()
    return User(id=row["id"], email=row["email"], session_epoch=row["session_epoch"]) if row else None


def delete_account(user_id: int, current_password: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not _verify(row["password_hash"], current_password or ""):
            raise AuthError("Password is incorrect.")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))  # cascades to all owned rows


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False

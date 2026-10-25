"""Input validation and the demo-account setup command."""

import pytest

from grantbridge import auth, repo, validation as v
from scripts import create_demo_account


@pytest.mark.parametrize(
    "data, message",
    [
        ({"name": ""}, "required"),
        ({"name": "X", "ein": "123"}, "EIN"),
        ({"name": "X", "website": "javascript:alert(1)"}, "Website"),
        ({"name": "X", "state": "ZZ"}, "state"),
        ({"name": "X", "focus_areas": ["Made up"]}, "focus"),
        ({"name": "X", "annual_budget": -5}, "budget"),
        ({"name": "X", "mission": "m" * 1501}, "Mission"),
    ],
)
def test_profile_validation_rejects_bad_input(data, message):
    user = auth.sign_up("a@example.org", "correct horse battery staple", "A")
    with pytest.raises(v.ValidationError, match=message):
        repo.save_organization(user.id, data)


def test_application_status_must_be_known():
    user = auth.sign_up("a@example.org", "correct horse battery staple", "A")
    app_id = repo.create_application(user.id, "Test")
    with pytest.raises(v.ValidationError):
        repo.update_application(user.id, app_id, {"status": "Hacked"})


def test_demo_account_command_creates_account_with_one_time_password(capsys):
    assert create_demo_account.main(["--email", "demo@example.org"]) == 0
    out = capsys.readouterr().out
    password = out.split("Password (shown once, not saved anywhere): ")[1].split()[0]
    user = auth.log_in("demo@example.org", password)
    assert repo.get_organization(user.id)["name"].startswith("Harbor Lantern")
    assert len(repo.list_applications(user.id)) == 1


def test_demo_account_command_refuses_duplicate_without_reset(capsys):
    assert create_demo_account.main(["--email", "demo@example.org"]) == 0
    assert create_demo_account.main(["--email", "demo@example.org"]) == 1
    assert create_demo_account.main(["--email", "demo@example.org", "--reset"]) == 0


def test_two_demo_runs_get_different_passwords(capsys):
    create_demo_account.main(["--email", "one@example.org"])
    create_demo_account.main(["--email", "two@example.org"])
    out = capsys.readouterr().out
    passwords = [line.split(": ")[1] for line in out.splitlines() if line.startswith("Password")]
    assert len(set(passwords)) == 2


def test_profile_version_increases_on_every_save():
    """Pages compare versions (not timestamps) to detect stale results, so two saves in one second still count."""
    user = auth.sign_up("a@example.org", "correct horse battery staple", "A")
    start = repo.get_organization(user.id)["version"]
    repo.save_organization(user.id, {"name": "A"})
    repo.save_organization(user.id, {"name": "A"})
    assert repo.get_organization(user.id)["version"] == start + 2

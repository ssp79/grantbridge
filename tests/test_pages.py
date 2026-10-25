"""Drive the real Streamlit pages headlessly with streamlit.testing.AppTest."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from grantbridge import auth, repo

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
PASSWORD = "correct horse battery staple"


def fresh_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def sign_in_page() -> AppTest:
    """A signed-out visitor who opened the Sign in page (the landing page is About GrantBridge)."""
    at = fresh_app()
    at.switch_page("app_pages/sign_in.py").run()
    return at


def log_in(at: AppTest, email: str, password: str) -> AppTest:
    at.switch_page("app_pages/sign_in.py").run()  # visitors land on About GrantBridge first
    at.text_input[0].input(email)
    at.text_input[1].input(password)
    at.button[0].click().run()
    return at


def page_text(at: AppTest) -> str:
    parts = [e.value for e in (*at.title, *at.markdown, *at.subheader, *at.info, *at.warning, *at.caption)]
    return "\n".join(str(p) for p in parts)


def test_signed_out_visitor_lands_on_the_public_about_page():
    at = fresh_app()
    assert not at.exception
    assert at.title[0].value == "Less time chasing funding. More time changing lives."
    at = sign_in_page()
    assert not at.exception
    assert at.title[0].value == "GrantBridge"
    assert [t.label for t in at.tabs] == ["Log in", "Create account"]


def test_wrong_password_shows_generic_error():
    auth.sign_up("alice@example.org", PASSWORD, "Alice Pantry")
    at = log_in(fresh_app(), "alice@example.org", "not the password")
    assert at.error[0].value == "Email or password is incorrect."
    assert at.title[0].value == "GrantBridge"


def test_log_in_then_every_page_renders_without_error():
    auth.sign_up("alice@example.org", PASSWORD, "Alice Pantry")
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    assert not at.exception
    assert at.title[0].value == "Your funding workspace"  # the landing page after logging in
    for page, title in [
        ("app_pages/find_grants.py", "Find Grants"),
        ("app_pages/saved_grants.py", "Saved Grants"),
        ("app_pages/applications.py", "Applications"),
        ("app_pages/advisor.py", "AI Grant Advisor"),
        ("app_pages/profile.py", "Organization Profile"),
        ("app_pages/settings.py", "Account"),
        ("app_pages/dashboard.py", "Your funding workspace"),
    ]:
        at.switch_page(page).run()
        assert not at.exception, page
        assert at.title[0].value == title
        assert not at.error, page


def test_log_out_returns_to_sign_in():
    auth.sign_up("alice@example.org", PASSWORD, "Alice Pantry")
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    next(b for b in at.sidebar.button if b.label == "Log out").click().run()
    assert at.title[0].value == "GrantBridge"
    assert "logged out" in at.info[0].value


def test_deleted_account_session_is_ended():
    user = auth.sign_up("alice@example.org", PASSWORD, "Alice Pantry")
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    auth.delete_account(user.id, PASSWORD)
    at.run()
    assert at.title[0].value == "GrantBridge"


def test_pages_show_only_the_signed_in_users_data():
    alice = auth.sign_up("alice@example.org", PASSWORD, "Alice Pantry")
    auth.sign_up("bob@example.org", PASSWORD, "Bob Arts")
    alice_app = repo.create_application_from_grant(alice.id, "sample-01")
    at = log_in(fresh_app(), "bob@example.org", PASSWORD)
    # Even if Bob's session somehow asks for Alice's application id, it is not shown.
    at.session_state["open_application_id"] = alice_app
    at.switch_page("app_pages/applications.py").run()
    assert not at.exception
    assert "You have no applications yet" in page_text(at)   # Bob sees the start flow, not Alice's work
    assert "Connecticut After-School Learning Grant" not in page_text(at)


def test_load_demo_data_button_fills_the_profile_form():
    auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page("app_pages/profile.py").run()
    assert "Still missing" in page_text(at)
    next(b for b in at.button if b.label == "Load demo data").click().run()
    assert not at.exception
    assert "Demo data loaded" in at.success[0].value
    assert at.text_input[0].value.startswith("Harbor Lantern Tutoring Collective")
    assert "Still missing" not in page_text(at)
    assert at.selectbox[0].value == "CT"
    assert at.number_input[0].value == 25000  # requested funding


def test_profile_edit_and_save_round_trip():
    auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page("app_pages/profile.py").run()
    area = next(t for t in at.text_area if t.label == "Track record and outcomes")
    area.input("Served 40 students in 2025.")
    next(b for b in at.button if b.label == "Save profile").click().run()
    assert not at.exception
    assert at.success[0].value == "Profile saved."
    area = next(t for t in at.text_area if t.label == "Track record and outcomes")
    assert area.value == "Served 40 students in 2025."


@pytest.mark.parametrize("bad_email", ["not-an-email", ""])
def test_sign_up_validation_message(bad_email):
    at = sign_in_page()
    fields = at.text_input
    fields[2].input("Test Org")
    fields[3].input(bad_email)
    fields[4].input(PASSWORD)
    fields[5].input(PASSWORD)
    at.button[1].click().run()
    assert at.error[0].value == "Enter a valid email address."

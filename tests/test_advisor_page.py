"""AI Advisor page: mock mode, Agent Activity panel, saved history per account."""

import pytest

from grantbridge import auth, demo, repo
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text


@pytest.fixture(autouse=True)
def mock_by_default(monkeypatch):
    """The test machine may have a real key; force mock mode so no test can spend tokens."""
    monkeypatch.setenv("GRANTBRIDGE_ADVISOR_MODE", "mock")


def open_advisor(email="alice@example.org"):
    user = auth.sign_up(email, PASSWORD, "Alice Org")
    demo.load_demo_data(user.id)
    at = log_in(fresh_app(), email, PASSWORD)
    at.switch_page("app_pages/advisor.py").run()
    return user, at


def ask(at, text):
    at.chat_input[0].set_value(text).run()
    return at


def test_empty_advisor_offers_examples(fresh_db):
    _, at = open_advisor()
    assert not at.exception
    assert at.toggle(key="advisor_mock").value is True
    assert "Which sample grants fit us best?" in [b.label for b in at.button]
    assert "Try one of these to start" in page_text(at)
    assert not at.expander  # no Technical details until there is an answer


def test_mock_answer_is_labeled_with_activity_panel(fresh_db):
    _, at = open_advisor()
    ask(at, "Which sample grants fit us best?")
    assert not at.exception
    body = page_text(at)
    assert "Small Nonprofit Capacity Grant" in body
    assert "**From your records**" in body and "**Still to verify**" in body
    assert "Technical details: agent activity, tokens, and cost" in [e.label for e in at.expander]
    activity = at.dataframe[0].value
    assert list(activity["Step"]) == ["receive_message", "mock_planner", "get_organization_profile",
                                      "search_grants", "check_reply"]
    assert "message=[redacted," in activity["Inputs (redacted)"].iloc[0]
    assert set(activity["Status"]) == {"ok"}


def test_example_button_asks_the_question(fresh_db):
    _, at = open_advisor()
    next(b for b in at.button if b.label == "How far along are my applications?").click().run()
    assert "Connecticut After-School Learning Grant" in page_text(at)


def test_history_persists_across_sessions_and_is_private(fresh_db):
    _, at = open_advisor()
    ask(at, "What is missing from my profile?")
    again = log_in(fresh_app(), "alice@example.org", PASSWORD)
    again.switch_page("app_pages/advisor.py").run()
    assert "What is missing from my profile?" in [m.value for m in again.markdown]
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    other = log_in(fresh_app(), "bob@example.org", PASSWORD)
    other.switch_page("app_pages/advisor.py").run()
    assert "What is missing from my profile?" not in [m.value for m in other.markdown]
    assert repo.list_messages(bob.id) == []


def test_clear_conversation(fresh_db):
    user, at = open_advisor()
    ask(at, "hello")
    next(b for b in at.button if b.label == "Clear conversation").click().run()
    assert repo.list_messages(user.id) == []


def test_activity_panel_follows_the_newest_answer(fresh_db):
    """Regression: after a second question, the panel kept the first answer's label in the browser."""
    _, at = open_advisor()
    ask(at, "What is missing from my profile?")
    ask(at, "How far along are my applications?")
    steps = list(at.dataframe[0].value["Step"])
    assert "get_application_state" in steps and "get_organization_profile" not in steps
    assert at.selectbox[0].key == "activity_run_2"
    assert "Mock answers make no AI calls and cost nothing." in page_text(at)

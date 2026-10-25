"""Should We Pursue? page end to end (practice mode): choose, assess, confirm, act, and the entry buttons."""

from datetime import date

import pytest

from grantbridge import auth, demo, pursuit, repo, timeline
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text


@pytest.fixture(autouse=True)
def mock_and_pinned_clock(monkeypatch):
    monkeypatch.setenv("GRANTBRIDGE_ADVISOR_MODE", "mock")  # no test may spend tokens
    monkeypatch.setattr(timeline, "current_date", lambda: date(2026, 10, 21))


@pytest.fixture
def at():
    user = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    demo.load_demo_data(user.id)
    app = log_in(fresh_app(), "alice@example.org", PASSWORD)
    return app


def open_pursue(at, target: str):
    at.session_state["pursue_target"] = target
    at.switch_page("app_pages/pursue.py").run()
    assert not at.exception
    return at


def test_the_page_assesses_explains_and_reaches_strong_after_confirming(at):
    open_pursue(at, "grant:sample-01")
    assert at.title[0].value == "Should We Pursue?"
    assert at.selectbox(key="pursue_pick").value == "grant:sample-01"
    at.button(key="pursue_run_grant:sample-01").click().run()
    assert not at.exception
    text = page_text(at)
    assert "### :blue[:material/fact_check: Promising, but verify first]" in text
    assert "**Why:** An eligibility check is unknown, or a rule of the listing is not yet confirmed by you." in text
    assert "##### What we verified" in text and "##### What we still need to know" in text
    assert "based on a sample opportunity" in " ".join(i.value for i in at.info)
    assert "##### Effort breakdown" in text

    for box in at.checkbox:
        if box.key and box.key.startswith("pursue_c_"):
            box.check()
    next(b for b in at.button if b.label == "Save confirmations and assess again").click().run()
    assert not at.exception
    text = page_text(at)
    assert "### :green[:material/verified: Strong candidate]" in text
    assert "Confirmed by you on 2026-10-21" in text
    [latest, previous] = repo.list_pursuit_assessments(1, "grant:sample-01")[:2]
    assert (latest["outcome"], previous["outcome"]) == ("strong", "verify")


def test_a_do_not_pursue_grant_lists_the_failed_check_and_no_confirm_box_for_it(at):
    open_pursue(at, "grant:sample-07")
    at.button(key="pursue_run_grant:sample-07").click().run()
    text = page_text(at)
    assert "Do not pursue under current conditions" in text
    assert "a failed check cannot be confirmed away" in text
    assert not any("Only organizations in TX" in (box.label or "") for box in at.checkbox)


def test_effort_assumptions_change_the_result_immediately(at):
    open_pursue(at, "grant:sample-01")
    at.button(key="pursue_run_grant:sample-01").click().run()
    at.number_input(key="pursue_week_grant:sample-01").set_value(1)
    next(b for b in at.button if b.label == "Save and assess again").click().run()
    assert "Do not pursue under current conditions" in page_text(at)
    assert repo.list_pursuit_assessments(1, "grant:sample-01")[0]["payload"]["settings"]["hours_per_week"] == 1


def test_create_a_workback_plan_from_the_assessment(at):
    open_pursue(at, "grant:sample-01")
    at.button(key="pursue_run_grant:sample-01").click().run()
    at.button(key="pursue_plan_grant:sample-01").click().run()
    app = repo.application_for_grant(1, "sample-01")
    assert repo.get_timeline(1, app["id"]) is not None
    assert any("Workback plan saved" in s.value for s in at.success)


def test_entry_buttons_open_the_page_on_the_right_grant(at):
    at.switch_page("app_pages/find_grants.py").run()
    at.segmented_control(key="search_source").set_value("sample").run()  # the page opens on Grants.gov
    at.button(key="pursue_sample_sample-01").click().run()
    assert not at.exception and at.selectbox(key="pursue_pick").value == "grant:sample-01"
    at.switch_page("app_pages/saved_grants.py").run()
    at.button(key="saved_pursue_sample-05").click().run()
    assert at.selectbox(key="pursue_pick").value == "grant:sample-05"
    app_id = repo.application_for_grant(1, "sample-01")["id"]
    at.switch_page("app_pages/applications.py").run()
    at.button(key=f"pursue_app_{app_id}").click().run()
    assert at.selectbox(key="pursue_pick").value == "grant:sample-01"


def test_an_own_application_can_be_chosen(at):
    own = repo.create_application(1, "Community Foundation request", "Local foundation")
    open_pursue(at, f"application:{own}")
    at.button(key=f"pursue_run_application:{own}").click().run()
    assert not at.exception
    assert "no grant listing in GrantBridge" in page_text(at)
    assert pursuit.OUTCOMES["verify"][0] in page_text(at)

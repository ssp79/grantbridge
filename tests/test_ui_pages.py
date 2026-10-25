"""The redesigned workspace: Dashboard onboarding and reminders, Saved Grants, live saves, and used drafts."""

from datetime import date

import httpx
import pytest

from grantbridge import auth, demo, drafting, repo
from grantbridge import components as c
from grantbridge.db import connect
from tests.conftest import envelope, fake_client, hit, search_data
from tests.test_pages import sign_in_page, PASSWORD, fresh_app, log_in, page_text


@pytest.fixture(autouse=True)
def mock_by_default(monkeypatch):
    monkeypatch.setenv("GRANTBRIDGE_ADVISOR_MODE", "mock")  # no test may spend tokens


def new_user(email="alice@example.org"):
    return auth.sign_up(email, PASSWORD, "Alice Org")


def text(at) -> str:
    return page_text(at) + "\n".join(str(e.value) for e in (*at.error, *at.success))


# ---------------------------------------------------------------- dashboard

def test_a_new_user_lands_on_onboarding_with_one_obvious_next_step():
    new_user()
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    assert at.title[0].value == "Your funding workspace"  # the nav label stays "Dashboard"
    body = text(at)
    assert "Get started in three steps" in body and "1. Tell GrantBridge about your organization" in body
    primary = [b.label for b in at.button if b.proto.type == "primary"]
    assert primary == ["Set up your organization"]  # exactly one primary action on first run
    assert "No applications yet" in body and "Nothing saved yet" in body
    assert "No upcoming verified deadlines" in body


def test_demo_data_from_the_dashboard_fills_every_section():
    user = new_user()
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.button(key="start_demo").click().run()
    assert not at.exception
    body = text(at)
    assert "Demo data loaded" in body
    assert "Get started in three steps" not in body  # profile, saved grants, and an application all exist now
    assert [b.label for b in at.button if b.proto.type == "primary"][0] == "Find funding"
    assert "Connecticut After-School Learning Grant" in body
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Profile"] == "8 of 8" and metrics["Saved grants"] == "2" and metrics["Applications"] == "1"
    # The demo application copies the sample grant's example date: it must never appear as a real deadline.
    assert "Example date 2026-12-11 from a SAMPLE grant: not a real deadline." in body
    assert "No upcoming verified deadlines" in body
    assert c.deadline_reminders(user.id) == []


def test_deadline_reminders_use_only_grants_gov_dates_and_dates_the_user_entered():
    user = new_user()
    demo.load_demo_data(user.id)  # a sample application with an invented date: excluded
    with connect() as conn:
        conn.execute("""INSERT INTO grants (id, title, funder, funder_type, summary, amount_min, amount_max, deadline,
                                            focus_areas, eligible_states, eligibility, questions, source_url,
                                            retrieved_at, is_example)
                        VALUES ('gg-123456', 'Literacy Partnerships', 'Test Agency', 'Federal agency (Grants.gov)', '',
                                NULL, NULL, '2026-12-01', '[]', '[]', '[]', '[]',
                                'https://www.grants.gov/search-results-detail/123456', '2026-10-20T19:51:00+00:00', 0)""")
    repo.save_grant(user.id, "gg-123456")
    own = repo.create_application(user.id, "Community Foundation request", "Local foundation")
    repo.update_application(user.id, own, {"status": "Drafting", "due_date": date(2026, 11, 15),
                                           "amount_requested": None, "notes": ""})
    items = c.deadline_reminders(user.id, today=date(2026, 10, 20))
    assert [(i["title"], i["kind"]) for i in items] == [("Community Foundation request", "entered"),
                                                       ("Literacy Partnerships", "grants.gov")]
    assert all(i["date"] != date(2026, 12, 11) for i in items)  # the sample's example date never appears
    assert c.deadline_reminders(user.id, today=date(2027, 1, 1)) == []  # past dates drop off


# ---------------------------------------------------------------- saved grants

def test_saved_grants_has_a_useful_empty_state():
    new_user()
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page("app_pages/saved_grants.py").run()
    assert "You haven't saved any grants yet" in text(at)
    assert at.button(key="empty_saved-none").label == "Find funding"


def test_saved_grants_lists_labeled_samples_and_remove_works():
    user = new_user()
    demo.load_demo_data(user.id)
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page("app_pages/saved_grants.py").run()
    body = text(at)
    assert body.count("SAMPLE / NOT LIVE") >= 2
    at.button(key="saved_remove_sample-05").click().run()
    assert "sample-05" not in repo.saved_grant_ids(user.id)
    assert "Removed New England Youth Opportunity Fund" in text(at)


def test_work_on_application_from_saved_grants_opens_the_workspace():
    user = new_user()
    demo.load_demo_data(user.id)
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page("app_pages/saved_grants.py").run()
    at.button(key="saved_apply_sample-05").click().run()
    assert not at.exception
    assert at.title[0].value == "Applications"
    assert repo.application_for_grant(user.id, "sample-05") is not None
    assert "New England Youth Opportunity Fund" in text(at)


# ---------------------------------------------------------------- find grants: live save

def test_a_live_grant_can_be_saved_as_a_dated_snapshot(monkeypatch):
    from grantbridge import grants_gov

    user = new_user()
    demo.load_demo_data(user.id)
    monkeypatch.setattr(grants_gov, "_default_client", fake_client(
        lambda r: httpx.Response(200, json=envelope(search_data([hit("361822", "Literacy Partnerships")])))))
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page("app_pages/find_grants.py").run()
    at.segmented_control(key="search_source").set_value("grants.gov").run()
    next(b for b in at.button if b.label == "Search").click().run()
    at.button(key="save_live_361822").click().run()
    assert "gg-361822" in repo.saved_grant_ids(user.id)
    assert at.button(key="save_live_361822").label == "Saved"
    assert "LIVE · Grants.gov" in text(at) and "SAMPLE / NOT LIVE." not in text(at)


# ---------------------------------------------------------------- applications: a used draft is not offered again

def test_a_draft_already_in_the_answer_is_labeled_used():
    user = new_user()
    app_id = demo.load_demo_data(user.id)
    sid = repo.list_sections(user.id, app_id)[0].id
    drafting.draft_section(user.id, sid, want_mock=True)
    drafting.use_draft(user.id, sid)
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page("app_pages/applications.py").run()
    assert not at.exception
    body = text(at)
    assert "Used in your answer" in body
    assert not [b for b in at.button if b.key == f"use_{sid}"]  # no button to use it again
    assert at.button(key=f"discard_{sid}").label == "Dismiss draft"


# ---------------------------------------------------------------- sign in

def test_forgot_password_never_asks_for_an_email():
    at = sign_in_page()
    help_box = next(e for e in at.expander if e.label == "Forgot your password?")
    assert "never says whether an account exists" in " ".join(m.value for m in help_box.markdown)
    assert len(at.text_input) == 6  # the two forms only: log in (2) and create account (4)

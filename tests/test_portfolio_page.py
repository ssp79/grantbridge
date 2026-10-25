"""Portfolio Strategist page end to end (practice mode): settings recompute at once, decisions, drift, commitments."""

from datetime import date

import pytest

from grantbridge import auth, demo, portfolio, repo, timeline
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text


@pytest.fixture(autouse=True)
def mock_and_pinned_clock(monkeypatch):
    monkeypatch.setenv("GRANTBRIDGE_ADVISOR_MODE", "mock")
    monkeypatch.setattr(timeline, "current_date", lambda: date(2026, 10, 21))


@pytest.fixture
def at():
    user = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    demo.load_demo_data(user.id)
    for gid in ("sample-02", "sample-07", "sample-09"):
        repo.save_grant(user.id, gid)
    app = log_in(fresh_app(), "alice@example.org", PASSWORD)
    app.switch_page("app_pages/portfolio.py").run()
    assert not app.exception
    return app


def metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


def test_the_page_shows_statuses_reasons_and_potential_requests(at):
    assert at.title[0].value == "Portfolio Strategist"
    assert [t.label for t in at.tabs] == ["Recommended portfolio", "Weekly capacity", "Mission drift", "Commitments"]
    text = page_text(at)
    assert ":green-badge[:material/check_circle: Recommended]" in text
    assert ":red-badge[:material/block: Excluded]" in text
    assert "It fails a required eligibility check: Only organizations in TX, OK, LA, NM" in text
    assert metric(at, "Potential requests").startswith("$")
    assert "not a search over every combination, and it uses no award probabilities" in text


def test_changing_capacity_recomputes_immediately_and_is_saved(at):
    before = int(metric(at, "Recommended"))
    at.number_input(key="pf_hours").set_value(2).run()
    assert not at.exception
    assert int(metric(at, "Recommended")) < before
    assert portfolio.load_settings(1)["hours_per_week"] == 2


def test_priorities_and_decisions_change_the_result(at):
    at.slider(key="pf_w_funding").set_value(5).run()
    assert portfolio.load_settings(1)["weights"]["funding"] == 5
    at.selectbox(key="pf_dec_grant:sample-02").set_value("skip").run()
    assert "You marked it not interested." in page_text(at)
    assert portfolio.load_settings(1)["status"] == {"grant:sample-02": "skip"}
    at.selectbox(key="pf_dec_grant:sample-02").set_value("auto").run()
    assert portfolio.load_settings(1)["status"] == {}


def test_the_weekly_capacity_table_never_schedules_more_than_your_hours(at):
    rows = at.dataframe[0].value
    assert list(rows.columns) == ["Week of", "Available (yours)", "Scheduled", "Use", "Deadlines", "Status"]
    assert all(s <= a + 0.05 for s, a in zip(rows["Scheduled"], rows["Available (yours)"]))


def test_a_mission_drift_check_from_the_page(at):
    at.button(key="pf_drift_grant-sample-07").click().run()
    assert not at.exception
    assert any("Mission drift for Workforce Bridge Training Grant: High." in s.value for s in at.success)
    assert ":red-badge[:material/error: High mission-drift concern]" in page_text(at)


def test_commitments_can_be_added_and_removed(at):
    form_title = next(t for t in at.text_input if t.label == "Commitment")
    form_title.input("Final report to a current funder")
    at.date_input[0].set_value(date(2026, 11, 20))
    next(b for b in at.button if b.label == "Add commitment").click().run()
    assert not at.exception
    [item] = repo.list_commitments(1)
    assert item["title"] == "Final report to a current funder" and item["hours"] == 4.0
    assert "Final report to a current funder" in " ".join(str(v) for v in at.dataframe[0].value["Deadlines"])
    at.button(key=f"pf_rm_{item['id']}").click().run()
    assert repo.list_commitments(1) == []

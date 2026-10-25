"""Portfolio Strategist: the earliest-deadline-first schedule, the weekly view, and the portfolio's selection rule."""

import json
from datetime import date

import pytest

from grantbridge import advisor, auth, demo, mission_drift, portfolio as pf, pursuit, repo
from grantbridge import advisor_tools as tools
from grantbridge import validation as v

PASSWORD = "correct horse battery staple"
TODAY = date(2026, 10, 21)  # a Wednesday


def job(key, hours, due, deadline=None, order=1):
    return pf.Job(key=key, title=key, hours=hours, due=due, deadline=deadline or due, kind="candidate",
                  hours_source="estimate", order=order)


@pytest.fixture
def user():
    u = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    demo.load_demo_data(u.id)  # saves sample-01 and sample-05; applies (Researching) to sample-01
    for gid in ("sample-02", "sample-03", "sample-07", "sample-09"):
        repo.save_grant(u.id, gid)
    return u


def plan(user, **settings):
    return pf.recommend(user.id, settings={**pf.load_settings(user.id), **settings} if settings else None,
                        today=TODAY)


def by_grant(result):
    return {c["grant_id"]: c for c in result["candidates"]}


# ---------------------------------------------------------------- the schedule (deterministic)

def test_hours_are_spread_over_weekdays_and_weekends_are_skipped():
    result = pf.edf([job("a", 5, date(2026, 10, 23))], 6, TODAY)  # Wed to Fri: 3 days at 1.2 h
    assert sorted(result["alloc"]) == [date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]
    assert result["shortfall"] == {"a": 1.4}
    later = pf.edf([job("a", 5, date(2026, 10, 27))], 6, TODAY)  # Sat and Sun skipped, Mon and Tue added
    assert date(2026, 10, 24) not in later["alloc"] and later["shortfall"] == {}
    assert later["finish"]["a"] == date(2026, 10, 27)


def test_earliest_deadline_first_finds_a_schedule_that_a_priority_order_would_miss():
    """A long job due later and a short job due sooner: only working the sooner one first meets both deadlines."""
    long_job, short_job = job("long", 6, date(2026, 11, 6)), job("short", 2, date(2026, 10, 23))
    assert pf.edf([long_job, short_job], 6, TODAY)["shortfall"] == {}
    result = pf.edf([long_job, short_job], 6, TODAY)
    assert result["finish"]["short"] < result["finish"]["long"]


def test_work_due_before_today_is_all_shortfall():
    assert pf.edf([job("late", 3, date(2026, 10, 20))], 6, TODAY)["shortfall"] == {"late": 3}


def test_the_weekly_view_counts_this_weeks_remaining_days_and_flags_conflicts():
    jobs = [job("a", 10, date(2026, 10, 30)), job("b", 4, date(2026, 11, 13))]
    result = pf.edf(jobs, 6, TODAY)
    weeks = pf.weeks(jobs, result, TODAY)
    assert [w["week"] for w in weeks] == ["2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09"]
    assert weeks[0]["available"] == 3.6 and weeks[0]["status"] == "full"
    assert weeks[1]["status"] == "conflict" and weeks[1]["short"] == {"a": 0.4}
    assert weeks[1]["deadlines"] == ["a"] and weeks[3]["deadlines"] == ["b"]


# ---------------------------------------------------------------- the portfolio

def test_statuses_reasons_and_potential_requests(user):
    result = plan(user)
    cands = by_grant(result)
    assert cands["sample-07"]["status"] == "excluded"
    assert cands["sample-07"]["reasons"][0].startswith("It fails a required eligibility check: Only organizations in")
    assert cands["sample-03"]["status"] == "deferred"  # a rolling deadline cannot be scheduled
    assert cands["sample-03"]["reasons"][0].startswith("It has no deadline")
    recommended = [c for c in result["candidates"] if c["status"] == "recommended"]
    assert recommended and all(c["reasons"][0].startswith("Fits your hours") for c in recommended)
    assert result["potential_requested"] == sum(c["request"] for c in recommended)
    text = json.dumps(result, default=str).lower()
    assert "probability" not in text and "expected value" not in text


def test_the_recommendation_respects_weekly_capacity(user):
    full = plan(user, hours_per_week=6)
    slim = plan(user, hours_per_week=3)
    assert slim["counts"]["recommended"] < full["counts"]["recommended"]
    assert all(w["scheduled"] <= w["available"] + 0.05 for w in slim["weeks"])  # never more than the hours you have
    assert by_grant(slim)["sample-01"]["status"] == "deferred"
    assert "Even with no other grant" in by_grant(slim)["sample-01"]["reasons"][0]


def test_a_higher_priority_grant_can_push_another_out_with_the_reason_given(user):
    result = plan(user, hours_per_week=6)
    deferred = [c for c in result["candidates"] if c["status"] == "deferred" and c["deadline"]]
    assert deferred
    assert any(r.startswith(("After the higher-priority work", "Adding it would push work already planned"))
               for c in deferred for r in c["reasons"])


def test_your_priorities_reorder_the_portfolio(user):
    by_funding = plan(user, weights={"fit": 0, "certainty": 0, "funding": 5, "effort": 0, "alignment": 0})
    by_effort = plan(user, weights={"fit": 0, "certainty": 0, "funding": 0, "effort": 5, "alignment": 0})
    assert by_grant(by_funding)["sample-01"]["score"] == 100.0  # every request is $25,000, the largest
    assert by_grant(by_effort)["sample-01"]["score"] < by_grant(by_effort)["sample-02"]["score"]  # 27 h vs 24 h
    with pytest.raises(v.ValidationError, match="at least one priority"):
        pf.clean_settings({"weights": {k: 0 for k in pf.COMPONENTS}})


def test_must_pursue_goes_first_and_not_interested_is_excluded(user):
    assert by_grant(plan(user, hours_per_week=6))["sample-09"]["status"] == "deferred"  # pushed out by sample-01
    result = plan(user, hours_per_week=6, status={"grant:sample-09": "must", "grant:sample-02": "skip"})
    cands = by_grant(result)
    assert cands["sample-02"]["status"] == "excluded" and cands["sample-02"]["reasons"] == [
        "You marked it not interested."]
    assert cands["sample-09"]["status"] == "recommended"
    assert "You marked it must pursue, so it was placed first." in cands["sample-09"]["reasons"]


def test_must_pursue_that_cannot_fit_is_explained(user):
    cands = by_grant(plan(user, hours_per_week=3, status={"grant:sample-09": "must"}))
    assert cands["sample-09"]["status"] == "deferred"
    assert cands["sample-09"]["reasons"][0].startswith("Even with no other grant")
    assert "You marked it must pursue, but it does not fit" in cands["sample-09"]["reasons"][1]


def test_your_own_hour_estimate_replaces_the_estimate(user):
    result = plan(user, hours_override={"grant:sample-01": 60})
    c = by_grant(result)["sample-01"]
    assert (c["hours"], c["hours_source"]) == (60, "yours")


def test_commitments_take_hours_first(user):
    before = plan(user)
    repo.add_commitment(user.id, "Final report to a current funder", 30, "2026-11-20")
    after = plan(user)
    assert after["counts"]["recommended"] <= before["counts"]["recommended"]
    assert any(c["title"] == "Final report to a current funder" for c in after["commitments"])
    repo.add_commitment(user.id, "Huge audit", 200, "2026-11-02")
    overloaded = plan(user)
    assert overloaded["notes"][0].startswith("Your commitments alone do not fit your hours")


def test_an_application_you_are_drafting_is_a_commitment_not_a_candidate(user):
    app = repo.application_for_grant(user.id, "sample-01")
    repo.update_application(user.id, app["id"], {"status": "Drafting", "due_date": app["due_date"],
                                                  "amount_requested": 25000, "notes": ""})
    result = plan(user)
    assert "sample-01" not in by_grant(result)
    [drafting] = [c for c in result["commitments"] if c["kind"] == "drafting"]
    assert drafting["deadline"] == "2026-12-11" and drafting["hours_source"] == "estimate"


def test_settled_eligibility_can_be_required(user):
    result = plan(user, require_settled=True)
    deferred = [c for c in result["candidates"] if c["status"] == "deferred"
                and "not settled yet" in c["reasons"][0]]
    assert deferred and result["counts"]["recommended"] == 0  # every sample grant has rules to confirm
    first = pursuit.assess(user.id, grant_id="sample-01", want_mock=True, today=TODAY).data
    confirmations = {i["key"]: "2026-10-21" for i in first["dimensions"]["eligibility"]["items"]
                     if i["status"] in ("unknown", "unchecked")}
    pursuit.assess(user.id, grant_id="sample-01", want_mock=True, today=TODAY, confirmations=confirmations)
    settled = plan(user, require_settled=True)
    assert by_grant(settled)["sample-01"]["status"] == "recommended"  # confirmed on Should We Pursue?


def test_high_mission_drift_can_be_excluded_or_only_scored(user):
    repo.save_grant(user.id, "sample-04")
    repo.add_drift_assessment(user.id, "sample-04", "h", "mock", {"overall": "high", "summary": "", "concerns": []})
    assert by_grant(plan(user))["sample-04"]["status"] == "excluded"
    kept = by_grant(plan(user, exclude_high_drift=False))["sample-04"]
    assert kept["status"] != "excluded" and kept["components"]["alignment"] == 0.0


def test_a_passed_deadline_is_excluded(user):
    result = pf.recommend(user.id, today=date(2026, 12, 2))  # sample-09 closed on 2026-11-30
    assert by_grant(result)["sample-09"]["reasons"] == ["Its deadline (2026-11-30) has passed."]


# ---------------------------------------------------------------- settings

def test_settings_are_validated_and_kept(user):
    saved = pf.save_settings(user.id, {"hours_per_week": 9, "weights": {"fit": 5}, "status": {"grant:x": "bogus"}})
    assert saved["hours_per_week"] == 9 and saved["weights"]["fit"] == 5 and saved["status"] == {}
    assert pf.load_settings(user.id)["hours_per_week"] == 9
    for bad in ({"hours_per_week": 0}, {"weights": {"fit": 9}}, {"hours_override": {"grant:sample-01": -1}}):
        with pytest.raises(v.ValidationError):
            pf.clean_settings(bad)


def test_should_we_pursue_uses_your_capacity(user):
    pf.save_settings(user.id, {"hours_per_week": 3})
    data = pursuit.assess(user.id, grant_id="sample-02", want_mock=True, today=TODAY).data
    assert data["settings"]["hours_per_week"] == 3


def test_commitments_are_validated():
    u = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    for title, hours, due in (("", 2, "2026-12-01"), ("Report", 0, "2026-12-01"), ("Report", 2, None)):
        with pytest.raises(v.ValidationError):
            repo.add_commitment(u.id, title, hours, due)


# ---------------------------------------------------------------- the advisor reads the same recommendation

def test_the_advisor_reports_the_codes_portfolio(user):
    result = plan(user)
    out = tools.call_tool(tools.ToolContext(user_id=user.id, user_message="Which grants should we prioritize?",
                                            today=TODAY), "get_portfolio", {})
    assert out.status == "ok"
    assert {g["grant_id"]: g["status"] for g in out.output["grants"]} == {
        c["grant_id"]: c["status"] for c in result["candidates"]}
    assert "not expected or guaranteed awards" in out.output["note"]
    assert advisor.plan("Which grants should we prioritize this fall?") == ("portfolio", None)
    turn = advisor.run_turn(user.id, "Which grants should we prioritize?", want_mock=True)
    assert "potential requests" in turn.reply.reply.lower() and turn.guard_notes == []


def test_mission_drift_module_is_used_only_through_saved_results(user, monkeypatch):
    """Computing the portfolio never calls the AI or Grants.gov: it reads saved checks."""
    monkeypatch.setattr(mission_drift, "check", lambda *a, **k: pytest.fail("the portfolio ran a drift check"))
    plan(user)

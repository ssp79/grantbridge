"""Application Timeline: deadline provenance, workback scheduling, checks, edits, calendar export, and the dashboard."""

import json
from datetime import date, datetime, timezone

import pytest

from grantbridge import advisor_tools as tools
from grantbridge import auth, demo, grant_search as gs, repo, timeline as tl, trace
from grantbridge import components as c
from grantbridge import validation as v
from grantbridge.db import connect

PASSWORD = "correct horse battery staple"
TODAY = date(2026, 10, 21)
COPIED = datetime(2026, 10, 20, 19, 51, tzinfo=timezone.utc)


def live_grant(close: date | None = date(2026, 12, 1), opp_id: str = "999001") -> str:
    """A Grants.gov-style snapshot, as Find Grants saves it."""
    result = gs.GrantResult(
        source=gs.LIVE, id=opp_id, number="TEST-1", title="Community Literacy Partnerships", funder="Test Agency",
        summary="Supports literacy programs.", amount_min=None, amount_max=None, close_date=close,
        deadline=gs.DeadlineStatus("posted", "x", "x", "ok"), status_reported="posted",
        source_url=f"https://www.grants.gov/search-results-detail/{opp_id}", retrieved_at=COPIED,
        eligibility=(), checks=(), unknowns=())
    return repo.save_live_grant_snapshot(result)


def set_due(user_id: int, app_id: int, due) -> None:
    app = repo.get_application(user_id, app_id)
    repo.update_application(user_id, app_id, {"status": app["status"], "due_date": due,
                                              "amount_requested": app["amount_requested"], "notes": app["notes"]})


@pytest.fixture
def user():
    return auth.sign_up("alice@example.org", PASSWORD, "Alice Org")


@pytest.fixture
def sample_app(user):
    return user, demo.load_demo_data(user.id)  # the SAMPLE grant's example date: 2026-12-11


def deadline_of(user, app_id) -> tl.Deadline:
    app = repo.get_application(user.id, app_id)
    return tl.resolve_deadline(app, repo.get_grant(app["grant_id"]) if app["grant_id"] else None)


# ---------------------------------------------------------------- where the deadline comes from

def test_a_sample_grants_date_is_only_ever_an_example(sample_app):
    user, app_id = sample_app
    d = deadline_of(user, app_id)
    assert (d.date, d.source) == (date(2026, 12, 11), "sample")
    assert d.note == "Example date 2026-12-11 from a SAMPLE grant: not a real deadline."


def test_a_grants_gov_date_is_labeled_with_its_copy_date(user):
    app_id = repo.create_application_from_grant(user.id, live_grant())
    d = deadline_of(user, app_id)
    assert (d.date, d.source, d.copied) == (date(2026, 12, 1), "grants.gov", "2026-10-20")
    assert "copied the listing (2026-10-20). Confirm it on Grants.gov" in d.note


def test_a_corrected_date_is_the_users_and_the_listed_date_is_still_shown(user):
    app_id = repo.create_application_from_grant(user.id, live_grant())
    set_due(user.id, app_id, date(2026, 11, 20))
    d = deadline_of(user, app_id)
    assert (d.date, d.source) == (date(2026, 11, 20), "user")
    assert d.note == ("A date you entered. Grants.gov listed 2026-12-01 when GrantBridge copied the listing "
                      "(2026-10-20): check which is right.")
    app = repo.get_application(user.id, app_id)
    assert c.due_date_note(app, repo.get_grant(app["grant_id"])).startswith("Due 2026-11-20: a date you entered.")


def test_no_deadline_is_never_guessed(user):
    own = repo.create_application(user.id, "Community Foundation request")
    d = deadline_of(user, own)
    assert d.date is None and d.source is None and "never guesses" in d.note
    no_close = repo.create_application_from_grant(user.id, live_grant(close=None, opp_id="999002"))
    assert deadline_of(user, no_close).date is None and deadline_of(user, no_close).official is None
    with pytest.raises(v.ValidationError, match="never guesses"):
        tl.build_plan(user.id, own, today=TODAY)
    assert repo.get_timeline(user.id, own) is None
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 0  # nothing ran


# ---------------------------------------------------------------- scheduling

def dates(plan):
    return [(m["step"], m["due_date"]) for m in plan["milestones"]]


def test_with_enough_time_every_step_gets_its_default_days(sample_app):
    user, app_id = sample_app
    out = tl.build_plan(user.id, app_id, today=TODAY)
    assert dates(out["plan"]) == [("eligibility", "2026-11-08"), ("documents", "2026-11-15"), ("budget", "2026-11-20"),
                                  ("draft", "2026-11-30"), ("review", "2026-12-05"), ("revisions", "2026-12-08"),
                                  ("submission", "2026-12-09")]  # 2 days before the 2026-12-11 deadline
    s = out["plan"]["settings"]
    assert (s["days_left"], s["work_days"], s["default_work_days"], s["submit_early"]) == (51, 34, 34, 2)
    assert out["elapsed_ms"] >= 0


def test_the_submit_early_margin_shrinks_before_the_steps(sample_app):
    user, app_id = sample_app
    plan = tl.build_plan(user.id, app_id, today=date(2026, 11, 6))["plan"]  # 35 days left: 1 day to spare
    assert plan["settings"]["submit_early"] == 1 and plan["settings"]["work_days"] == 34
    assert plan["milestones"][-1]["due_date"] == "2026-12-10"


def test_a_short_deadline_shrinks_every_step_and_is_flagged(sample_app):
    user, app_id = sample_app
    out = tl.build_plan(user.id, app_id, today=date(2026, 12, 3))  # 8 days left
    due = [m["due_date"] for m in out["plan"]["milestones"]]
    assert due == sorted(due) and due[0] >= "2026-12-03" and due[-1] == "2026-12-11"
    kinds = {f["kind"] for f in out["flags"]}
    assert {"squeezed", "no_margin", "practice"} <= kinds
    squeezed = next(f for f in out["flags"] if f["kind"] == "squeezed")
    assert squeezed["text"].startswith("Only 8 day(s) for work that the default plan gives 34 days")


def test_due_today_and_passed_deadlines(sample_app):
    user, app_id = sample_app
    out = tl.build_plan(user.id, app_id, today=date(2026, 12, 11))
    assert {m["due_date"] for m in out["plan"]["milestones"]} == {"2026-12-11"}
    assert "due_today" in {f["kind"] for f in out["flags"]}
    with pytest.raises(v.ValidationError, match="has passed"):
        tl.build_plan(user.id, app_id, today=date(2026, 12, 12))


def test_custom_days_are_validated_and_kept_for_rebuilds(sample_app):
    user, app_id = sample_app
    plan = tl.build_plan(user.id, app_id, days={"draft": 20}, submit_early=5, today=TODAY)["plan"]
    assert plan["settings"]["days"]["draft"] == 20 and plan["settings"]["default_submit_early"] == 5
    rebuilt = tl.build_plan(user.id, app_id, today=TODAY)["plan"]
    assert rebuilt["settings"]["days"]["draft"] == 20 and rebuilt["settings"]["default_submit_early"] == 5
    for bad in ({"draft": -1}, {"draft": 500}, {"lunch": 1}, {k: 0 for k in tl.STEPS}):
        with pytest.raises(v.ValidationError):
            tl.build_plan(user.id, app_id, days=bad, today=TODAY)
    with pytest.raises(v.ValidationError):
        tl.build_plan(user.id, app_id, submit_early=99, today=TODAY)


def test_a_plan_is_traced_as_code_steps_with_no_tokens(sample_app):
    user, app_id = sample_app
    out = tl.build_plan(user.id, app_id, today=TODAY)
    steps = trace.run_steps(user.id, out["run_id"])
    assert [s["tool"] for s in steps] == ["resolve_deadline", "schedule_steps", "save_plan", "check_plan"]
    assert all(s["kind"] == "code" and s["input_tokens"] == 0 for s in steps)
    assert steps[0]["summary"] == {"deadline_source": "sample", "days_left": 51}


# ---------------------------------------------------------------- edits, status, and checks

def test_steps_can_be_marked_done_and_redated(sample_app):
    user, app_id = sample_app
    plan = tl.build_plan(user.id, app_id, today=TODAY)["plan"]
    first, second = plan["milestones"][:2]
    repo.update_milestone(user.id, first["id"], first["due_date"], True)
    repo.update_milestone(user.id, second["id"], "2026-11-18", False)
    after = repo.get_timeline(user.id, app_id)["milestones"]
    assert after[0]["done_at"] and not after[0]["edited"]
    assert after[1]["due_date"] == "2026-11-18" and after[1]["edited"] == 1
    repo.update_milestone(user.id, first["id"], first["due_date"], False)
    assert repo.get_timeline(user.id, app_id)["milestones"][0]["done_at"] is None
    with pytest.raises(v.ValidationError):
        repo.update_milestone(user.id, first["id"], "not a date", True)


def test_rebuilding_keeps_done_steps_done(sample_app):
    user, app_id = sample_app
    plan = tl.build_plan(user.id, app_id, today=TODAY)["plan"]
    repo.update_milestone(user.id, plan["milestones"][0]["id"], plan["milestones"][0]["due_date"], True)
    set_due(user.id, app_id, date(2026, 12, 20))
    rebuilt = tl.build_plan(user.id, app_id, today=TODAY)["plan"]
    assert rebuilt["deadline"] == "2026-12-20" and rebuilt["deadline_source"] == "user"
    assert rebuilt["milestones"][0]["done_at"] is not None
    assert all(m["done_at"] is None for m in rebuilt["milestones"][1:])


def test_status_is_in_words(sample_app):
    user, app_id = sample_app
    m = tl.build_plan(user.id, app_id, today=TODAY)["plan"]["milestones"][0]  # due 2026-11-08
    assert tl.status(m, date(2026, 11, 3)) == ("upcoming", "Due in 5 day(s)")
    assert tl.status(m, date(2026, 11, 8)) == ("today", "Due today")
    assert tl.status(m, date(2026, 11, 10)) == ("overdue", "Overdue by 2 day(s)")
    assert tl.status({**m, "done_at": "2026-11-07"}, date(2026, 11, 10)) == ("done", "Done")


def test_overdue_out_of_order_late_and_changed_deadlines_are_flagged(sample_app):
    user, app_id = sample_app
    plan = tl.build_plan(user.id, app_id, today=TODAY)["plan"]
    ms = plan["milestones"]
    repo.update_milestone(user.id, ms[2]["id"], "2026-11-10", False)  # budget now due before documents
    repo.update_milestone(user.id, ms[5]["id"], "2026-12-15", False)  # revisions after the deadline
    set_due(user.id, app_id, date(2026, 12, 18))
    plan = repo.get_timeline(user.id, app_id)
    flags = {f["kind"]: f["text"] for f in tl.check_plan(plan, deadline_of(user, app_id), date(2026, 11, 12))}
    assert flags["overdue"] == "Overdue: Eligibility review (due 2026-11-08); Budget (due 2026-11-10)."
    assert flags["out_of_order"] == ("Budget (2026-11-10) is due before Document collection (2026-11-15); Submission "
                                     "(2026-12-09) is due before Final revisions (2026-12-15). Check the order of your "
                                     "dates.")
    assert flags["after_deadline"] == "Planned after the deadline: Final revisions (2026-12-15)."
    assert "from 2026-12-11 to 2026-12-18" in flags["deadline_changed"]
    passed = {f["kind"] for f in tl.check_plan(plan, deadline_of(user, app_id), date(2026, 12, 12))}
    assert "passed" in passed


def test_a_grants_gov_plan_asks_the_user_to_confirm_the_date(user):
    app_id = repo.create_application_from_grant(user.id, live_grant())
    out = tl.build_plan(user.id, app_id, today=TODAY)
    confirm = next(f for f in out["flags"] if f["kind"] == "confirm")
    assert "copied the listing (2026-10-20). Confirm it on Grants.gov" in confirm["text"]
    assert "practice" not in {f["kind"] for f in out["flags"]}


# ---------------------------------------------------------------- calendar export

def parse_ics(text: str) -> list[dict]:
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    unfolded = text.replace("\r\n ", "")
    events, current = [], None
    for line in unfolded.split("\r\n"):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key] = value
    return events


def test_the_calendar_file_has_open_steps_and_the_deadline_and_no_alarms(sample_app):
    user, app_id = sample_app
    plan = tl.build_plan(user.id, app_id, today=TODAY)["plan"]
    repo.update_milestone(user.id, plan["milestones"][0]["id"], plan["milestones"][0]["due_date"], True)
    plan = repo.get_timeline(user.id, app_id)
    text = tl.to_ics(repo.get_application(user.id, app_id), plan, now=datetime(2026, 10, 21, 12, tzinfo=timezone.utc))
    assert text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "VALARM" not in text and "TRIGGER" not in text  # GrantBridge sends no reminders
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    events = parse_ics(text)
    assert len(events) == 7  # six open steps (eligibility is done) and the deadline
    assert events[0]["DTSTART;VALUE=DATE"] == "20261115" and events[0]["DTEND;VALUE=DATE"] == "20261116"
    assert events[-1]["SUMMARY"] == "Deadline: Connecticut After-School Learning Grant"
    assert "SAMPLE / NOT LIVE grant: not a real deadline" in events[-1]["DESCRIPTION"]
    assert "GrantBridge does not send reminders" in events[0]["DESCRIPTION"]
    assert len({e["UID"] for e in events}) == 7


def test_calendar_text_is_escaped(user):
    app_id = repo.create_application(user.id, "Arts, culture; and more\\stuff")
    set_due(user.id, app_id, date(2026, 12, 1))
    plan = tl.build_plan(user.id, app_id, today=TODAY)["plan"]
    events = parse_ics(tl.to_ics(repo.get_application(user.id, app_id), plan))
    assert events[-1]["SUMMARY"] == "Deadline: Arts\\, culture\\; and more\\\\stuff"


# ---------------------------------------------------------------- dashboard, advisor, privacy

def test_the_dashboard_lists_open_steps_soonest_first_and_only_the_users_own(sample_app):
    user, app_id = sample_app
    plan = tl.build_plan(user.id, app_id, today=TODAY)["plan"]
    repo.update_milestone(user.id, plan["milestones"][0]["id"], plan["milestones"][0]["due_date"], True)
    items = tl.upcoming(user.id, today=TODAY, limit=3)
    assert [(i["step"], i["due"], i["practice"]) for i in items] == [
        ("Document collection", "2026-11-15", True), ("Budget", "2026-11-20", True), ("First draft", "2026-11-30", True)]
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    assert tl.upcoming(bob.id) == []


def test_a_corrected_grants_gov_date_is_reminded_as_the_users_own(user):
    app_id = repo.create_application_from_grant(user.id, live_grant())
    set_due(user.id, app_id, date(2026, 11, 20))
    [item] = c.deadline_reminders(user.id, today=TODAY)
    assert (item["date"], item["kind"]) == (date(2026, 11, 20), "entered")


def test_the_advisor_sees_the_next_step(sample_app):
    user, app_id = sample_app
    tl.build_plan(user.id, app_id, today=TODAY)
    ctx = tools.ToolContext(user_id=user.id, user_message="What should we do next?", today=TODAY)
    result = tools.call_tool(ctx, "get_application_state", {"grant_id": None})
    summary = result.output["applications"][0]["timeline"]
    assert summary["next_step"] == {"step": "Eligibility review", "due": "2026-11-08", "status": "Due in 18 day(s)"}
    assert summary["deadline_source"] == "SAMPLE example date" and summary["steps_done"] == 0


def test_deleting_the_plan_or_the_application_removes_the_milestones(sample_app):
    user, app_id = sample_app
    tl.build_plan(user.id, app_id, today=TODAY)
    repo.delete_timeline(user.id, app_id)
    assert repo.get_timeline(user.id, app_id) is None
    assert repo.get_application(user.id, app_id)["due_date"] == "2026-12-11"  # the deadline is unchanged
    tl.build_plan(user.id, app_id, today=TODAY)
    repo.delete_application(user.id, app_id)
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM timeline_milestones").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM timelines").fetchone()[0] == 0


def test_the_trace_holds_no_titles_or_dates_of_the_plan(sample_app):
    user, app_id = sample_app
    tl.build_plan(user.id, app_id, today=TODAY)
    with connect() as conn:
        dumped = json.dumps([dict(r) for r in conn.execute("SELECT args, summary FROM agent_steps").fetchall()])
    assert "Connecticut" not in dumped and "2026-12-11" not in dumped

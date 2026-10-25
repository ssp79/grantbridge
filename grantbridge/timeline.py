"""Application Timeline: a workback plan from the deadline, with every date computed and checked by code.

The deadline is never invented. It comes from one of three places, and the page always says which:
  - "grants.gov": the close date Grants.gov listed when GrantBridge copied the listing (confirm it there);
  - "sample": the example date of a SAMPLE grant, never a real deadline (a practice plan only);
  - "user": a date the user entered or corrected on the application.
Without a deadline there is no plan: the user is asked for the date.

The plan works back from the deadline through seven steps, using default durations that the user can change.
When less time is left than the defaults need, the submit-early margin goes first, then every step shrinks in
proportion, and the plan says by how much. Code flags a passed deadline, steps that are overdue, out of order, or
after the deadline, a deadline that changed since the plan was built, and plans squeezed below half the default.

The .ics file adds the dates to the user's own calendar. GrantBridge itself sends no reminders.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from grantbridge import repo, trace
from grantbridge import validation as v
from grantbridge.db import SAMPLE_LABEL

STEPS = {  # key: (label, default days, what the step covers); the order is the plan's order
    "eligibility": ("Eligibility review", 3, "Confirm each eligibility rule against the funder's own listing."),
    "documents": ("Document collection", 7, "Gather the attachments the funder asks for, such as proof of 501(c)(3) "
                                            "status or financial statements."),
    "budget": ("Budget", 5, "Finish the budget lines and the budget narrative."),
    "draft": ("First draft", 10, "Answer every question."),
    "review": ("Internal review", 5, "Someone else reads the whole application, and you run Review my proposal."),
    "revisions": ("Final revisions", 3, "Fix what the review found and resolve every [NEEDS] and [VERIFY] marker."),
    "submission": ("Submission", 1, "Submit in the funder's system and keep the confirmation."),
}
assert tuple(STEPS) == repo.TIMELINE_STEPS
DEFAULT_SUBMIT_EARLY = 2  # days before the deadline the plan aims to submit: an assumption the user can change
MAX_STEP_DAYS = 120
MAX_SUBMIT_EARLY = 30
SQUEEZE_WARNING = 0.5  # below half of the default working time, the plan is flagged as unrealistic
SOURCE_LABELS = {"grants.gov": "From Grants.gov", "sample": "SAMPLE example date", "user": "Entered by you"}


def current_date() -> date:
    """Today's date. One function, so tests can pin the clock for the pages too."""
    return date.today()


# ---------------------------------------------------------------- the deadline and where it came from

@dataclass(frozen=True)
class Deadline:
    date: date | None
    source: str | None  # "grants.gov", "sample", "user", or None when there is no deadline
    note: str  # where the date came from, in plain words
    official: date | None  # the grant record's own date (a Grants.gov copy or a sample's example date)
    official_source: str | None
    copied: str  # when GrantBridge copied the Grants.gov listing (YYYY-MM-DD), or ""


def _day(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None  # "rolling", "unknown", or anything else that is not a date


def resolve_deadline(app: dict, grant: dict | None) -> Deadline:
    """The application's deadline and where it came from. GrantBridge never guesses one."""
    official = _day(grant["deadline"]) if grant else None
    official_source = None if grant is None else ("sample" if grant["is_example"] else "grants.gov")
    copied = "" if grant is None or grant["is_example"] else (grant.get("retrieved_at") or "")[:10]
    due = _day(app["due_date"])
    if due is not None and due == official and official_source == "sample":
        return Deadline(due, "sample", f"Example date {due} from a SAMPLE grant: not a real deadline.", official,
                        official_source, copied)
    if due is not None and due == official:
        return Deadline(due, "grants.gov", f"The close date Grants.gov listed when GrantBridge copied the listing "
                                           f"({copied or 'copy date unknown'}). Confirm it on Grants.gov: listings "
                                           "change.", official, official_source, copied)
    if official is None:
        other = ""
    elif official_source == "sample":
        other = f" The {SAMPLE_LABEL} grant's example date is {official}."
    else:
        other = f" Grants.gov listed {official} when GrantBridge copied the listing ({copied}): check which is right."
    if due is None:
        ask = "No deadline set. Enter the funder's deadline: GrantBridge never guesses one."
        return Deadline(None, None, ask + other, official, official_source, copied)
    return Deadline(due, "user", "A date you entered." + other, official, official_source, copied)


# ---------------------------------------------------------------- scheduling (working back from the deadline)

def clean_days(days: dict | None) -> dict[str, int]:
    """The step durations: the defaults, overridden by the user's own numbers."""
    out = {key: default for key, (_, default, _) in STEPS.items()}
    for key, value in (days or {}).items():
        if key not in STEPS:
            raise v.ValidationError("Unknown plan step.")
        out[key] = v.optional_int(value, f"Days for {STEPS[key][0].lower()}", 0, MAX_STEP_DAYS) or 0
    if sum(out.values()) < 1:
        raise v.ValidationError("A plan needs at least one day of work.")
    return out


def schedule(deadline: date, today: date, days: dict[str, int], submit_early: int) -> tuple[list[tuple[str, date]],
                                                                                              dict]:
    """Each step's due date, working back from the deadline. Shrinks the plan when time is short."""
    days_left = (deadline - today).days
    if days_left < 0:
        raise v.ValidationError(f"The deadline ({deadline}) has passed. GrantBridge does not plan for a passed date: "
                                "if the funder has a new deadline, enter it first.")
    span = sum(days.values())
    if days_left >= span + submit_early:
        early, work = submit_early, span
    elif days_left >= span:
        early, work = days_left - span, span  # the submit-early margin shrinks first
    else:
        early, work = 0, days_left  # then every step shrinks in proportion
    end = deadline - timedelta(days=early)  # the submission date
    start = end - timedelta(days=work)
    dated, done_days = [], 0
    for key in STEPS:
        done_days += days[key]
        dated.append((key, start + timedelta(days=int(done_days * work / span + 0.5))))
    meta = {"days_left": days_left, "work_days": work, "default_work_days": span, "submit_early": early,
            "default_submit_early": submit_early, "start": start.isoformat()}
    return dated, meta


# ---------------------------------------------------------------- checks and status (no AI)

def label(milestone: dict) -> str:
    return STEPS[milestone["step"]][0]


def status(milestone: dict, today: date) -> tuple[str, str]:
    """(code, words) for one milestone: done, overdue, today, or upcoming. Words, so color is never the only cue."""
    if milestone["done_at"]:
        return "done", "Done"
    left = (date.fromisoformat(milestone["due_date"]) - today).days
    if left < 0:
        return "overdue", f"Overdue by {-left} day(s)"
    if left == 0:
        return "today", "Due today"
    return "upcoming", f"Due in {left} day(s)"


def check_plan(plan: dict, deadline: Deadline, today: date) -> list[dict]:
    """What a person must look at in the plan, each as {kind, level, text}."""
    out: list[dict] = []

    def add(kind: str, level: str, text: str) -> None:
        out.append({"kind": kind, "level": level, "text": text})

    planned = date.fromisoformat(plan["deadline"])
    if deadline.date is None:
        add("no_deadline", "error", "The application no longer has a deadline. Set it, then rebuild the plan.")
    elif deadline.date != planned:
        add("deadline_changed", "warning", f"The deadline changed after this plan was built (from {planned} to "
                                           f"{deadline.date}). Rebuild the plan.")
    if planned < today:
        add("passed", "error", f"The deadline this plan was built for ({planned}) has passed.")
    elif planned == today:
        add("due_today", "warning", "The deadline is today.")
    milestones = plan["milestones"]
    overdue = [m for m in milestones if status(m, today)[0] == "overdue"]
    if overdue:
        add("overdue", "warning", "Overdue: " + "; ".join(f"{label(m)} (due {m['due_date']})" for m in overdue) + ".")
    swapped = [f"{label(after)} ({after['due_date']}) is due before {label(before)} ({before['due_date']})"
               for before, after in zip(milestones, milestones[1:]) if after["due_date"] < before["due_date"]]
    if swapped:
        add("out_of_order", "warning", "; ".join(swapped) + ". Check the order of your dates.")
    late = [m for m in milestones if date.fromisoformat(m["due_date"]) > planned]
    if late:
        add("after_deadline", "error", "Planned after the deadline: " + "; ".join(
            f"{label(m)} ({m['due_date']})" for m in late) + ".")
    s = plan["settings"]
    if s["work_days"] < s["default_work_days"] * SQUEEZE_WARNING:
        add("squeezed", "warning", f"Only {s['work_days']} day(s) for work that the default plan gives "
                                   f"{s['default_work_days']} days, so every step gets less than half of its default "
                                   "time. Consider whether this deadline is realistic, or apply in a later cycle.")
    elif s["work_days"] < s["default_work_days"]:
        add("shortened", "info", f"The steps are shortened to fit {s['work_days']} day(s) instead of the default "
                                 f"{s['default_work_days']}.")
    if s["submit_early"] == 0 and planned >= today:
        add("no_margin", "info", "The plan has no days left to submit before the deadline day, so there is no time "
                                 "to fix a problem with the submission.")
    if plan["deadline_source"] == "sample":
        add("practice", "info", f"Practice plan: built on an example date from a {SAMPLE_LABEL} grant, which is not a "
                                "real deadline.")
    elif plan["deadline_source"] == "grants.gov":
        add("confirm", "info", f"The deadline is the close date Grants.gov listed when GrantBridge copied the listing "
                               f"({deadline.copied or 'copy date unknown'}). Confirm it on Grants.gov before relying "
                               "on this plan.")
    return out


# ---------------------------------------------------------------- building a plan

def build_plan(user_id: int, application_id: int, *, days: dict | None = None, submit_early: int | None = None,
               today: date | None = None) -> dict:
    """Create or rebuild the workback plan from the application's deadline. Steps already done stay done."""
    started = time.perf_counter()
    application = repo.get_application(user_id, application_id)
    if application is None:
        raise repo.NotFound("Application not found.")
    grant = repo.get_grant(application["grant_id"]) if application["grant_id"] else None
    today = today or current_date()
    existing = repo.get_timeline(user_id, application_id)
    days = clean_days(days if days is not None else (existing or {}).get("settings", {}).get("days"))
    if submit_early is None:
        submit_early = (existing or {}).get("settings", {}).get("default_submit_early", DEFAULT_SUBMIT_EARLY)
    early = v.optional_int(submit_early, "Days to submit early", 0, MAX_SUBMIT_EARLY) or 0
    deadline = resolve_deadline(application, grant)
    if deadline.date is None:
        raise v.ValidationError("Set the deadline first. GrantBridge never guesses one.")
    dated, meta = schedule(deadline.date, today, days, early)  # raises for a passed deadline
    with trace.run(user_id, "plan_timeline") as run:
        with run.step("resolve_deadline", kind="code", application_id=application_id) as step:
            step.ok(deadline_source=deadline.source, days_left=meta["days_left"])
        with run.step("schedule_steps", kind="code") as step:
            step.ok(plan_days=meta["work_days"] + meta["submit_early"],
                    default_days=meta["default_work_days"] + early, steps_total=len(dated))
        with run.step("save_plan", kind="code", application_id=application_id) as step:
            settings = {"days": days, **meta, "built_on": today.isoformat()}
            repo.save_timeline(user_id, application_id, deadline.date.isoformat(), deadline.source, settings,
                               [(key, due.isoformat()) for key, due in dated])
            plan = repo.get_timeline(user_id, application_id)
            step.ok(kept_done=sum(bool(m["done_at"]) for m in plan["milestones"]))
        with run.step("check_plan", kind="code") as step:
            flags = check_plan(plan, deadline, today)
            step.ok(plan_flags=len(flags), overdue_steps=sum(f["kind"] == "overdue" for f in flags))
    return {"plan": plan, "deadline": deadline, "flags": flags, "run_id": run.run_id,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}


def summary(plan: dict | None, today: date | None = None) -> dict | None:
    """A compact view of a plan for the advisor and the dashboard."""
    if plan is None:
        return None
    today = today or current_date()
    open_steps = [m for m in plan["milestones"] if not m["done_at"]]
    nxt = open_steps[0] if open_steps else None
    return {"deadline": plan["deadline"], "deadline_source": SOURCE_LABELS[plan["deadline_source"]],
            "steps_done": len(plan["milestones"]) - len(open_steps), "steps_total": len(plan["milestones"]),
            "next_step": None if nxt is None else {"step": label(nxt), "due": nxt["due_date"],
                                                   "status": status(nxt, today)[1]},
            "overdue_steps": [label(m) for m in open_steps if status(m, today)[0] == "overdue"]}


def upcoming(user_id: int, today: date | None = None, limit: int = 6) -> list[dict]:
    """Milestones not yet done across the user's applications, soonest first (for the dashboard)."""
    today = today or current_date()
    items = []
    for m in repo.list_open_milestones(user_id):
        code, words = status(m, today)
        items.append({"application_id": m["application_id"], "title": m["application_title"], "step": label(m),
                      "due": m["due_date"], "status": code, "words": words,
                      "practice": m["deadline_source"] == "sample"})
    return items[:limit]


# ---------------------------------------------------------------- calendar export (RFC 5545)

def _ics_text(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> list[str]:
    """Lines longer than 75 octets continue on the next line, which starts with a space."""
    parts, current = [], ""
    for ch in line:
        if len((current + ch).encode("utf-8")) > 75:
            parts.append(current)
            current = " " + ch
        else:
            current += ch
    return parts + [current]


DEADLINE_EVENT_NOTES = {
    "grants.gov": "The close date Grants.gov listed when GrantBridge copied the listing. Confirm it on Grants.gov.",
    "sample": f"An example date from a {SAMPLE_LABEL} grant: not a real deadline.",
    "user": "A date you entered in GrantBridge.",
}


def to_ics(application: dict, plan: dict, now: datetime | None = None) -> str:
    """The plan's open steps and the deadline as all-day calendar events. No alarms: GrantBridge sends no reminders."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    title, app_id = application["title"], application["id"]
    events = [(date.fromisoformat(m["due_date"]), f"{label(m)}: {title}",
               f"{STEPS[m['step']][2]} Planned in GrantBridge, working back from the deadline {plan['deadline']}. "
               "GrantBridge does not send reminders.", m["step"])
              for m in plan["milestones"] if not m["done_at"]]
    events.append((date.fromisoformat(plan["deadline"]), f"Deadline: {title}",
                   DEADLINE_EVENT_NOTES[plan["deadline_source"]], "deadline"))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//GrantBridge//Application Timeline//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH"]
    for day, summary_text, description, key in events:
        lines += ["BEGIN:VEVENT", f"UID:grantbridge-app{app_id}-{key}@grantbridge.invalid", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_ics_text(summary_text)}", f"DESCRIPTION:{_ics_text(description)}", "TRANSP:TRANSPARENT",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"

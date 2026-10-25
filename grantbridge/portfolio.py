"""Grant Portfolio Strategist: which grants to prioritize with the hours you actually have.

Everything here is deterministic Python. The mission-drift explanations (mission_drift.py) are the only AI part,
and this module only reads their saved results. Three parts:

1. Capacity. Inputs: your staff hours a week for grant work (yours), the hours each application needs (an estimate
   from editable assumptions, or your own number), and your commitments: applications marked Drafting and other
   work you entered, such as reports. The work is scheduled day by day, earliest deadline first, at a fifth of the
   weekly hours on each weekday, and summed into weeks. Grant work is planned to finish two days before each
   deadline, as on the Timeline tab. Work that cannot fit before its deadline is a shortfall. With staff hours
   pooled and work divisible, earliest-deadline-first meets every deadline whenever any schedule can, so a
   shortfall means the hours really are not there.

2. Portfolio. Every saved grant, and the grant of every application still marked Researching, is a candidate.
   Excluded: you marked it "not interested"; it fails a required eligibility check; its deadline has passed; or, if
   you choose, it carries a high mission-drift concern. If you choose, grants whose eligibility is not settled (met
   or confirmed by you) are deferred. The rest get a priority score from five components, each 0
   to 1, weighted by your priorities (0 to 5): strategic fit, eligibility certainty, potential request, low effort,
   and mission alignment. Grants you marked "must pursue" go first, then the rest by score. Each is added only if
   every deadline (commitments and grants already chosen) can still be met; otherwise it is deferred, with the
   reason. This is a transparent rule, not a search over every combination.

   No award probabilities and no "expected value": a grant's amount is a potential request (your request, capped at
   the listed maximum award), never an expected or guaranteed award.

3. Mission drift. The latest check of each grant feeds the alignment component and the optional exclusion. A grant
   not yet checked counts as unknown (0.5).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from grantbridge import award_feasibility, pursuit, repo, timeline
from grantbridge import budget as budgets
from grantbridge import grant_search as gs
from grantbridge import validation as v

COMPONENTS = {  # key: (label, what a full score means)
    "fit": ("Strategic fit", "focus areas and key words in common (a word-level signal)"),
    "certainty": ("Eligibility certainty", "every eligibility item met or confirmed by you"),
    "funding": ("Potential request", "the largest potential request among these grants (a request, not an award)"),
    "effort": ("Low effort", "the fewest estimated hours among these grants"),
    "alignment": ("Mission alignment", "a low mission-drift concern"),
}
DEFAULT_WEIGHTS = {"fit": 3, "certainty": 3, "funding": 2, "effort": 2, "alignment": 3}
FIT_VALUES = {"good": 1.0, "gap": 0.6, "unknown": 0.5, "caution": 0.2, "blocker": 0.0}
ALIGNMENT_VALUES = {"low": 1.0, "moderate": 0.6, "unknown": 0.5, None: 0.5, "high": 0.0}
SUBMIT_EARLY_DAYS = 2
EPS = 1e-6
SHORTFALL_HOURS = 0.05  # below this, rounding noise
MAX_HORIZON_DAYS = 400
_KEY = re.compile(r"^(?:grant:[a-z0-9\-]{1,40}|application:\d{1,12})$")
STATUS_WORDS = {"recommended": "Recommended", "deferred": "Deferred", "excluded": "Excluded"}


# ---------------------------------------------------------------- settings (the user's own numbers)

def clean_settings(raw: dict | None) -> dict:
    raw = raw or {}
    hours = v.optional_int(raw.get("hours_per_week", pursuit.DEFAULT_HOURS_PER_WEEK), "Staff hours a week", 1, 80)
    weights = {}
    for key, default in DEFAULT_WEIGHTS.items():
        weights[key] = v.optional_int((raw.get("weights") or {}).get(key, default),
                                      f"Weight for {COMPONENTS[key][0].lower()}", 0, 5) or 0
    if not any(weights.values()):
        raise v.ValidationError("Give at least one priority a weight above 0.")
    status = {k: s for k, s in (raw.get("status") or {}).items() if _KEY.match(str(k)) and s in ("must", "skip")}
    overrides = {}
    for k, h in (raw.get("hours_override") or {}).items():
        if _KEY.match(str(k)) and h not in (None, ""):
            overrides[k] = float(v.decimal(h, "Your hour estimate", places=1, lo=Decimal(0), hi=Decimal(500)))
    return {"hours_per_week": hours, "weights": weights, "exclude_high_drift": bool(raw.get("exclude_high_drift", True)),
            "require_settled": bool(raw.get("require_settled", False)),
            "defer_cash_burden": bool(raw.get("defer_cash_burden", False)), "status": status,
            "hours_override": overrides, "effort_hours": pursuit.clean_hours(raw.get("effort_hours"))}


def load_settings(user_id: int) -> dict:
    try:
        return clean_settings(repo.get_capacity_settings(user_id))
    except v.ValidationError:
        return clean_settings({})  # a stored value from an older version: start from the defaults


def save_settings(user_id: int, settings: dict) -> dict:
    cleaned = clean_settings(settings)
    repo.save_capacity_settings(user_id, cleaned)
    return cleaned


# ---------------------------------------------------------------- scheduling (earliest deadline first)

@dataclass
class Job:
    key: str
    title: str
    hours: float
    due: date  # the last day to work on it
    deadline: date
    kind: str  # "commitment" (yours), "drafting" (an application you are drafting), or "candidate"
    hours_source: str  # "yours" or "estimate"
    order: int = 0  # "must pursue" first among equal due dates


def workdays(start: date, end: date):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def edf(jobs: list[Job], hours_per_week: float, today: date) -> dict:
    """Fill each weekday's hours with the unfinished work due soonest. Returns allocations, finish days, shortfalls."""
    daily = hours_per_week / 5
    remaining = {j.key: j.hours for j in jobs}
    finish: dict[str, date] = {j.key: today for j in jobs if j.hours <= EPS}
    alloc: dict[date, dict[str, float]] = defaultdict(dict)
    order = sorted(jobs, key=lambda j: (j.due, j.order, j.key))
    end = min(max((j.due for j in jobs), default=today), today + timedelta(days=MAX_HORIZON_DAYS))
    for day in workdays(today, end):
        cap = daily
        for j in order:
            if cap <= EPS:
                break
            if remaining[j.key] <= EPS or day > j.due:
                continue
            use = min(cap, remaining[j.key])
            alloc[day][j.key] = alloc[day].get(j.key, 0.0) + use
            remaining[j.key] -= use
            cap -= use
            if remaining[j.key] <= EPS:
                finish[j.key] = day
    shortfall = {k: round(r, 1) for k, r in remaining.items() if r > SHORTFALL_HOURS}
    return {"alloc": alloc, "finish": finish, "shortfall": shortfall, "daily": daily}


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def weeks(jobs: list[Job], result: dict, today: date) -> list[dict]:
    """The schedule summed into weeks: available hours, scheduled hours, deadlines, shortfalls, and a status."""
    if not jobs:
        return []
    last = min(max(max(j.due for j in jobs), max(j.deadline for j in jobs)), today + timedelta(days=MAX_HORIZON_DAYS))
    out, start = [], week_start(today)
    titles = {j.key: j.title for j in jobs}
    while start <= last:
        end = start + timedelta(days=6)
        days = list(workdays(max(start, today), start + timedelta(days=4)))
        available = result["daily"] * len(days)
        per_job: dict[str, float] = {}
        for day in days:
            for key, hours in result["alloc"].get(day, {}).items():
                per_job[key] = per_job.get(key, 0.0) + hours
        scheduled = sum(per_job.values())
        short = {titles[j.key]: result["shortfall"][j.key] for j in jobs
                 if j.key in result["shortfall"] and start <= max(j.due, today) <= end}
        status = "conflict" if short else "full" if available and scheduled >= available - 0.05 else "ok"
        out.append({"week": start.isoformat(), "available": round(available, 1), "scheduled": round(scheduled, 1),
                    "per_job": {titles[k]: round(h, 1) for k, h in per_job.items()},
                    "deadlines": [j.title for j in jobs if start <= j.deadline <= end],
                    "short": short, "status": status})
        start += timedelta(days=7)
    return out


# ---------------------------------------------------------------- commitments and candidates

def _hours(key: str, target: pursuit.Target, b, settings: dict) -> tuple[float, str]:
    if key in settings["hours_override"]:
        return settings["hours_override"][key], "yours"
    return pursuit.effort(target, b, settings["effort_hours"])["hours"], "estimate"


def commitments(user_id: int, settings: dict, today: date) -> tuple[list[Job], list[str]]:
    """Work already promised: what you entered, and applications marked Drafting."""
    jobs, notes = [], []
    for c in repo.list_commitments(user_id):
        due = date.fromisoformat(c["due_date"])
        jobs.append(Job(key=f"commitment:{c['id']}", title=c["title"], hours=c["hours"], due=due, deadline=due,
                        kind="commitment", hours_source="yours"))
    for a in repo.list_applications(user_id):
        if a["status"] != "Drafting":
            continue
        key = f"application:{a['id']}"
        target = pursuit.load_target(user_id, application_id=a["id"], fetch=False)
        hours, source = _hours(key, target, budgets.summarize(user_id, a["id"]), settings)
        deadline = pursuit.deadline_for(target).date
        if deadline is None:
            notes.append(f"{a['title']} (Drafting) has no deadline, so its work is not scheduled. Set one on its "
                         "Timeline tab.")
            continue
        jobs.append(Job(key=key, title=a["title"], hours=hours, due=deadline - timedelta(days=SUBMIT_EARLY_DAYS),
                        deadline=deadline, kind="drafting", hours_source=source))
    return jobs, notes


def candidate_keys(user_id: int) -> list[str]:
    """Saved grants and the grants of applications still marked Researching. Grants you are drafting are
    commitments; submitted, awarded, or declined ones are finished."""
    apps = repo.list_applications(user_id)
    busy = {a["grant_id"] for a in apps if a["grant_id"] and a["status"] != "Researching"}
    ids = [g["id"] for g in repo.list_saved_grants(user_id)]
    ids += [a["grant_id"] for a in apps if a["grant_id"] and a["status"] == "Researching"]
    return [f"grant:{gid}" for gid in dict.fromkeys(ids) if gid not in busy]


def _request(target: pursuit.Target) -> tuple[int | None, str]:
    asked = (target.application or {}).get("amount_requested") or target.org.get("requested_amount")
    high = (target.grant or {}).get("amount_max")
    if asked and high and asked > high:
        return high, f"your ${asked:,} request, capped at the listed ${high:,} maximum award"
    return asked, ("from your application" if (target.application or {}).get("amount_requested")
                   else "from your profile") if asked else "no request amount in your profile or application"


def describe(user_id: int, key: str, settings: dict, today: date) -> dict:
    """Everything the portfolio knows about one candidate, from the existing features. No AI, no Grants.gov."""
    grant_id = key.removeprefix("grant:")
    target = pursuit.load_target(user_id, grant_id=grant_id, fetch=False)
    latest = (repo.list_pursuit_assessments(user_id, key, limit=1) or [None])[0]
    confirmations = latest["payload"]["settings"]["confirmations"] if latest else {}
    if latest is not None and not target.is_sample:  # a full check against Grants.gov beats the offline one
        eligibility = latest["payload"]["dimensions"]["eligibility"]
        fit = latest["payload"]["dimensions"]["fit"]
        eligibility_source = f"your Should We Pursue? check of {latest['created_at'][:10]}"
    else:
        eligibility = pursuit.eligibility(target, confirmations)
        fit = pursuit.fit(target)
        eligibility_source = "GrantBridge's checks" + (" with your confirmations" if confirmations else "")
    app = target.application
    hours, hours_source = _hours(key, target, budgets.summarize(user_id, app["id"]) if app else None, settings)
    deadline = pursuit.deadline_for(target)
    request, request_note = _request(target)
    drift = repo.latest_drift_assessment(user_id, grant_id)
    items = eligibility["items"]
    settled = sum(i["status"] == gs.MEETS or bool(i["confirmed_on"]) for i in items)
    return {
        "key": key, "grant_id": grant_id, "title": (target.grant or {}).get("title", grant_id),
        "sample": target.is_sample, "application_id": app["id"] if app else None,
        "eligibility": {"level": eligibility["level"], "settled": settled, "total": len(items),
                        "hard_fail": next((i["detail"] for i in items if i["status"] == gs.FAILS and i["hard"]), None),
                        "source": eligibility_source},
        "fit": {"level": fit["level"], "reason": fit["reason"]},
        "hours": round(hours, 1), "hours_source": hours_source,
        "deadline": deadline.date.isoformat() if deadline.date else None, "deadline_source": deadline.source,
        "deadline_note": deadline.note, "request": request, "request_note": request_note,
        "drift": None if drift is None else {"overall": drift["payload"]["overall"], "checked": drift["created_at"][:10],
                                             "mode": drift["mode"], "summary": drift["payload"]["summary"]},
        "afford": award_feasibility.signal(user_id, target),  # Can We Afford to Win?, when it has been run
        "decision": settings["status"].get(key, "auto"),
    }


# ---------------------------------------------------------------- scoring and selection

def components(c: dict, pool: list[dict]) -> dict[str, float]:
    max_request = max((p["request"] or 0 for p in pool), default=0)
    max_hours = max((p["hours"] for p in pool), default=0)
    total = c["eligibility"]["total"]
    return {
        "fit": FIT_VALUES.get(c["fit"]["level"], 0.5),
        "certainty": c["eligibility"]["settled"] / total if total else 0.5,
        "funding": (c["request"] or 0) / max_request if max_request else 0.0,
        "effort": 1 - c["hours"] / max_hours if max_hours else 1.0,
        "alignment": ALIGNMENT_VALUES.get((c["drift"] or {}).get("overall"), 0.5),
    }


def score(parts: dict[str, float], weights: dict[str, int]) -> float:
    total = sum(weights.values())
    return round(100 * sum(weights[k] * parts[k] for k in parts) / total, 1) if total else 0.0


def _exclusion(c: dict, settings: dict, today: date) -> str | None:
    if c["decision"] == "skip":
        return "You marked it not interested."
    if c["eligibility"]["hard_fail"]:
        return f"It fails a required eligibility check: {c['eligibility']['hard_fail']}"
    if c["deadline"] and date.fromisoformat(c["deadline"]) < today:
        return f"Its deadline ({c['deadline']}) has passed."
    if settings["exclude_high_drift"] and (c["drift"] or {}).get("overall") == "high":
        return "It carries a high mission-drift concern (you chose to exclude these)."
    return None


def recommend(user_id: int, settings: dict | None = None, today: date | None = None) -> dict:
    """The recommended portfolio: every candidate's status with its reasons, and the week-by-week schedule."""
    today = today or timeline.current_date()
    settings = clean_settings(settings) if settings is not None else load_settings(user_id)
    per_week = settings["hours_per_week"]
    committed, notes = commitments(user_id, settings, today)
    base = edf(committed, per_week, today)
    if base["shortfall"]:
        names = {j.key: j.title for j in committed}
        notes.insert(0, "Your commitments alone do not fit your hours: " + "; ".join(
            f"{names[k]} would be {h:g} h short" for k, h in base["shortfall"].items()) + ".")
    cands = [describe(user_id, key, settings, today) for key in candidate_keys(user_id)]
    for c in cands:
        c["status"], c["reasons"] = None, []
        reason = _exclusion(c, settings, today)
        if reason:
            c["status"], c["reasons"] = "excluded", [reason]
    pool = [c for c in cands if c["status"] is None]
    for c in cands:
        c["components"] = components(c, pool or cands)
        c["score"] = score(c["components"], settings["weights"])
    for c in pool:
        if not c["deadline"]:
            c["status"], c["reasons"] = "deferred", ["It has no deadline, so it cannot be scheduled. Set a date (or a "
                                                     "target date for a rolling deadline) on its application's Timeline "
                                                     "tab."]
        elif date.fromisoformat(c["deadline"]) - timedelta(days=SUBMIT_EARLY_DAYS) < today:
            c["status"], c["reasons"] = "deferred", ["Fewer than two days are left before its deadline."]
        elif settings["require_settled"] and c["eligibility"]["settled"] < c["eligibility"]["total"]:
            open_items = c["eligibility"]["total"] - c["eligibility"]["settled"]
            c["status"], c["reasons"] = "deferred", [f"{open_items} eligibility item(s) are not settled yet, and you "
                                                     "chose to recommend only settled grants. Confirm them on Should "
                                                     "We Pursue?."]
        elif (settings["defer_cash_burden"] and c["afford"] and c["afford"]["known"]
              and c["afford"]["level"] == "burden"):  # never for an unknown term: missing is not a "no"
            c["status"], c["reasons"] = "deferred", [f"{c['afford']['reason']} You chose to defer grants that would "
                                                     "strain your cash (Can we afford to win?)."]
    order = sorted((c for c in pool if c["status"] is None),
                   key=lambda c: (c["decision"] != "must", -c["score"], c["deadline"], c["title"]))
    chosen = list(committed)
    titles = {j.key: j.title for j in committed}
    for c in order:
        deadline = date.fromisoformat(c["deadline"])
        job = Job(key=c["key"], title=c["title"], hours=c["hours"], due=deadline - timedelta(days=SUBMIT_EARLY_DAYS),
                  deadline=deadline, kind="candidate", hours_source=c["hours_source"],
                  order=0 if c["decision"] == "must" else 1)
        trial = edf(chosen + [job], per_week, today)
        new_short = {k: h for k, h in trial["shortfall"].items() if k not in base["shortfall"]}
        if not new_short:
            chosen.append(job)
            titles[job.key] = job.title
            c["status"] = "recommended"
            finished = trial["finish"].get(job.key, today)
            c["reasons"] = [f"Fits your hours: its work can be done by {finished:%b %d}, before the {deadline:%b %d} "
                            "deadline (two days early)."]
            if c["decision"] == "must":
                c["reasons"].append("You marked it must pursue, so it was placed first.")
            continue
        alone = edf(committed + [job], per_week, today)
        c["status"] = "deferred"
        if job.key in alone["shortfall"]:
            c["reasons"] = [f"Even with no other grant, about {alone['shortfall'][job.key]:g} hours of its work would "
                            f"not fit before {deadline:%b %d} at {per_week} hours a week."]
        elif job.key in new_short:
            c["reasons"] = [f"After the higher-priority work above, about {new_short[job.key]:g} hours of it would not "
                            f"fit before {deadline:%b %d}."]
        else:
            pushed = "; ".join(f"{titles.get(k, k)} ({h:g} h short)" for k, h in new_short.items())
            c["reasons"] = [f"Adding it would push work already planned past its deadline: {pushed}."]
        if c["decision"] == "must":
            c["reasons"].append("You marked it must pursue, but it does not fit: add hours or move a commitment.")
    final = edf(chosen, per_week, today)
    recommended = [c for c in cands if c["status"] == "recommended"]
    for c in cands:  # explain each score in words: the components that helped and hurt most
        weighted = sorted(((settings["weights"][k] * value, k) for k, value in c["components"].items()
                           if settings["weights"][k]), reverse=True)
        if weighted:
            c["strengths"] = [COMPONENTS[k][0] for _, k in weighted[:2] if c["components"][k] >= 0.6]
            c["weaknesses"] = [COMPONENTS[k][0] for _, k in weighted[::-1][:2] if c["components"][k] < 0.5]
        else:
            c["strengths"], c["weaknesses"] = [], []
    cands.sort(key=lambda c: (["recommended", "deferred", "excluded"].index(c["status"]), -c["score"], c["title"]))
    return {
        "settings": settings, "today": today.isoformat(), "candidates": cands, "notes": notes,
        "commitments": [{"key": j.key, "title": j.title, "hours": j.hours, "deadline": j.deadline.isoformat(),
                         "kind": j.kind, "hours_source": j.hours_source,
                         "short": base["shortfall"].get(j.key)} for j in committed],
        "weeks": weeks(chosen, final, today),
        "potential_requested": sum(c["request"] or 0 for c in recommended),
        "planned_hours": round(sum(j.hours for j in chosen), 1),
        "counts": {s: sum(c["status"] == s for c in cands) for s in ("recommended", "deferred", "excluded")},
    }


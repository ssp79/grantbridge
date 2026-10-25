"""Page building blocks shared by every page: headers, empty states, grant cards, and provenance labels.

Every grant on every page carries one of two labels, so a sample can never pass for a real opportunity:
SAMPLE (orange, warm card edge) or LIVE · Grants.gov (navy card edge, with the retrieval time and a link).
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import date

import streamlit as st

from grantbridge import grant_search as gs
from grantbridge import repo, ui
from grantbridge.db import SAMPLE_LABEL

SAMPLE_BADGE = f":orange-badge[:material/science: {SAMPLE_LABEL}]"
LIVE_BADGE = ":blue-badge[:material/public: LIVE · Grants.gov listing]"
OWN_BADGE = ":gray-badge[:material/edit_note: Your own application]"
TONE_COLORS = {"example": "orange", "ok": "green", "warn": "orange", "no": "red", "info": "blue"}
OUTCOME_ICONS = {gs.MEETS: ":green[:material/check_circle: Meets]", gs.FAILS: ":red[:material/cancel: Does not meet]",
                 gs.UNKNOWN: ":orange[:material/help: Unknown]"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:60] or "x"


def header(title: str, icon: str, intro: str | None = None) -> None:
    """Page title (matching its navigation label) and one plain sentence on what the page is for.

    Every authenticated page uses this, so the title, the line of orientation, and the rule under them land in the
    same place on each one. The styling hangs off the `page-head` key (see ui.CSS).
    """
    with st.container(key="page-head"):
        st.title(title, icon=icon, anchor=False)
        if intro:
            st.markdown(intro)


def empty_state(icon: str, title: str, body: str, *, action: str | None = None, key: str | None = None,
                primary: bool = True) -> bool:
    """What is missing, why it matters, and the next step. Returns True when the action button is clicked."""
    with st.container(border=True, key=f"card-empty-{slug(key or title)}"):
        st.markdown(f"**{icon} {title}**")
        st.markdown(body)
        if action:
            return st.button(action, key=f"empty_{slug(key or title)}", type="primary" if primary else "secondary")
    return False


def deadline_badge(deadline: gs.DeadlineStatus) -> str:
    color = TONE_COLORS.get(deadline.tone, "gray")
    return f":{color}-badge[{ui.md_safe(deadline.label)}]"


def award_text(r: gs.GrantResult) -> str:
    if r.amount_min or r.amount_max:
        return ui.amount_range(r.amount_min, r.amount_max)
    return "Load details to see" if r.is_live and not r.details_loaded else "Not listed"


def meta_line(r: gs.GrantResult) -> str:
    """Funder · award · source, in one line. A sample has no source; a live grant links to Grants.gov."""
    source = f"[Grants.gov page]({r.source_url})" if r.is_live else "none (sample grant)"
    funder = ui.md_safe(r.funder) + (f" · {ui.md_safe(r.number)}" if r.is_live and r.number else "")
    return f"{funder} · **Award:** {award_text(r)} · **Source:** {source}"


def fit_verdict(r: gs.GrantResult) -> str:
    """One plain-language line on how the grant matches the profile, from GrantBridge's rules (not AI).

    Icons and words carry the meaning, never color alone. It never says "eligible": only the funder decides.
    """
    fails = [c for c in r.checks if c.outcome == gs.FAILS]
    unknown = [c for c in r.checks if c.outcome == gs.UNKNOWN]
    hard = [c for c in fails if c.hard]
    total = len(r.checks)
    if hard:
        return (f":red[:material/block:] **Not a match on a required rule:** {hard[0].name.lower()}. "
                "See the checks below.")
    if fails:
        names = ", ".join(c.name.lower() for c in fails)
        return f":orange[:material/rule:] **Partial match:** {total - len(fails) - len(unknown)} of {total} checks met; not met: {names}."
    if unknown:
        return (f":orange[:material/help:] **Can't tell yet:** {len(unknown)} of {total} checks need details from your "
                "profile.")
    return f":green[:material/check_circle:] **Matches all {total} checks** GrantBridge can run."


def verify_line(r: gs.GrantResult) -> str:
    """How many requirements no code can check, which the user has to read for themselves."""
    n = len(r.unknowns)
    if not n:
        return ":material/fact_check: Before applying, read the funder's full notice yourself."
    return (f":material/fact_check: **{n} requirement{'s' if n != 1 else ''} to check yourself**, such as: "
            f"{ui.md_safe(r.unknowns[0].removeprefix('Not checked automatically: '))}")


def deadline_text(r: gs.GrantResult) -> str:
    return "None: practice grant" if not r.is_live else ui.md_safe(r.deadline.label)


@contextmanager
def grant_card(r: gs.GrantResult, key: str):
    """A grant as a card built for scanning: label, name, funder / award / deadline, fit, and what to verify.

    The caller adds the next actions and the expandable details inside the `with` block.
    """
    kind = "live" if r.is_live else "sample"
    with st.container(border=True, key=f"card-{kind}-{slug(key)}"):
        st.markdown(LIVE_BADGE if r.is_live else SAMPLE_BADGE)
        st.subheader(r.title, anchor=False)
        f_col, a_col, d_col = st.columns(3)
        f_col.markdown(f"**Funder**  \n{ui.md_safe(r.funder)}")
        a_col.markdown(f"**Award**  \n{award_text(r)}")
        d_col.markdown(f"**Deadline**  \n{deadline_text(r)}")
        st.markdown(fit_verdict(r))
        st.markdown(verify_line(r))
        yield


def grant_details(r: gs.GrantResult) -> None:
    """Everything else about a grant, for the card's details expander."""
    if r.summary:
        st.markdown(ui.external_md(ui.clip(r.summary, 600)))
    st.markdown(meta_line(r))
    st.caption(r.deadline.detail)
    st.markdown("**Every check GrantBridge ran (rules, not AI)**")
    st.markdown("\n".join(f"- {OUTCOME_ICONS[c.outcome]} · **{c.name}:** {ui.md_safe(c.detail)}" for c in r.checks))
    if r.eligibility:
        st.markdown("**Eligibility as listed by the source**")
        st.markdown("\n".join(f"- {ui.external_md(e)}" for e in r.eligibility))
    if r.eligibility_text:
        st.markdown("**Eligibility notes from the Grants.gov notice (excerpt)**")
        st.markdown(ui.external_md(ui.clip(r.eligibility_text, 1200)))
    st.markdown("**To check yourself (GrantBridge cannot check these)**")
    st.markdown("\n".join(f"- {ui.md_safe(u)}" for u in r.unknowns) or "- Nothing listed.")
    if not r.is_live:
        grant = repo.get_grant(r.id)
        if grant and grant["questions"]:
            st.markdown("**Application questions**")
            st.markdown("\n".join(f"{n}. {ui.external_md(q)}" for n, q in enumerate(grant["questions"], 1)))
    if r.is_live and r.retrieved_at:
        st.caption(f"Retrieved from {r.source_url} on {gs.fmt_time(r.retrieved_at)}.")


def explanation_block(result, key: str) -> None:
    """An AI fit explanation (fit_explainer.ExplainOutcome), clearly marked as AI-written and checked by code."""
    with st.container(border=True, key=f"card-explain-{slug(key)}"):
        if result.explanation is None:
            st.warning(result.error, icon=":material/smart_toy:")
            return
        e = result.explanation
        st.markdown(f":violet-badge[:material/smart_toy: AI explanation] **AI fit explanation:** {e.verdict} · "
                    f"confidence {e.confidence}")
        st.markdown(ui.md_safe(e.summary))
        if e.reasons:
            st.markdown("\n".join(f"- {ui.md_safe(x.point)} _(based on {x.based_on})_" for x in e.reasons))
        if e.uncertainties:
            st.markdown("**What is uncertain**\n" + "\n".join(f"- {ui.md_safe(u)}" for u in e.uncertainties))
        if e.verify_next:
            st.markdown("**Verify next**\n" + "\n".join(f"- {ui.md_safe(x)}" for x in e.verify_next))
        for note in result.guard_notes:
            st.caption(f":material/shield: {note}")
        st.caption(
            f"Written by {ui.usage_line(result.cost) or result.model}. AI can be wrong. The checks above come from "
            "deterministic code, and only the funder's own notice is authoritative."
        )


# ---------------------------------------------------------------- applications and dates

def application_badge(grant: dict | None) -> str:
    if grant is None:
        return OWN_BADGE
    return SAMPLE_BADGE if grant["is_example"] else ":blue-badge[:material/public: Grants.gov snapshot]"


def due_date_note(app: dict, grant: dict | None) -> str:
    """Where an application's due date came from (timeline.resolve_deadline). A sample's date is never presented as
    a real deadline, and a date the user changed is never presented as the Grants.gov date."""
    from grantbridge import timeline  # timeline imports nothing from the UI layer

    deadline = timeline.resolve_deadline(app, grant)
    if deadline.date is None or deadline.source == "sample":
        return deadline.note
    return f"Due {deadline.date}: {deadline.note[0].lower()}{deadline.note[1:]}"


def deadline_reminders(user_id: int, today: date | None = None) -> list[dict]:
    """Upcoming deadlines that come from Grants.gov or from the user, never from a sample grant.

    For an application, the date and its source come from timeline.resolve_deadline: the Grants.gov close date
    as copied, or a date the user entered or corrected (shown as theirs). A saved Grants.gov listing without an
    application shows its listed close date. Practice applications on sample grants never appear.
    """
    from grantbridge import timeline

    today = today or date.today()
    items, covered = [], set()
    for a in repo.list_applications(user_id):
        grant = repo.get_grant(a["grant_id"]) if a["grant_id"] else None
        if grant is not None and grant["is_example"]:
            continue  # a practice application: its dates are never reminders
        deadline = timeline.resolve_deadline(a, grant)  # a date the user changed is theirs, not Grants.gov's
        if deadline.date is None:
            continue
        if grant is not None:
            covered.add(grant["id"])
        if deadline.date >= today:
            items.append({"date": deadline.date, "title": a["title"],
                          "kind": "grants.gov" if deadline.source == "grants.gov" else "entered",
                          "url": grant["source_url"] if grant else None, "copied": deadline.copied,
                          "application_id": a["id"]})
    for saved in repo.list_saved_grants(user_id):
        g = repo.get_grant(saved["id"])
        if g is None or g["is_example"] or g["id"] in covered:
            continue
        try:
            when = date.fromisoformat(g["deadline"])
        except (TypeError, ValueError):
            continue  # "unknown": Grants.gov listed no close date
        if when >= today:
            items.append({"date": when, "title": g["title"], "kind": "grants.gov", "url": g["source_url"],
                          "copied": (g.get("retrieved_at") or "")[:10], "application_id": None})
    return sorted(items, key=lambda i: i["date"])


def profile_meter(org: dict | None) -> tuple[int, int, list[str]]:
    """(key fields filled, total key fields, labels still missing)."""
    missing = repo.missing_profile_fields(org)
    total = len(repo.KEY_PROFILE_FIELDS)
    return total - len(missing), total, missing


# ---------------------------------------------------------------- the dashboard's working lists
# Both functions below read only this account's rows and report only what is in them. Nothing is inferred,
# predicted, or filled in: an empty list means there is genuinely nothing to show.

ATTENTION_WINDOW_DAYS = 21  # a deadline further off than this is not yet "needing attention"


def attention_items(user_id: int, today: date | None = None, limit: int = 6) -> list[dict]:
    """What actually needs the user's attention, soonest and most urgent first.

    Each item is {urgency, title, detail, action, page, application_id, grant_id}. Urgency is "overdue", "soon" or
    "open". Drawn from: workback steps that are late or due, verification items left open on an application,
    verified deadlines inside the window, and saved grants never assessed.
    """
    from grantbridge import drafting, timeline

    today = today or date.today()
    items: list[dict] = []

    for step in timeline.upcoming(user_id, today=today, limit=20):
        if step["status"] not in ("overdue", "today"):
            continue
        items.append({"urgency": "overdue" if step["status"] == "overdue" else "soon",
                      "title": f"{step['step']} · {step['title']}",
                      "detail": f"{step['words']} (due {step['due']})"
                                + (" · practice plan from a SAMPLE date" if step["practice"] else ""),
                      "action": "Open the timeline", "page": "app_pages/applications.py",
                      "application_id": step["application_id"], "grant_id": None})

    for p in drafting.application_progress(user_id):
        if p["open_items"]:
            items.append({"urgency": "open", "title": f"Verify {p['open_items']} item(s) · {p['title']}",
                          "detail": "Statements in your answers that a person still has to check before you submit.",
                          "action": "Open the application", "page": "app_pages/applications.py",
                          "application_id": p["application_id"], "grant_id": None})

    for item in deadline_reminders(user_id):
        days = (item["date"] - today).days
        if 0 <= days <= ATTENTION_WINDOW_DAYS:
            items.append({"urgency": "soon" if days > 0 else "overdue",
                          "title": f"Deadline in {days} day(s) · {item['title']}" if days else
                                   f"Deadline today · {item['title']}",
                          "detail": "A close date from Grants.gov or a due date you entered. Confirm it with the "
                                    "funder before you rely on it.",
                          "action": "Open the application" if item["kind"] != "grants.gov" else "See saved grants",
                          "page": "app_pages/applications.py" if item["kind"] != "grants.gov"
                                  else "app_pages/saved_grants.py",
                          "application_id": item.get("application_id"), "grant_id": None})

    assessed = {a["target"] for a in repo.list_pursuit_assessments(user_id)}
    for g in repo.list_saved_grants(user_id):
        if f"grant:{g['id']}" not in assessed:
            items.append({"urgency": "open", "title": f"Not assessed yet · {g['title']}",
                          "detail": "Should We Pursue? checks eligibility, fit, staff hours, and the budget before "
                                    "you spend time writing.",
                          "action": "Assess it", "page": "app_pages/pursue.py",
                          "application_id": None, "grant_id": g["id"]})

    order = {"overdue": 0, "soon": 1, "open": 2}
    items.sort(key=lambda i: order[i["urgency"]])
    return items[:limit]


def priority_grants(user_id: int, limit: int = 8) -> list[dict]:
    """One row per saved grant: what it is, when it closes, what GrantBridge decided, and the next step."""
    from grantbridge import pursuit

    latest = {}
    for a in repo.list_pursuit_assessments(user_id):
        latest.setdefault(a["target"], a)
    apps = {a["grant_id"]: a for a in repo.list_applications(user_id) if a["grant_id"]}
    rows = []
    for g in repo.list_saved_grants(user_id)[:limit]:
        assessment = latest.get(f"grant:{g['id']}")
        outcome = assessment["payload"]["outcome"] if assessment else None
        app = apps.get(g["id"])
        if outcome is None:
            action = "Assess it"
        elif app is None:
            action = "Start the application"
        else:
            action = "Continue the application"
        rows.append({
            "grant_id": g["id"], "title": g["title"], "funder": g["funder"], "sample": bool(g["is_example"]),
            "deadline": g["deadline"], "assessment": pursuit.OUTCOMES[outcome][0] if outcome else "Not assessed",
            "assessed_on": assessment["created_at"][:10] if assessment else None,
            "action": action, "application_id": app["id"] if app else None,
        })
    return rows


# ---------------------------------------------------------------- the Getting Started walkthrough
# One place that decides what a user has actually done. Every step says how it is checked, and a step GrantBridge
# cannot check honestly reports "not tracked" rather than guessing.

WALKTHROUGH = [
    ("profile", "Set up your nonprofit profile",
     "Every eligibility check and every drafted answer uses only the facts you enter here. Anything you leave "
     "blank is reported as unknown, never guessed.",
     "Open setup", "app_pages/setup.py"),
    ("discover", "Discover grant opportunities",
     "Search practice grants or live federal listings from Grants.gov, and save the ones worth a closer look.",
     "Find grants", "app_pages/find_grants.py"),
    ("evaluate", "Evaluate whether to pursue a grant",
     "Should We Pursue? checks eligibility, mission fit, staff hours, and the budget against rules you can read, "
     "and tells you what still needs confirming.",
     "Assess a grant", "app_pages/pursue.py"),
    ("portfolio", "Prioritize your grant portfolio",
     "With limited hours, some grants have to wait. The Portfolio Strategist schedules the work against the hours "
     "you actually have and explains every deferral.",
     "Prioritize", "app_pages/portfolio.py"),
    ("application", "Build an application and budget",
     "Draft answers from your own facts, review the whole proposal, and build a budget whose arithmetic is done in "
     "code, not by the AI.",
     "Open applications", "app_pages/applications.py"),
    ("timeline", "Plan deadlines and next steps",
     "Turn a deadline into a dated workback plan, tick off milestones, and watch the next steps on your dashboard.",
     "Plan deadlines", "app_pages/applications.py"),
]


def walkthrough_progress(user_id: int) -> list[dict]:
    """For each walkthrough step: whether this account has done it, and the evidence for saying so.

    `state` is "done", "todo", or "untracked" for the one step GrantBridge cannot verify from the records.
    """
    from grantbridge import budget as budgets

    org = repo.get_organization(user_id)
    filled, total, missing = profile_meter(org)
    saved = repo.list_saved_grants(user_id)
    apps = repo.list_applications(user_id)
    assessments = repo.list_pursuit_assessments(user_id)
    capacity = repo.get_capacity_settings(user_id)
    commitments = repo.list_commitments(user_id)
    with_budget = [a for a in apps if budgets.summarize(user_id, a["id"]).lines]
    planned = [a for a in apps if repo.get_timeline(user_id, a["id"])]

    checks = {
        "profile": (not missing, f"{filled} of {total} key profile fields filled in"
                                 + (f" · still blank: {', '.join(missing)}" if missing else "")),
        "discover": (bool(saved), f"{len(saved)} grant(s) saved" if saved else "No grants saved yet"),
        "evaluate": (bool(assessments), f"{len(assessments)} assessment(s) run" if assessments
                     else "No grant assessed yet"),
        "portfolio": (bool(capacity or commitments),
                      "Your weekly hours and priorities are saved" if capacity or commitments
                      else "Your weekly hours have not been set yet"),
        "application": (bool(with_budget), f"{len(apps)} application(s), {len(with_budget)} with budget lines"
                        if apps else "No application started yet"),
        "timeline": (bool(planned), f"{len(planned)} application(s) with a workback plan" if planned
                     else "No workback plan yet"),
    }
    rows = []
    for key, title, blurb, action, page in WALKTHROUGH:
        done, evidence = checks[key]
        rows.append({"key": key, "title": title, "blurb": blurb, "action": action, "page": page,
                     "state": "done" if done else "todo", "evidence": evidence})
    return rows

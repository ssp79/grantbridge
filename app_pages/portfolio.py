"""Portfolio Strategist: which grants to pursue with the hours you have, week by week, and what might pull you off
mission. Code makes every recommendation (portfolio.py); the AI only explains possible mission drift."""

import os
from datetime import date

import altair as alt
import streamlit as st

from grantbridge import components as c
from grantbridge import award_feasibility, mission_drift, portfolio, pursuit, repo, session, timeline, ui
from grantbridge import validation as v
from grantbridge.config import ConfigError, resolve_settings

STATUS_BADGES = {"recommended": ":green-badge[:material/check_circle: Recommended]",
                 "deferred": ":orange-badge[:material/pause_circle: Deferred]",
                 "excluded": ":red-badge[:material/block: Excluded]"}
DRIFT_BADGES = {"low": ":green-badge[:material/check: Low mission-drift concern]",
                "moderate": ":orange-badge[:material/warning: Moderate mission-drift concern]",
                "high": ":red-badge[:material/error: High mission-drift concern]",
                "unknown": ":gray-badge[:material/help: Mission drift unknown]",
                None: ":gray-badge[:material/hourglass_empty: Mission drift not checked]"}
LEVEL_BADGES = {"low": ":green-badge[Low]", "moderate": ":orange-badge[Moderate]", "high": ":red-badge[High]",
                "unknown": ":gray-badge[Unknown]"}
WEEK_STATUS = {"ok": "OK", "full": "Full", "conflict": "Conflict"}
DECISIONS = {"auto": "Let GrantBridge decide", "must": "Must pursue", "skip": "Not interested"}
SOURCE_WORDS = {"grants.gov": "from Grants.gov", "sample": "SAMPLE example date", "user": "entered by you", None: ""}

user = session.require_user()
try:
    resolve_settings()
    key_found = True
except ConfigError:
    key_found = False
default_mock = (not key_found) or os.getenv("GRANTBRIDGE_ADVISOR_MODE", "").strip().lower() == "mock"

c.header("Portfolio Strategist", ":material/insights:",
         "Decide which grants to pursue with the hours you actually have. GrantBridge's code schedules the work week "
         "by week and chooses grants by your priorities; the AI only explains possible mission drift. Amounts are "
         "potential requests, not expected or guaranteed awards.")

with st.container():  # notices: always present, so the tabs below keep their position
    notice = st.session_state.pop("pf_notice", None)
    if notice:
        st.success(notice, icon=":material/check_circle:")
    warning = st.session_state.pop("pf_warning", None)
    if warning:
        st.warning(warning, icon=":material/info:")

# ---------------------------------------------------------------- your numbers (each change recomputes at once)
settings = portfolio.load_settings(user.id)
state = st.session_state
for key in portfolio.candidate_keys(user.id):  # this run's widget values, before the portfolio is computed
    decision = state.get(f"pf_dec_{key}")
    if decision in ("must", "skip"):
        settings["status"][key] = decision
    elif decision == "auto":
        settings["status"].pop(key, None)
    if f"pf_h_{key}" in state:
        if state[f"pf_h_{key}"] is None:
            settings["hours_override"].pop(key, None)
        else:
            settings["hours_override"][key] = state[f"pf_h_{key}"]

with st.container(border=True, key="card-portfolio-settings"):
    st.markdown("##### Your capacity and priorities")
    top = st.columns([2, 3], gap="large")
    with top[0]:
        settings["hours_per_week"] = st.number_input(
            "Staff hours a week for grant work (yours)", min_value=1, max_value=80, step=1,
            value=settings["hours_per_week"], key="pf_hours",
            help="All staff time for grant applications, pooled. GrantBridge spreads it over the five weekdays.")
        settings["exclude_high_drift"] = st.toggle("Exclude grants with a high mission-drift concern",
                                                   value=settings["exclude_high_drift"], key="pf_exclude_drift")
        settings["require_settled"] = st.toggle(
            "Recommend only grants whose eligibility is settled", value=settings["require_settled"],
            key="pf_require_settled", help="Settled: every eligibility item met, or confirmed by you on Should We "
                                           "Pursue?. Off: uncertainty only lowers the score.")
        settings["defer_cash_burden"] = st.toggle(
            "Defer grants that would strain our cash", value=settings["defer_cash_burden"], key="pf_defer_cash",
            help="Uses Can We Afford to Win? on Should We Pursue?. Only a burden worked out from known terms and "
                 "your reserves counts; an unknown term never defers a grant.")
    with top[1]:
        st.markdown("**Your priorities** (0 = ignore, 5 = most important)")
        cols = st.columns(2)
        for i, (key, (label, meaning)) in enumerate(portfolio.COMPONENTS.items()):
            settings["weights"][key] = cols[i % 2].slider(label, 0, 5, value=settings["weights"][key],
                                                          key=f"pf_w_{key}", help=f"Full score: {meaning}.")
    with st.expander("Effort assumptions: hours per step of an application (estimates you can change)",
                     icon=":material/tune:"):
        cols = st.columns(3)
        for i, (key, (label, default, how)) in enumerate(pursuit.EFFORT.items()):
            settings["effort_hours"][key] = cols[i % 3].number_input(
                label, min_value=0, max_value=200, step=1, value=int(settings["effort_hours"].get(key, default)),
                key=f"pf_eh_{key}", help=f"Counted {how}.")
        st.caption("Shared with Should We Pursue?. Your own hour estimate for one grant (on its card) replaces "
                   "these.")
try:
    if settings != portfolio.load_settings(user.id):
        settings = portfolio.save_settings(user.id, settings)
except v.ValidationError as err:
    st.warning(str(err), icon=":material/info:")
    settings = portfolio.load_settings(user.id)

result = portfolio.recommend(user.id, settings)
cands = result["candidates"]

portfolio_tab, capacity_tab, drift_tab, commitments_tab = st.tabs(
    ["Recommended portfolio", "Weekly capacity", "Mission drift", "Commitments"])

# ---------------------------------------------------------------- recommended portfolio
with portfolio_tab:
    if not cands:
        if c.empty_state(":material/bookmarks:", "No grants to compare yet",
                         "Save a few grants on **Find Grants**: the strategist compares saved grants and the grants "
                         "of applications you are researching.", action="Find grants", key="pf-none"):
            st.switch_page("app_pages/find_grants.py")
    else:
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Recommended", result["counts"]["recommended"], border=True)
        m2.metric("Potential requests", f"${result['potential_requested']:,}", border=True,
                  help="The sum of your requests for the recommended grants: potential requests, not expected or "
                       "guaranteed awards.")
        m3.metric("Hours planned", f"{result['planned_hours']:g}", border=True,
                  help="Recommended grants plus your commitments, at your hours a week.")
        m4.metric("Deferred", result["counts"]["deferred"], border=True)
        m5.metric("Excluded", result["counts"]["excluded"], border=True)
        for note in result["notes"]:
            st.warning(ui.md_safe(note), icon=":material/warning:")
        with st.expander("How GrantBridge chooses", icon=":material/rule:"):
            st.markdown(
                "1. **Excluded:** you marked it not interested; it fails a required eligibility check; its deadline "
                "has passed; or it has a high mission-drift concern (if that switch is on).\n"
                "2. **Priority score (0 to 100):** each of the five priorities gives a component from 0 to 1, "
                "weighted by your sliders: "
                + "; ".join(f"{label.lower()} ({settings['weights'][k]})" for k, (label, _) in
                            portfolio.COMPONENTS.items()) + ".\n"
                "3. **Deferred before scheduling:** no deadline; fewer than two days left; eligibility not settled "
                "(if that switch is on); or winning would strain your cash, as worked out by Can We Afford to Win? "
                "from known terms (if that switch is on).\n"
                "4. **Recommended or deferred:** grants you marked *must pursue* go first, then the rest by score. "
                "Each is kept only if every deadline (your commitments and the grants already chosen) can still be "
                "met at your hours a week. That is checked with an earliest-deadline-first schedule, which meets every "
                "deadline whenever any schedule can.\n\n"
                "This is a transparent rule, not a search over every combination, and it uses no award "
                "probabilities. Amounts are potential requests: never expected or guaranteed awards.")
        for cand in cands:
            key = cand["key"]
            with st.container(border=True, key=f"card-pf-{c.slug(key)}"):
                badges = [STATUS_BADGES[cand["status"]],
                          c.SAMPLE_BADGE if cand["sample"] else c.LIVE_BADGE, DRIFT_BADGES[(cand["drift"] or {})
                                                                                           .get("overall")]]
                if cand["decision"] != "auto":
                    badges.append(f":gray-badge[{DECISIONS[cand['decision']]}]")
                st.markdown(" ".join(badges))
                title_col, score_col = st.columns([4, 1], vertical_alignment="center")
                title_col.markdown(f"**{ui.md_safe(cand['title'])}**")
                score_col.markdown(f"**{cand['score']:g}** / 100 priority")
                st.markdown("\n".join(f"- {ui.external_md(r)}" for r in cand["reasons"]))
                deadline = (f"{cand['deadline']} ({SOURCE_WORDS[cand['deadline_source']]})" if cand["deadline"]
                            else "none set")
                request = f"${cand['request']:,}" if cand["request"] else "not set"
                st.caption(f"Deadline {deadline} · Effort {cand['hours']:g} h "
                           f"({'your estimate' if cand['hours_source'] == 'yours' else 'GrantBridge estimate'}) · "
                           f"Potential request {request} ({ui.md_safe(cand['request_note'])}) · Eligibility "
                           f"{cand['eligibility']['settled']} of {cand['eligibility']['total']} settled "
                           f"({cand['eligibility']['source']})")
                afford = cand.get("afford")
                if afford:
                    color = award_feasibility.LEVELS[afford["level"]][1]
                    st.markdown(f":{color}-badge[:material/account_balance_wallet: Can we afford to win? "
                                f"{afford['label']}] {ui.md_safe(afford['reason'])}")
                if cand["strengths"] or cand["weaknesses"]:
                    st.caption(("Helped by: " + ", ".join(cand["strengths"]) if cand["strengths"] else "")
                               + (" · " if cand["strengths"] and cand["weaknesses"] else "")
                               + ("Held back by: " + ", ".join(cand["weaknesses"]) if cand["weaknesses"] else ""))
                with st.expander("Score breakdown", icon=":material/calculate:"):
                    total_weight = sum(settings["weights"].values()) or 1
                    st.markdown("| Priority | Component (0 to 1) | Your weight | Points |\n|---|---:|---:|---:|\n"
                                + "\n".join(f"| {portfolio.COMPONENTS[k][0]} | {value:.2f} | {settings['weights'][k]}"
                                            f" | {100 * settings['weights'][k] * value / total_weight:.1f} |"
                                            for k, value in cand["components"].items())
                                + f"\n| **Total** | | | **{cand['score']:g}** |")
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    st.selectbox("Your decision", list(DECISIONS), format_func=DECISIONS.get, key=f"pf_dec_{key}",
                                 index=list(DECISIONS).index(cand["decision"]))
                    st.number_input("Your hour estimate (blank: GrantBridge's)", min_value=0.0, max_value=500.0,
                                    step=1.0, key=f"pf_h_{key}",
                                    value=settings["hours_override"].get(key))
                    if st.button("Should we pursue?", key=f"pf_pursue_{c.slug(key)}", icon=":material/thumbs_up_down:",
                                 type="tertiary"):
                        st.session_state["pursue_target"] = key
                        st.switch_page("app_pages/pursue.py")

# ---------------------------------------------------------------- weekly capacity
with capacity_tab:
    weeks = result["weeks"]
    if not weeks:
        st.caption(":material/calendar_month: Nothing is scheduled yet: no commitments, and no grant recommended.")
    else:
        rows = [{"Week of": w["week"], "Work": name, "Hours": hours}
                for w in weeks for name, hours in w["per_job"].items()]
        available = [{"Week of": w["week"], "Available hours": w["available"]} for w in weeks]
        bars = alt.Chart(alt.Data(values=rows)).mark_bar().encode(
            x=alt.X("Week of:O", title="Week of"), y=alt.Y("sum(Hours):Q", title="Hours"),
            color=alt.Color("Work:N", title="Work"), tooltip=["Week of:O", "Work:N", "Hours:Q"])
        line = alt.Chart(alt.Data(values=available)).mark_line(point=True, color="#12304A").encode(
            x="Week of:O", y="Available hours:Q", tooltip=["Week of:O", "Available hours:Q"])
        busiest = max(weeks, key=lambda w: w["scheduled"])
        st.altair_chart(bars + line, width="stretch",
                        alt=f"Hours scheduled per week, from {weeks[0]['week']} to {weeks[-1]['week']}, against "
                            f"{settings['hours_per_week']} available hours a week. The busiest week is "
                            f"{busiest['week']} with {busiest['scheduled']:g} hours. The table below lists every week.")
        st.caption("Bars: the work scheduled each week, earliest deadline first. Line: your available hours (the "
                   "current week counts only its remaining weekdays).")
        st.dataframe(
            [{"Week of": w["week"], "Available (yours)": w["available"], "Scheduled": w["scheduled"],
              "Use": f"{100 * w['scheduled'] / w['available']:.0f}%" if w["available"] else "—",
              "Deadlines": ", ".join(w["deadlines"]) or "—",
              "Status": WEEK_STATUS[w["status"]] + ("".join(f": {name} {h:g} h short" for name, h in w["short"].items())
                                                    if w["short"] else "")} for w in weeks],
            hide_index=True, width="stretch")
        st.caption("Full means every available hour is used. Conflict means some work cannot be finished before its "
                   "deadline at your hours a week. Hours per application are estimates unless you entered your own.")

# ---------------------------------------------------------------- mission drift
with drift_tab:
    st.caption("Compares each grant's activities, population, geography, resource demands, and obligations with "
               "your mission, programs, population, and location. The AI's concerns must quote the grant; facts "
               "checked by code (such as eligible states) take precedence. Low, moderate, high, or unknown: this "
               "is a prompt for your own judgment, not a verdict.")
    mock_drift = st.toggle("Practice mode (no AI, free)", value=default_mock, disabled=not key_found, key="pf_mock",
                           help="Practice mode rates only what code can check; the rest stays unknown.")

    def run_drift(grant_id: str, force: bool = False) -> None:
        try:
            out = mission_drift.check(user.id, grant_id, want_mock=mock_drift, force=force)
        except (v.ValidationError, repo.NotFound) as err:
            st.session_state["pf_warning"] = str(err)
            return
        level = mission_drift.LEVEL_WORDS[out.data["overall"]]
        cost = ui.usage_line(out.data.get("usage")) if out.mode == "live" and not out.data.get("reused") else ""
        st.session_state["pf_notice"] = (f"Mission drift for {out.data['title']}: {level}."
                                         + (" Reused the last check: nothing it reads had changed."
                                            if out.data.get("reused") else "") + (f" AI use: {cost}." if cost else ""))
        if out.notice:
            st.session_state["pf_warning"] = out.notice

    unchecked = [cand for cand in cands if cand["drift"] is None]
    if unchecked and st.button(f"Check mission drift for {min(len(unchecked), 5)} unchecked grant(s)",
                               key="pf_drift_all", type="primary", icon=":material/travel_explore:",
                               help="At most five at a time, to stay within the per-minute AI limit."):
        with st.spinner("Checking mission drift…"):
            for cand in unchecked[:5]:
                run_drift(cand["grant_id"])
        st.rerun()
    for cand in cands:
        latest = repo.latest_drift_assessment(user.id, cand["grant_id"])
        with st.container(border=True, key=f"card-drift-{c.slug(cand['key'])}"):
            level = latest["payload"]["overall"] if latest else None
            st.markdown(f"{DRIFT_BADGES[level]} **{ui.md_safe(cand['title'])}**")
            if latest is None:
                st.caption("Not checked yet.")
            else:
                p = latest["payload"]
                st.caption(f"Checked {latest['created_at'].replace('T', ' ')[:16]} UTC · "
                           + ("concerns written by AI (gpt-6-luna), quotes checked by code" if latest["mode"] == "live"
                              else "practice mode: code checks only, no AI"))
                if p["summary"]:
                    st.markdown(ui.md_safe(p["summary"]))
                for concern in p["concerns"]:
                    who = "checked by code" if concern["source"] == "code" else "AI"
                    lines = [f"{LEVEL_BADGES[concern['level']]} **{mission_drift.AREAS[concern['area']]}** _({who})_"]
                    if concern["grant_quote"]:
                        lines.append(f"The grant: “{ui.external_md(concern['grant_quote'])}”")
                    if concern["profile_quote"]:
                        lines.append(f"Your profile: “{ui.external_md(concern['profile_quote'])}”")
                    lines.append(ui.md_safe(concern["explanation"]))
                    if concern["uncertainty"]:
                        lines.append(f"_Uncertain:_ {ui.md_safe(concern['uncertainty'])}")
                    st.markdown("  \n".join(lines))
                if p["unjudged"]:
                    st.caption("Not judged: " + ", ".join(mission_drift.AREAS[a].lower() for a in p["unjudged"]) + ".")
            if st.button("Check again" if latest else "Check mission drift", key=f"pf_drift_{c.slug(cand['key'])}",
                         icon=":material/travel_explore:", type="tertiary"):
                with st.spinner("Checking mission drift…"):
                    run_drift(cand["grant_id"], force=latest is not None)
                st.rerun()

# ---------------------------------------------------------------- commitments
with commitments_tab:
    st.caption("Work that takes the same staff hours. Applications marked **Drafting** count automatically (change "
               "an application's status on its Details tab); add anything else here, such as a report to a funder.")
    drafting_jobs = [j for j in result["commitments"] if j["kind"] == "drafting"]
    if drafting_jobs:
        st.markdown("**Applications you are drafting**\n" + "\n".join(
            f"- {ui.md_safe(j['title'])}: {j['hours']:g} h "
            f"({'your estimate' if j['hours_source'] == 'yours' else 'GrantBridge estimate'}), deadline {j['deadline']}"
            + (f" · :red[{j['short']:g} h short]" if j["short"] else "") for j in drafting_jobs))
    others = repo.list_commitments(user.id)
    st.markdown("**Other commitments (entered by you)**")
    if not others:
        st.caption("None yet.")
    for item in others:
        text_col, remove_col = st.columns([6, 1], vertical_alignment="center")
        text_col.markdown(f"{ui.md_safe(item['title'])} · {item['hours']:g} h · due {item['due_date']}")
        if remove_col.button("Remove", key=f"pf_rm_{item['id']}", type="tertiary", icon=":material/delete:"):
            repo.delete_commitment(user.id, item["id"])
            st.session_state["pf_notice"] = "Commitment removed."
            st.rerun()
    with st.form("pf_add_commitment", clear_on_submit=True):
        a, b, d = st.columns([3, 1, 2])
        title = a.text_input("Commitment", max_chars=120, placeholder="e.g. Final report to a current funder")
        hours = b.number_input("Hours", min_value=0.5, max_value=500.0, value=4.0, step=0.5)
        due = d.date_input("Due", value=None, format="YYYY-MM-DD", min_value=timeline.current_date())
        if st.form_submit_button("Add commitment", icon=":material/add:"):
            try:
                repo.add_commitment(user.id, title, hours, due)
            except v.ValidationError as err:
                st.error(str(err), icon=":material/error:")
            else:
                st.session_state["pf_notice"] = "Commitment added. The schedule includes it now."
                st.rerun()

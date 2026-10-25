"""Should We Pursue? A go/no-go check for one grant: eligibility, fit, readiness, time, budget, and quality.

The outcome is decided by GrantBridge's code from the rules listed on the page (pursuit.RULES). The AI only writes
fit evidence, as exact quotes that code verifies. Nothing on this page predicts whether a grant will be won.
"""

import os

import streamlit as st

from grantbridge import components as c
from grantbridge import grant_search as gs
from grantbridge import award_view, pursuit, repo, session, timeline, trace, ui
from grantbridge import validation as v
from grantbridge.config import ConfigError, resolve_settings

LEVEL_BADGES = {
    "good": ":green-badge[:material/check_circle: Good]",
    "gap": ":orange-badge[:material/construction: Needs work]",
    "unknown": ":gray-badge[:material/help: Unknown]",
    "caution": ":orange-badge[:material/warning: Caution]",
    "blocker": ":red-badge[:material/block: Blocker]",
    "not_assessed": ":gray-badge[:material/hourglass_empty: Not yet assessed]",
}
STATUS_WORDS = {gs.MEETS: ":green[:material/check_circle:] Met", gs.FAILS: ":red[:material/cancel:] Not met",
                gs.UNKNOWN: ":gray[:material/help:] Unknown", "unchecked": ":gray[:material/help:] Not checked by code"}
RULE_TEXT = {rule_id: text for rule_id, _, text in pursuit.RULES}

user = session.require_user()
try:
    resolve_settings()
    key_found = True
except ConfigError:
    key_found = False
default_mock = (not key_found) or os.getenv("GRANTBRIDGE_ADVISOR_MODE", "").strip().lower() == "mock"

c.header("Should We Pursue?", ":material/thumbs_up_down:",
         "A structured go/no-go check for one grant: eligibility, strategic fit, application readiness, time and "
         "capacity, budget, and proposal quality. GrantBridge's code makes the call from the rules shown below. It is "
         "advice for your team's decision, not a prediction of funding.")

# Always present, so the elements below keep their position across reruns.
with st.container():
    notice = st.session_state.pop("pursue_notice", None)
    if notice:
        st.success(notice, icon=":material/check_circle:")
    warning = st.session_state.pop("pursue_warning", None)
    if warning:
        st.warning(warning, icon=":material/info:")

# ---------------------------------------------------------------- what to assess
choices: dict[str, str] = {}
for g in repo.list_saved_grants(user.id):
    choices[f"grant:{g['id']}"] = f"{g['title']} · {'SAMPLE' if g['is_example'] else 'Grants.gov'} · saved"
for a in repo.list_applications(user.id):
    if a["grant_id"]:
        choices.setdefault(f"grant:{a['grant_id']}", f"{a['title']} · your application")
    else:
        choices[f"application:{a['id']}"] = f"{a['title']} · your own application (no listing)"
for g in repo.list_sample_grants():
    choices.setdefault(f"grant:{g['id']}", f"{g['title']} · SAMPLE")
extra = st.session_state.setdefault("pursue_extra", {})  # live grants opened from Find Grants without saving
wanted = st.session_state.pop("pursue_target", None)
if wanted and wanted not in choices and wanted.startswith("grant:"):
    grant = repo.get_grant(wanted.removeprefix("grant:"))
    if grant is not None:
        extra[wanted] = f"{grant['title']} · Grants.gov"
choices.update({k: label for k, label in extra.items() if k not in choices})
if wanted in choices:
    st.session_state["pursue_pick"] = wanted
elif st.session_state.get("pursue_pick") not in choices:
    st.session_state["pursue_pick"] = next(iter(choices))
pick_col, mode_col = st.columns([3, 1], vertical_alignment="bottom")
pick = pick_col.selectbox("Grant or application", list(choices), format_func=choices.get, key="pursue_pick")
mock_on = mode_col.toggle("Practice mode (no AI, free)", value=default_mock, disabled=not key_found,
                          key="pursue_mock", help="The decision is always made by code. Practice mode only skips the "
                                                  "AI's fit evidence.")
kind, _, ident = pick.partition(":")
target_args = {"grant_id": ident} if kind == "grant" else {"application_id": int(ident)}
history = repo.list_pursuit_assessments(user.id, pick)
latest = history[0] if history else None
settings = latest["payload"]["settings"] if latest else {}


def run_assessment(**kwargs) -> None:
    try:
        with st.spinner("Checking eligibility, time, budget, and fit…"):
            out = pursuit.assess(user.id, **target_args, want_mock=mock_on, **kwargs)
    except (v.ValidationError, repo.NotFound) as err:
        st.session_state["pursue_warning"] = str(err)
    else:
        label = pursuit.OUTCOMES[out.data["outcome"]][0]
        cost = ui.usage_line(out.data.get("usage")) if out.mode == "live" and not out.data["fit_reused"] else ""
        st.session_state["pursue_notice"] = (f"Assessment saved: {label}." + (f" AI use: {cost}." if cost else "")
                                             + (" The AI fit evidence was reused: nothing it reads had changed."
                                                if out.data["fit_reused"] else ""))
        if out.notice:
            st.session_state["pursue_warning"] = out.notice
    st.rerun()


# Two questions about the same grant: should we pursue it (eligibility, fit, time), and can we afford to win it
# (cash and staff after an award). The second opens first when a page sends someone here for it.
wanted_tab = st.session_state.pop("pursue_tab", None)
assess_tab, afford_tab = st.tabs(["Should we pursue?", "Can we afford to win?"],
                                 default="Can we afford to win?" if wanted_tab == "afford" else "Should we pursue?")
with afford_tab:
    award_view.render(user, pick, target_args, mock_on)

with assess_tab:
    with st.expander("Effort assumptions: hours per step and your capacity (you can change them)", icon=":material/tune:"):
        hours_now = settings.get("hours") or {k: d for k, (_, d, _) in pursuit.EFFORT.items()}
        with st.form(f"pursue_hours_{pick}", border=False):
            cols = st.columns(3)
            entered = {key: cols[i % 3].number_input(label, min_value=0, max_value=200, step=1,
                                                     value=int(hours_now.get(key, default)), key=f"pursue_h_{pick}_{key}",
                                                     help=f"Counted {how}.")
                       for i, (key, (label, default, how)) in enumerate(pursuit.EFFORT.items())}
            per_week = st.number_input("Staff hours a week you can give this application", min_value=1, max_value=80,
                                       step=1, value=int(settings.get("hours_per_week", pursuit.DEFAULT_HOURS_PER_WEEK)),
                                       key=f"pursue_week_{pick}")
            st.caption("These are GrantBridge's rough assumptions, not a funder's rule. Change them to fit your team.")
            if st.form_submit_button("Save and assess again", icon=":material/restart_alt:"):
                run_assessment(hours=entered, hours_per_week=per_week)

    if st.button("Assess again" if latest else "Assess this grant", type="primary", key=f"pursue_run_{pick}",
                 icon=":material/thumbs_up_down:"):
        run_assessment()

    if latest is None:
        st.caption(":material/info: Not assessed yet. The check takes a few seconds: GrantBridge's code runs every check "
                   "and the decision rules; the AI only adds fit evidence (skipped in practice mode).")
        st.stop()

    # ---------------------------------------------------------------- the result
    p = latest["payload"]
    dims, grant = p["dimensions"], p["grant"]
    label, color, icon = pursuit.OUTCOMES[p["outcome"]]
    deciding = next((r for r, _, _ in pursuit.RULES if r in p["rules_fired"]), None)
    with st.container(border=True, key="card-pursuit-outcome"):
        st.markdown(f"### :{color}[{icon} {label}]")
        st.markdown(f"**Why:** {RULE_TEXT[deciding] if deciding else pursuit.STRONG_RULE}")
        also = [RULE_TEXT[r] for r in p["rules_fired"] if r != deciding]
        if also:
            st.markdown("**Also applies:**\n" + "\n".join(f"- {t}" for t in also))
        source = grant["source"] if grant else "your own application"
        st.caption(f"Assessed {latest['created_at'].replace('T', ' ')[:16]} UTC · {ui.md_safe(source)} · "
                   + ("fit evidence written by AI (gpt-6-luna), checked by code" if latest["mode"] == "live"
                      else "practice mode: no AI was used"))
        st.caption(pursuit.ADVISORY_NOTE)
    if grant and grant["sample"]:
        st.info("This assessment is based on a sample opportunity.", icon=":material/science:")
    if p.get("fetch_error"):
        st.warning(f"Grants.gov could not be checked just now: {ui.md_safe(p['fetch_error'])} Eligibility is unknown "
                   "until it can be.", icon=":material/cloud_off:")
    if dims["time"].get("listing_changed"):
        st.warning(ui.md_safe(dims["time"]["listing_changed"]), icon=":material/update:")

    rows = [list(pursuit.DIMENSIONS.items())[:3], list(pursuit.DIMENSIONS.items())[3:]]
    for row in rows:
        for col, (key, name) in zip(st.columns(3), row):
            with col, st.container(border=True, key=f"card-dimension-{key}", height="stretch"):
                st.markdown(f"**{name}**  \n{LEVEL_BADGES[dims[key]['level']]}")
                st.markdown(ui.external_md(dims[key]["reason"]))

    verified_col, unknown_col = st.columns(2, gap="medium")
    items = dims["eligibility"]["items"]
    with verified_col, st.container(border=True, key="card-pursuit-verified"):
        st.markdown("##### What we verified")
        lines = [f"- {STATUS_WORDS[i['status']]} · **{ui.md_safe(i['name'])}:** {ui.external_md(i['detail'])}"
                 for i in items if i["status"] == gs.MEETS]
        lines += [f"- :blue[:material/how_to_reg:] Confirmed by you on {i['confirmed_on']} · **{ui.md_safe(i['name'])}:** "
                  f"{ui.external_md(i['detail'])}" for i in items if i["confirmed_on"]]
        if dims["time"]["deadline"]:
            lines.append(f"- :material/event: **Deadline {dims['time']['deadline']}:** {ui.md_safe(dims['time']['deadline_note'])}")
        st.markdown("\n".join(lines) if lines else "Nothing could be verified yet.")
        if grant and grant["source_url"]:
            st.markdown(f"[Open the Grants.gov listing]({grant['source_url']})")
        st.caption("Checks compare the grant's listing with your profile, which is self-reported. Only the funder decides "
                   "eligibility.")
    with unknown_col, st.container(border=True, key="card-pursuit-unknown"):
        st.markdown("##### What we still need to know")
        failed = [i for i in items if i["status"] == gs.FAILS]
        if failed:
            st.markdown("**Not met** (fix your profile if it is wrong; a failed check cannot be confirmed away)\n"
                        + "\n".join(f"- **{ui.md_safe(i['name'])}:** {ui.external_md(i['detail'])}" for i in failed))
        confirmable = [i for i in items if i["status"] in (gs.UNKNOWN, "unchecked")]
        if confirmable:
            with st.form(f"pursue_confirm_{latest['id']}", border=False):
                st.markdown("**To confirm.** Check each one against the funder's listing; tick it only once you have.")
                ticked = {i["key"]: st.checkbox(f"{i['name']}: {i['detail']}", value=bool(i["confirmed_on"]),
                                                key=f"pursue_c_{latest['id']}_{i['key']}") for i in confirmable}
                if st.form_submit_button("Save confirmations and assess again", icon=":material/how_to_reg:"):
                    confirmations = {k: d for k, d in settings.get("confirmations", {}).items() if k not in ticked}
                    today = timeline.current_date().isoformat()
                    confirmations.update({k: (settings.get("confirmations", {}).get(k) or today)
                                          for k, on in ticked.items() if on})
                    run_assessment(confirmations=confirmations)
        other = []
        if dims["time"]["deadline"] is None:
            other.append(dims["time"]["reason"])
        missing = repo.missing_profile_fields(repo.get_organization(user.id))
        if missing:
            other.append(f"Profile fields missing: {', '.join(missing)}.")
        if dims["budget"]["level"] == "unknown":
            other.append(dims["budget"]["reason"])
        if other:
            st.markdown("**Also unknown**\n" + "\n".join(f"- {ui.external_md(t)}" for t in other))
        if not (failed or confirmable or other):
            st.markdown("Nothing open.")

    with st.container(border=True, key="card-pursuit-next"):
        st.markdown("##### Top next actions")
        st.markdown("\n".join(f"{n}. {ui.external_md(a)}" for n, a in enumerate(p["next_actions"], 1))
                    or "Nothing urgent. Keep going.")

    effort_col, fit_col = st.columns(2, gap="medium")
    with effort_col, st.container(border=True, key="card-pursuit-effort"):
        t = dims["time"]
        st.markdown("##### Effort breakdown")
        st.markdown("| Step | Count | Hours each | Hours |\n|---|---:|---:|---:|\n"
                    + "\n".join(f"| {line['label']} | {line['count']:g} | {line['hours_each']} | {line['hours']:g} |"
                                for line in p["effort"]["lines"])
                    + f"\n| **Total** | | | **{p['effort']['hours']:g}** |")
        weeks = (f"{t['weeks_needed']:g} weeks at {t['hours_per_week']} hours a week; {t['weeks_left']:g} weeks are left."
                 if t.get("weeks_needed") is not None else f"At {t['hours_per_week']} hours a week.")
        st.caption(f"{weeks} Change the assumptions above to match your team."
                   + (" The question count is assumed: the listing's questions are not in GrantBridge."
                      if dims["readiness"]["questions_assumed"] else ""))
    with fit_col, st.container(border=True, key="card-pursuit-fit"):
        evidence = p["fit_evidence"]
        st.markdown("##### Strategic fit evidence")
        if evidence.get("summary"):
            st.markdown(ui.md_safe(evidence["summary"]))
        for point in evidence.get("points", []):
            st.markdown(f"- Your profile: “{ui.external_md(point['profile_quote'])}”  \n  The grant: "
                        f"“{ui.external_md(point['grant_quote'])}”  \n  {ui.md_safe(point['connection'])}")
        if evidence.get("gaps"):
            st.markdown("**Where the fit is weaker**\n" + "\n".join(f"- {ui.md_safe(g)}" for g in evidence["gaps"]))
        if latest["mode"] == "live":
            st.caption("Quotes are kept only if they appear word for word in your profile and in the grant's text.")

    with st.container(horizontal=True):
        app_id = p["application_id"]
        if grant and st.button("Continue application" if app_id else "Start application", key=f"pursue_apply_{pick}",
                               icon=":material/description:"):
            st.session_state["open_application_id"] = app_id or repo.create_application_from_grant(user.id, grant["id"])
            st.switch_page("app_pages/applications.py")
        if not grant and st.button("Open the application", key=f"pursue_open_{pick}", icon=":material/description:"):
            st.session_state["open_application_id"] = app_id
            st.switch_page("app_pages/applications.py")
        if st.button("Create a workback plan", key=f"pursue_plan_{pick}", icon=":material/event_note:",
                     disabled=app_id is None, help="Start the application first." if app_id is None else
                     "Plans back from the deadline on the application's Timeline tab."):
            try:
                out = timeline.build_plan(user.id, app_id)
            except (v.ValidationError, repo.NotFound) as err:
                st.session_state["pursue_warning"] = str(err)
            else:
                st.session_state["pursue_notice"] = (f"Workback plan saved: {len(out['plan']['milestones'])} steps to "
                                                     f"{out['plan']['deadline']}. See the application's Timeline tab.")
            st.rerun()
        if grant and st.button("Ask the AI Grant Advisor about this grant", key=f"pursue_ask_{pick}",
                               icon=":material/forum:", type="tertiary"):
            st.session_state["advisor_pending"] = (f"What should we check before applying to {grant['title']} "
                                                   f"({grant['id']})?")
            st.switch_page("app_pages/advisor.py")

    with st.expander("Decision rules: how the outcome is decided", icon=":material/rule:"):
        st.markdown("The rules are checked in order, and the first one that applies decides. The AI cannot change them.")
        lines = [f"{n}. **{pursuit.OUTCOMES[outcome][0]}** if: {text}" + (" ← **applies**" if rule_id in p["rules_fired"]
                                                                          else "")
                 for n, (rule_id, outcome, text) in enumerate(pursuit.RULES, 1)]
        lines.append(f"{len(pursuit.RULES) + 1}. **{pursuit.OUTCOMES['strong'][0]}** if: {pursuit.STRONG_RULE}"
                     + (" ← **applies**" if not p["rules_fired"] else ""))
        st.markdown("\n".join(lines))

    with st.expander("Technical details: the assessment's steps, tokens, and cost", icon=":material/terminal:"):
        steps = trace.run_steps(user.id, p["run_id"]) if p.get("run_id") else []
        if steps:
            st.dataframe(ui.trace_rows(steps), hide_index=True, width="stretch")
        usage = p.get("usage") or {}
        st.caption((ui.usage_line(usage) if usage.get("model_calls") else "No AI call in this run.")
                   + " Grants.gov receives only the opportunity id; your profile is never sent there.")
        if len(history) > 1:
            st.markdown("**Earlier assessments of this grant**\n" + "\n".join(
                f"- {h['created_at'].replace('T', ' ')[:16]} UTC · {pursuit.OUTCOMES[h['outcome']][0]}" for h in history[1:]))

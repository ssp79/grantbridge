"""Can We Afford to Win?: the tab of the Should We Pursue? page that checks one grant's award terms against the
organization's own numbers. award_feasibility.py does the work; this module only draws it."""

from __future__ import annotations

import altair as alt
import streamlit as st

from grantbridge import award_feasibility as af
from grantbridge import pursuit, repo, trace, ui
from grantbridge import validation as v

FROM_BADGES = {
    "you": ":blue-badge[your number]", "the grant's terms": ":green-badge[from the terms]",
    "your application": ":blue-badge[your application]", "your profile": ":blue-badge[your profile]",
    "your budget": ":blue-badge[your budget]", "the grant's maximum award": ":gray-badge[the grant's maximum]",
    "calculated": ":gray-badge[calculated]", "assumption": ":orange-badge[assumption]", "unknown": ":gray-badge[unknown]",
}
MODE_WORDS = {"live": "read by AI (gpt-6-luna), every quote checked by code",
              "mock": "found by fixed text patterns (practice mode, no AI)"}


def money(x) -> str:
    return af.usd(x)


def cash_chart(series: list[dict], reserves: float | None, *, scenario: list[dict] | None = None) -> alt.Chart:
    rows = [{"Month": p["month"], "Cash tied up": p["cash_tied_up"], "Case": "Your numbers"} for p in series]
    if scenario:
        rows += [{"Month": p["month"], "Cash tied up": p["cash_tied_up"], "Case": "This scenario"} for p in scenario]
    lines = alt.Chart(alt.Data(values=rows)).mark_line(strokeWidth=2.5).encode(
        x=alt.X("Month:Q", title="Month of the grant"), y=alt.Y("Cash tied up:Q", title="Your cash tied up ($)"),
        color=alt.Color("Case:N", title=None, scale=alt.Scale(range=["#173341", "#287F78"])),
        tooltip=["Case:N", "Month:Q", alt.Tooltip("Cash tied up:Q", format="$,.0f")])
    if reserves:
        rule = alt.Chart(alt.Data(values=[{"Reserves": reserves}])).mark_rule(color="#B42318", strokeDash=[6, 4]).encode(
            y="Reserves:Q", tooltip=[alt.Tooltip("Reserves:Q", format="$,.0f", title="Your reserves")])
        return (lines + rule).properties(height=260)
    return lines.properties(height=260)


def _verdict_block(a: dict) -> None:
    label, color, icon = af.LEVELS[a["verdict"]["level"]]
    st.markdown(f"##### :{color}-badge[{icon} {label}]")
    for reason in a["verdict"]["reasons"]:
        st.markdown(ui.md_safe(reason))


def _metrics(r: dict) -> None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Match you must fund", money(r["match_needed"]),
              help="From the match percent and what it is a percent of. 0 when no match is required.")
    m2.metric("Cash tied up at the worst point", money(r["peak_need"]),
              help="The most of your own cash the project would use at once: the grant's share you have spent but "
                   "not yet been paid, plus your share not covered by committed match money.")
    m3.metric("Payments begin", "at the start" if r["first_payment_day"] == 0 else
              (f"month {r['first_payment_month']:g}" if r["first_payment_month"] is not None else "unknown"))
    m4.metric("Reserves left at the worst point", money(r["reserves_left"]) if r["reserves"] is not None
              else "enter reserves")


def _source_words(source: str) -> str:
    return af.SOURCE_WORDS.get(source, source)


def _terms_tab(a: dict, payload: dict) -> None:
    st.caption(f"Terms {MODE_WORDS.get(payload.get('mode'), '')}. Each quote is word for word from "
               f"{'the grant’s listing or your notice' if payload.get('mode') else 'the text'}; an area nothing "
               "states stays unknown.")
    if payload.get("injection_signals"):
        st.warning("Some of this text contains instructions aimed at AI tools. GrantBridge treated it as data and "
                   "did not take any term from it.", icon=":material/shield:")
    for area, name in af.AREAS.items():
        found = [c for c in a["conditions"] if c["area"] == area]
        with st.container(border=True, key=f"afford-area-{area}"):
            if found:
                st.markdown(f"**{name}** :green-badge[:material/check_circle: stated]")
                for c in found:
                    st.markdown(f"“{ui.external_md(c['quote'])}”")
                    st.caption(f"From {_source_words(c['source'])}"
                               + (f" · {ui.md_safe(c['ambiguity'])}" if c.get("ambiguity") else ""))
            elif area == "match" and a["terms"].get("match_percent"):
                st.markdown(f"**{name}** :green-badge[:material/check_circle: stated]")
                st.markdown(f"“{ui.md_safe(a['terms']['match_percent']['quote'])}”")
                st.caption("From " + _source_words(a["terms"]["match_percent"]["source"]))
            else:
                st.markdown(f"**{name}** :gray-badge[:material/help: unknown]")
                st.caption("Not stated in the text GrantBridge has. Ask the funder; GrantBridge never assumes a "
                           "typical term.")
    listed = a["terms"].get("cost_sharing_listed")
    if listed is True:
        st.caption(":material/public: Grants.gov's own field says this opportunity has a cost-sharing or matching "
                   "requirement. Its amount is not in that field: find it in the notice.")
    elif listed is False:
        st.caption(":material/public: Grants.gov's own field says this opportunity has no cost-sharing requirement.")


def _changed(value, before) -> bool:
    if value is None or before is None:
        return (value is None) != (before is None)
    if isinstance(value, (int, float)) and isinstance(before, (int, float)):
        return abs(float(value) - float(before)) > 1e-9
    return value != before


def _numbers_form(user_id: int, pick: str, a: dict) -> None:
    vals = a["values"]

    def shown(key: str):
        """What the box showed before the user typed: monthly spending is shown in whole dollars."""
        value = vals[key]["value"]
        return round(value) if key == "monthly_spending" and value is not None else value

    st.caption("Every number shows where it came from. Change any of them; organization-wide ones (cash reserves and "
               "your indirect rate) apply to every grant.")
    with st.form(f"afford_numbers_{pick}", border=False):
        entered: dict = {}
        c1, c2, c3 = st.columns(3)
        money_fields = (("award", c1), ("cash_reserves", c2), ("committed_match", c3))
        for key, col in money_fields:
            current = vals[key]["value"]
            entered[key] = col.number_input(f"{af.INPUTS[key][0]}", min_value=0, max_value=1_000_000_000, step=500,
                                            value=None if current is None else int(current), key=f"afford_{pick}_{key}",
                                            help=af.INPUTS[key][1])
            col.markdown(FROM_BADGES.get(vals[key]["from"], ""))
        c1, c2, c3 = st.columns(3)
        payment = list(af.PAYMENT_TYPES)
        entered["payment_type"] = c1.selectbox(af.INPUTS["payment_type"][0], payment,
                                               index=payment.index(vals["payment_type"]["value"]),
                                               format_func=af.PAYMENT_TYPES.get, key=f"afford_{pick}_payment_type",
                                               help=af.INPUTS["payment_type"][1])
        c1.markdown(FROM_BADGES.get(vals["payment_type"]["from"], ""))
        for key, col, lo, hi, step in (("claim_every_months", c2, 1, 12, 1), ("payment_delay_days", c3, 0, 365, 5)):
            entered[key] = col.number_input(af.INPUTS[key][0], min_value=lo, max_value=hi, step=step,
                                            value=int(vals[key]["value"]), key=f"afford_{pick}_{key}",
                                            help=af.INPUTS[key][1])
            col.markdown(FROM_BADGES.get(vals[key]["from"], ""))
        c1, c2, c3 = st.columns(3)
        entered["match_percent"] = c1.number_input(af.INPUTS["match_percent"][0], min_value=0.0, max_value=300.0,
                                                   step=5.0, value=float(vals["match_percent"]["value"]),
                                                   key=f"afford_{pick}_match_percent",
                                                   help=af.INPUTS["match_percent"][1])
        c1.markdown(FROM_BADGES.get(vals["match_percent"]["from"], ""))
        bases = list(af.MATCH_BASES)
        entered["match_basis"] = c2.selectbox(af.INPUTS["match_basis"][0], bases,
                                              index=bases.index(vals["match_basis"]["value"]),
                                              format_func=af.MATCH_BASES.get, key=f"afford_{pick}_match_basis",
                                              help=af.INPUTS["match_basis"][1])
        c2.markdown(FROM_BADGES.get(vals["match_basis"]["from"], ""))
        types = list(af.MATCH_TYPES)
        entered["match_type"] = c3.selectbox(af.INPUTS["match_type"][0], types,
                                             index=types.index(vals["match_type"]["value"]),
                                             format_func=af.MATCH_TYPES.get, key=f"afford_{pick}_match_type",
                                             help=af.INPUTS["match_type"][1])
        c3.markdown(FROM_BADGES.get(vals["match_type"]["from"], ""))
        c1, c2, c3 = st.columns(3)
        entered["period_months"] = c1.number_input(af.INPUTS["period_months"][0], min_value=1, max_value=120, step=1,
                                                   value=int(vals["period_months"]["value"]),
                                                   key=f"afford_{pick}_period_months")
        c1.markdown(FROM_BADGES.get(vals["period_months"]["from"], ""))
        entered["monthly_spending"] = c2.number_input(af.INPUTS["monthly_spending"][0], min_value=0,
                                                      max_value=10_000_000, step=100,
                                                      value=int(round(vals["monthly_spending"]["value"])),
                                                      key=f"afford_{pick}_monthly_spending",
                                                      help=af.INPUTS["monthly_spending"][1])
        c2.markdown(FROM_BADGES.get(vals["monthly_spending"]["from"], ""))
        rate = vals["indirect_rate"]["value"]
        entered["indirect_rate"] = c3.number_input(af.INPUTS["indirect_rate"][0], min_value=0.0, max_value=100.0,
                                                   step=1.0, value=None if rate is None else float(rate),
                                                   key=f"afford_{pick}_indirect_rate",
                                                   help=af.INPUTS["indirect_rate"][1])
        c3.markdown(FROM_BADGES.get(vals["indirect_rate"]["from"], ""))
        if st.form_submit_button("Save my numbers", icon=":material/save:", type="primary"):
            changed = {}
            for key, value in entered.items():
                if key in af.ORG_LEVEL:  # always saved, so a cleared box clears it
                    changed[key] = value
                elif vals[key]["from"] == "you" or _changed(value, shown(key)):
                    changed[key] = value  # only what the user changed becomes "your number"
            try:
                af.save_inputs(user_id, pick, changed)
            except v.ValidationError as err:
                st.session_state["pursue_warning"] = str(err)
            else:
                st.session_state["pursue_notice"] = "Your numbers are saved. The results below use them."
            st.rerun()
    if a["row"]["inputs"] and st.button("Go back to the terms and defaults", key=f"afford_reset_{pick}",
                                        icon=":material/restart_alt:", type="tertiary",
                                        help="Forgets the numbers you entered for this grant (not your reserves)."):
        repo.save_award_feasibility(user_id, pick, inputs={})
        st.rerun()


def _what_if(user_id: int, pick: str, target: pursuit.Target, a: dict) -> None:
    vals = {k: x["value"] for k, x in a["values"].items()}
    st.caption("Try other terms without saving anything. The arithmetic reruns at once; your saved numbers stay as "
               "they are.")
    c1, c2 = st.columns(2)
    delay = c1.slider("Days until a reimbursement claim is paid", 0, 180, int(vals["payment_delay_days"]),
                      step=5, key=f"afford_wi_{pick}_delay")
    award = c2.slider("Award size ($)", 0, max(int(vals["award"] or 0) * 2, 10000), int(vals["award"] or 0),
                      step=1000, key=f"afford_wi_{pick}_award")
    c1, c2 = st.columns(2)
    match = c1.slider("Required match (%)", 0, 95 if vals["match_basis"] == "total_project" else 200,
                      int(min(vals["match_percent"], 95 if vals["match_basis"] == "total_project" else 200)), step=5,
                      key=f"afford_wi_{pick}_match")
    default_spend = int(round(vals["monthly_spending"]))
    spend = c2.slider("Project spending per month ($)", 0, max(default_spend * 2, 1000), default_spend, step=100,
                      key=f"afford_wi_{pick}_spend")
    payment = st.segmented_control("How the award is paid", list(af.PAYMENT_TYPES), format_func=af.PAYMENT_TYPES.get,
                                   default=vals["payment_type"], key=f"afford_wi_{pick}_payment") or vals["payment_type"]
    overrides = {"payment_delay_days": delay, "award": award, "match_percent": match, "payment_type": payment}
    if spend != default_spend:  # untouched, spending follows the scenario's own award and match
        overrides["monthly_spending"] = spend
    if payment in ("advance", "installments"):
        overrides["advance_percent"] = st.slider("Share paid in advance (%)", 0, 100,
                                                 int(vals["advance_percent"] or af.ADVANCE_ASSUMED[payment]), step=5,
                                                 key=f"afford_wi_{pick}_advance")
    try:
        s = af.analysis_for(user_id, target, af.clean_inputs(overrides))
    except v.ValidationError as err:
        st.warning(str(err), icon=":material/info:")
        return
    base, alt_r = a["result"], s["result"]
    label, color, icon = af.LEVELS[s["verdict"]["level"] if s["verdict"]["known"] else
                                   (s["verdict"]["projected"] or "unknown")]
    st.markdown(f"**This scenario:** :{color}-badge[{icon} {label}]")
    cols = st.columns(4)
    for col, (name, key) in zip(cols, (("Match you must fund", "match_needed"),
                                       ("Cash tied up at the worst point", "peak_need"),
                                       ("Reserves left at the worst point", "reserves_left"),
                                       ("Months of operating costs", "months_of_operating_costs"))):
        now, then = base[key], alt_r[key]
        shown = (money(then) if key != "months_of_operating_costs" else (f"{then:g}" if then is not None else "—"))
        delta = None
        if now is not None and then is not None and now != then:
            delta = (f"{then - now:+,.0f}" if key != "months_of_operating_costs" else f"{then - now:+.1f}")
        col.metric(name, shown if then is not None else "—", delta=delta,
                   delta_color="inverse" if key in ("match_needed", "peak_need", "months_of_operating_costs") else "normal")
    st.altair_chart(cash_chart(base["series"], base["reserves"], scenario=alt_r["series"]), width="stretch",
                    alt=f"Cash tied up over the grant, your numbers against this scenario. Your numbers peak at "
                        f"{money(base['peak_need'])}; this scenario peaks at {money(alt_r['peak_need'])}.")
    if not s["verdict"]["known"]:
        st.caption("The scenario's label uses your scenario's terms, which are not settled yet.")


def _explanation(user_id: int, pick: str, target: pursuit.Target, a: dict, mock_on: bool) -> None:
    saved = a["row"].get("explanation") or {}
    current = saved and saved.get("for_hash") == af.explanation_hash(a)
    if saved.get("explanation"):
        badge = (":violet-badge[:material/smart_toy: AI explanation · gpt-6-luna, figures checked by code]"
                 if saved.get("mode") == "live" else ":gray-badge[Practice mode: written by code from the numbers]")
        st.markdown(badge + ("" if current else " :orange-badge[written for earlier numbers]"))
        st.markdown(ui.md_safe(saved["explanation"]))
        if saved.get("tradeoffs"):
            st.markdown("**Options to weigh**\n" + "\n".join(f"- {ui.md_safe(t)}" for t in saved["tradeoffs"]))
        if saved.get("questions_for_funder"):
            st.markdown("**Questions for the funder**\n"
                        + "\n".join(f"- {ui.md_safe(q)}" for q in saved["questions_for_funder"]))
        if saved.get("mode") == "live" and (saved.get("usage") or {}).get("model_calls"):
            st.caption(ui.usage_line(saved["usage"]))
    label = ("Explain these numbers in plain words" + (" (practice rules)" if mock_on else " (AI)"))
    if st.button(label if not current else "Explain again", key=f"afford_explain_{pick}",
                 icon=":material/record_voice_over:"):
        try:
            with st.spinner("Writing a plain-language explanation of the numbers…"):
                out = af.explain(user_id, target, want_mock=mock_on)
        except v.ValidationError as err:
            st.session_state["pursue_warning"] = str(err)
        else:
            if out.notice:
                st.session_state["pursue_warning"] = out.notice
        st.rerun()


def render(user, pick: str, target_args: dict, mock_on: bool) -> None:
    st.markdown("#### :material/account_balance_wallet: Can we afford to win?")
    st.caption("Winning a grant can cost money before it brings any in: a required match, payment only after you "
               "spend, an overhead limit, and reports and staff the award requires. GrantBridge finds those terms and "
               "does the arithmetic against your own numbers. This is about money and staff time, not eligibility or "
               "strategic fit.")
    try:
        target = pursuit.load_target(user.id, **target_args, fetch=False)
    except repo.NotFound as err:
        st.warning(str(err))
        return
    row = repo.get_award_feasibility(user.id, pick) or {}
    demo = af.demo_data()
    with st.expander("The funder's notice or award terms" + (" · added" if row.get("notice") else " (optional)"),
                     icon=":material/description:", expanded=not row.get("terms")):
        st.caption("GrantBridge reads the grant's listing. Award terms such as match and payment rules are often only "
                   "in the full notice or agreement: copy them from it and paste them here. They stay in your account. "
                   "(To read a solicitation from a file instead, start one on the Applications page.)")
        text = st.text_area("Notice or award terms", value=row.get("notice", ""), height=180,
                            max_chars=repo.MAX_NOTICE_CHARS, key=f"afford_notice_{pick}",
                            placeholder="Paste the payment, matching, cost, reporting, and staffing terms here.")
        cols = st.columns([2, 3]) if pick == f"grant:{demo['grant_id']}" else [st.container(), None]
        if cols[0].button("Find the award terms" + (" (practice patterns)" if mock_on else " (AI)"),
                          key=f"afford_find_{pick}", type="primary", icon=":material/search:"):
            _find(user.id, target_args, text, "Notice you added", mock_on)
        if cols[1] is not None and cols[1].button("Use the SAMPLE award terms", key=f"afford_demo_{pick}",
                                                  icon=":material/science:",
                                                  help="Sample terms written for this SAMPLE grant, to see how a "
                                                       "grant that fits can still strain a small budget."):
            _find(user.id, target_args, demo["notice"], demo["notice_name"], mock_on)
    if not row.get("terms"):
        st.info("No award terms found yet. Press **Find the award terms**: GrantBridge reads the listing (and your "
                "notice, if you add one), then compares the terms with your numbers.", icon=":material/info:")
        return
    a = af.analysis_for(user.id, target)
    payload = row["terms"]
    summary_tab, terms_tab, numbers_tab, what_if_tab = st.tabs(["Summary", "Terms found", "Your numbers", "What if"])
    with summary_tab:
        with st.container(border=True, key="card-afford-summary"):
            _verdict_block(a)
            _metrics(a["result"])
            st.altair_chart(cash_chart(a["result"]["series"], a["result"]["reserves"]), width="stretch",
                            alt=f"Your cash tied up over the grant, by month. It peaks at "
                                f"{money(a['result']['peak_need'])} around month {a['result']['peak_month']:g}"
                                + (f", against {money(a['result']['reserves'])} of reserves (the dashed line)."
                                   if a["result"]["reserves"] else "."))
            st.caption("The line: your own cash tied up by the project on each day. The dashed line: your reserves.")
            st.markdown("\n".join(f"- {ui.md_safe(line)}" for line in a["summary"]))
        with st.container(border=True, key="card-afford-explanation"):
            _explanation(user.id, pick, target, a, mock_on)
        st.caption(af.LIMITS)
    with terms_tab:
        _terms_tab(a, payload)
        steps = trace.run_steps(user.id, payload["run_id"]) if payload.get("run_id") else []
        if payload.get("mode") == "live" and (payload.get("usage") or {}).get("model_calls"):
            st.caption(ui.usage_line(payload["usage"]))
        if steps:
            with st.expander("Technical details: the steps that found these terms", icon=":material/terminal:"):
                st.dataframe(ui.trace_rows(steps), hide_index=True, width="stretch")
    with numbers_tab:
        _numbers_form(user.id, pick, a)
    with what_if_tab, st.container(key="afford-what-if"):
        _what_if(user.id, pick, target, a)


def _find(user_id: int, target_args: dict, notice: str, name: str, mock_on: bool) -> None:
    try:
        with st.spinner("Reading the award terms…"):
            out = af.find_terms(user_id, **target_args, notice=notice, notice_name=name, want_mock=mock_on)
    except (v.ValidationError, repo.NotFound) as err:
        st.session_state["pursue_warning"] = str(err)
    else:
        kept = sum(1 for c in out.data["conditions"])
        cost = ui.usage_line(out.data.get("usage")) if out.mode == "live" and not out.data.get("reused") else ""
        st.session_state["pursue_notice"] = (
            f"Award terms saved: {kept} condition(s) found, each quoted from the text."
            + (" Nothing changed, so the saved terms were reused." if out.data.get("reused") else "")
            + (f" AI use: {cost}." if cost else ""))
        if out.notice:
            st.session_state["pursue_warning"] = out.notice
    st.rerun()

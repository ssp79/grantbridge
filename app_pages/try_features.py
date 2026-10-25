"""Try Features — the public, interactive demonstration.

Every panel runs GrantBridge's real code in memory on sample data: the pursuit rules (`pursuit.example`), the
cash-flow arithmetic (`award_feasibility.demo`), and the workback scheduler (`timeline.schedule`). No account, no
database write, no AI call, and nothing a visitor changes here is saved anywhere.
"""

from datetime import timedelta

import streamlit as st

from grantbridge import award_feasibility as af
from grantbridge import award_view, public, pursuit, session, timeline, ui

user = session.current_user()
LEVEL_WORDS = {"good": ":green[:material/check_circle:] Good", "gap": ":orange[:material/construction:] Needs work",
               "unknown": ":gray[:material/help:] Unknown", "caution": ":orange[:material/warning:] Caution",
               "blocker": ":red[:material/block:] Blocker",
               "not_assessed": ":gray[:material/hourglass_empty:] Not yet assessed"}
# Three SAMPLE grants the same rules judge differently, so a visitor can see the reasoning change.
CHOICES = {"sample-05": "New England Youth Opportunity Fund", "sample-08": "Family Engagement in Education Grant",
           "sample-07": "Workforce Bridge Training Grant"}
HOW = [
    (":material/travel_explore:", "It finds opportunities",
     "Ten sample practice listings for learning the tool, plus live federal grants from Grants.gov, each "
     "labelled with where it came from."),
    (":material/rule:", "It decides by rules you can read",
     "Eligibility, fit, staff hours and cash are checked against explicit criteria. Anything nobody knows is "
     "marked unknown rather than guessed either way."),
    (":material/edit_note:", "It drafts from your evidence",
     "Explanations and draft answers are built from your own records. Figures they do not support are flagged "
     "for you rather than invented."),
]

with public.shell("try-features"):
    public.eyebrow("try", "Try it yourself, no account needed")
    st.title("See it decide: a working example you can change", anchor=False)
    public.lede("GrantBridge helps a small nonprofit answer one question before it spends a fortnight writing: "
                "is this grant worth our time, and could we afford to win it?")

    for col, (icon, name, text) in zip(st.columns(3, gap="large"), HOW):
        with col:
            st.markdown(f"### {icon}")
            st.markdown(f"**{name}**")
            st.caption(text)

    st.space("small")
    st.markdown("Three of those checks are below, set up for a sample organization. **Change anything you "
                "like** — pick a different opportunity, move a slider, flip a switch — and the recommendation is "
                "worked out again from scratch.")

    with st.container(border=True, key="about-demo"):
        st.markdown(":orange-badge[:material/science: SAMPLE DATA] Harbor Lantern Tutoring Collective, a "
                    "sample organization, with sample opportunities. Worked out live as you change the inputs.")
        with st.container(key="about-demo-pick"):
            st.markdown(":material/ads_click: **Pick a question:**")
        pursue_tab, afford_tab, plan_tab = st.tabs(["Should we pursue it?", "Can we afford to win it?",
                                                    "How long will it take?"])

        # ------------------------------------------------------------ 1. the go/no-go rules, on a grant you choose
        with pursue_tab:
            with st.container(key="about-move-pursue"):
                st.markdown(":material/ads_click: Choose a grant, then move the switch:")
            picked = st.segmented_control("Which sample grant?", list(CHOICES), format_func=CHOICES.get,
                                          default="sample-05", key="about_demo_grant") or "sample-05"
            example = pursuit.example(grant_id=picked)
            confirmed = st.toggle(f"Confirm the {example['after_confirming']['confirmed']} listing rules that code "
                                  "cannot check", key="about_demo_confirm")
            outcome = example["after_confirming"]["outcome"] if confirmed else example["outcome"]
            label, color, icon = pursuit.OUTCOMES[outcome]
            st.markdown(f"#### :{color}[{icon} {label}]")
            fired = example["after_confirming"]["rules_fired"] if confirmed else example["rules_fired"]
            rule = next((text for rule_id, _, text in pursuit.RULES if rule_id in fired), pursuit.STRONG_RULE)
            st.markdown(f"**Why:** {rule}")
            for row in (list(pursuit.DIMENSIONS.items())[:3], list(pursuit.DIMENSIONS.items())[3:]):
                for col, (key, name) in zip(st.columns(3), row):
                    with col:
                        level = "good" if confirmed and key == "eligibility" else example["dimensions"][key]["level"]
                        st.markdown(f"**{name}**  \n{LEVEL_WORDS[level]}")
                        st.caption(ui.external_md(example["dimensions"][key]["reason"]) if not (
                            confirmed and key == "eligibility") else "Every check is met or confirmed by you.")
            after = pursuit.OUTCOMES[example["after_confirming"]["outcome"]][0]
            st.caption(f"Confirming the {example['after_confirming']['confirmed']} listing rules that code cannot "
                       f"check gives: {after}. A failed required rule cannot be confirmed away, and the AI never "
                       "decides the outcome; it only adds fit evidence.")

        # ------------------------------------------------------------ 2. what winning would cost before it pays
        with afford_tab:
            st.caption("A sample award paid only by reimbursement, with a cash match of 50% of the total "
                       "project cost — the kind of terms that decide whether an organization can carry a grant.")
            with st.container(key="about-move-afford"):
                st.markdown(":material/drag_pan: Drag these, and watch the numbers below change:")
            c1, c2 = st.columns(2)
            delay = c1.slider("Days until each reimbursement is paid", 0, 180, 90, step=15, key="about_demo_delay")
            match = c2.slider("Required match (% of the total project cost)", 0, 60, 50, step=5,
                              key="about_demo_match")
            paid = st.segmented_control("How the award is paid", ["reimbursement", "installments"],
                                        format_func=af.PAYMENT_TYPES.get, default="reimbursement",
                                        key="about_demo_payment") or "reimbursement"
            d = af.demo({"payment_delay_days": delay, "match_percent": match, "payment_type": paid,
                         **({"advance_percent": 50} if paid == "installments" else {})})
            r = d["result"]
            level, color, icon = af.LEVELS[d["verdict"]["level"]]
            st.markdown(f"#### :{color}[{icon} {level}]")
            m1, m2, m3 = st.columns(3)
            m1.metric("Match to fund", af.usd(r["match_needed"]))
            m2.metric("Cash tied up at the worst point", af.usd(r["peak_need"]))
            m3.metric("Sample reserves", af.usd(r["reserves"]))
            st.altair_chart(award_view.cash_chart(r["series"], r["reserves"]), width="stretch",
                            alt=f"The sample organization's cash tied up by the grant, by month: it peaks at "
                                f"{af.usd(r['peak_need'])} around month {r['peak_month']:g}, against "
                                f"{af.usd(r['reserves'])} of reserves.")
            st.markdown(ui.md_safe(d["verdict"]["reasons"][0]))
            st.caption(ui.md_safe(f"Award {af.usd(r['award'])} over {r['months']:g} months · "
                                  f"{af.usd(r['committed_match'])} of match already committed · all figures "
                                  "sample. Financial feasibility is not eligibility or fit."))

        # ------------------------------------------------------------ 3. the workback plan, squeezed by the clock
        with plan_tab:
            st.caption("GrantBridge turns a deadline into a dated plan and shrinks it when time is short, so you "
                       "can see before you start whether the work actually fits. Code only, no AI.")
            with st.container(key="about-move-plan"):
                st.markdown(":material/drag_pan: Drag the deadline closer, and watch the plan tighten:")
            days_left = st.slider("Days until the funder's deadline", 7, 120, 60, step=1, key="about_demo_days")
            today = timeline.current_date()
            dated, meta = timeline.schedule(today + timedelta(days=days_left), today,
                                            timeline.clean_days(None), timeline.DEFAULT_SUBMIT_EARLY)
            squeezed = meta["work_days"] < meta["default_work_days"]
            if meta["work_days"] < meta["default_work_days"] * timeline.SQUEEZE_WARNING:
                st.markdown("#### :red[:material/error: Not enough time for this plan]")
            elif squeezed:
                st.markdown("#### :orange[:material/warning: The plan is tight]")
            else:
                st.markdown("#### :green[:material/check_circle: There is time to do this properly]")
            st.markdown(f"The seven steps normally need **{meta['default_work_days']} days** of working time. With "
                        f"**{days_left} days** until the deadline, GrantBridge fits them into "
                        f"**{meta['work_days']} days**"
                        + (f", submitting {meta['submit_early']} day(s) early." if meta["submit_early"]
                           else ", with no margin before the deadline."))
            st.dataframe([{"Step": timeline.STEPS[key][0], "Due": due.strftime("%b %d, %Y"),
                           "What it covers": timeline.STEPS[key][2]} for key, due in dated],
                         hide_index=True, width="stretch")
            st.caption("Dates run from today here. In the application the plan is built from the funder's own "
                       "deadline, every date shows where it came from, and the whole plan exports to your "
                       "calendar.")

    st.space("medium")
    st.caption("Sample opportunities are used throughout this demonstration and are not real funding programmes. "
               "Nothing you change here is saved.")

    public.closing(user, "try", "Run this on your own organization",
                   "Create your nonprofit profile and assess real opportunities against your own capacity and "
                   "finances.",
                   secondary=("See how it works", public.HOW_IT_WORKS))

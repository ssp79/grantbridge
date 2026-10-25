"""Getting Started — the six steps of GrantBridge, revisitable at any time.

A guide, not a gate. It reuses the setup flow's own progress (`components.walkthrough_progress`), so what it marks
as done is read from this account's records rather than from anything it remembers being clicked. Opening it never
changes the profile, and no step has to be repeated.
"""

import streamlit as st

from grantbridge import components as c
from grantbridge import demo, public, repo, session, ui

user = session.require_user()
steps = c.walkthrough_progress(user.id)
done = [s for s in steps if s["state"] == "done"]
nxt = next((s for s in steps if s["state"] != "done"), None)

DETAIL = {
    "profile": "Three short steps collect your name and state, your mission and programs, and the size of grant you "
               "look for. Each step saves as you finish it, so you can stop and come back. Skipping a field is "
               "allowed: checks that need it will say **Unknown** rather than assume an answer.",
    "discover": "**Practice grants** are ten sample listings for learning the tool; their funders, amounts, and "
                "deadlines are illustrative. **Real federal grants** come from the Grants.gov "
                "API, and each one shows when GrantBridge copied it. Save anything worth a closer look: saving is "
                "what puts a grant into your pipeline, your portfolio, and this walkthrough's progress.",
    "evaluate": "Pick a saved grant and press **Assess this grant**. GrantBridge rates six dimensions — eligibility, "
                "strategic fit, application readiness, time and capacity, budget feasibility, and proposal quality — "
                "and then a short list of rules, printed on the page, decides one of four outcomes. The AI only adds "
                "quoted fit evidence; it cannot change the outcome. The second tab, **Can we afford to win?**, works "
                "out what winning would cost you in cash before the grant pays.",
    "portfolio": "Set the hours your team can really give each week. The Portfolio Strategist schedules every saved "
                 "grant's work backwards from its deadline, keeps the ones that fit, and says in hours and dates why "
                 "it deferred the rest. The **Weekly capacity** tab shows the same plan week by week, and **Mission "
                 "drift** flags grants that would pull you away from your stated mission.",
    "application": "Start an application from any saved grant. For each question you can gather facts, ask for a "
                   "draft built only from those facts, and review what you wrote. Gaps appear as `[NEEDS: …]` and "
                   "unsupported figures as `[VERIFY]`, never as invented text. The **Budget & narrative** tab adds "
                   "the numbers in Python and writes the narrative from your lines only.",
    "timeline": "The **Timeline** tab turns a deadline into a seven-step workback plan fitted to the time left, with "
                "a calendar file you can download. Milestones you have not ticked off appear on your dashboard under "
                "**Next steps**, and anything late shows up under **What needs your attention**.",
}
PREVIEW_FOR = "evaluate"  # one real screenshot, on the step it illustrates

c.header("Getting Started", ":material/school:",
         "The six steps of a grant, in order, with a link into each one. Come back whenever you like — nothing here "
         "repeats work you have already done.")

notice = st.session_state.pop("walkthrough_notice", None)
if notice:
    st.success(notice, icon=":material/check_circle:")

# ---------------------------------------------------------------- progress, and the way back in
top = st.columns([3, 2], gap="large", vertical_alignment="center")
with top[0]:
    st.progress(len(done) / len(steps), text=f"{len(done)} of {len(steps)} steps done in this account")
    st.caption("Each step is marked done only when GrantBridge can see it in your own records. The reason is listed "
               "under every step.")
with top[1]:
    if nxt:
        if st.button(f"Resume: {nxt['title'].lower()}", type="primary", icon=":material/play_arrow:",
                     key="walkthrough_resume", width="stretch"):
            st.switch_page(nxt["page"])
    else:
        st.success("Every step is done. Revisit any of them below.", icon=":material/check_circle:")

st.space("small")

# ---------------------------------------------------------------- the six steps
for n, step in enumerate(steps, 1):
    mark = (":green-badge[:material/check_circle: Done]" if step["state"] == "done"
            else ":gray-badge[:material/radio_button_unchecked: Not yet]")
    with st.container(key=f"walk-step-{step['key']}"):
        head = st.columns([4, 1.15], vertical_alignment="center")
        with head[0]:
            st.markdown(f"**{n}. {step['title']}** {mark}")
            st.markdown(step["blurb"])
            st.caption(f":material/fact_check: {step['evidence']}")
        if head[1].button(step["action"], key=f"walk_go_{step['key']}", icon=":material/arrow_forward:",
                          type="primary" if step is nxt else "secondary", width="stretch"):
            st.switch_page(step["page"])
        with st.expander("How this works in detail"):
            st.markdown(DETAIL[step["key"]])
            if step["key"] == PREVIEW_FOR and public.PREVIEW.exists():
                st.image(str(public.PREVIEW), alt=public.PREVIEW_ALT, width="stretch")
                st.caption("A real GrantBridge screen, with the sample organization's data.")
        st.divider()

# ---------------------------------------------------------------- sample data, kept separable
with st.container(border=True, key="card-walk-demo"):
    if demo.demo_loaded(user.id):
        st.markdown("**The sample data is loaded.** Harbor Lantern Tutoring Collective, two saved SAMPLE "
                    "grants, and one application — enough to try every step above.")
        st.caption("Removing it puts your own profile back as it was and takes out only what the demo added.")
        if st.button("Remove the sample data", icon=":material/delete_sweep:", key="walk_demo_remove"):
            removed = demo.remove_demo_data(user.id)
            st.session_state["walkthrough_notice"] = (
                f"Removed the sample data: {removed['grants']} saved grant(s) and "
                f"{removed['applications']} application(s)"
                + (", and your profile is back as it was." if removed["profile_restored"] else "."))
            st.rerun()
    else:
        st.markdown("**Would you rather follow the steps with ready-made data?** Load a sample "
                    "youth-tutoring nonprofit with two saved SAMPLE grants and one application.")
        replaces = demo.would_replace(user.id)
        if replaces:
            st.warning("This would replace " + ", and ".join(replaces)
                       + ". GrantBridge keeps a copy, so you can put it back with one button.",
                       icon=":material/warning:")
        if st.button("Try with sample data", icon=":material/dataset:", key="walk_demo_load"):
            demo.load_demo_data(user.id)
            st.session_state["walkthrough_notice"] = (
                "Sample demo data loaded. Work through the steps above with it, and remove it again here "
                "whenever you like.")
            st.rerun()
    st.caption("Everything in the demo is invented for practice. SAMPLE grants are never real opportunities.")

"""Set up your organization — a short, skippable first run.

Three steps, each saved as it is submitted, so a visitor can leave at any point and come back to exactly where they
stopped. It asks only for the facts GrantBridge actually uses to find and check grants (repo.KEY_PROFILE_FIELDS);
everything else stays on the Organization Profile page.

Nothing here is required: "Skip for now" leaves the account as it is, and the Dashboard keeps offering to finish.
"""

import streamlit as st

from grantbridge import components as c
from grantbridge import demo, repo, session
from grantbridge import validation as v

user = session.require_user()
org = repo.get_organization(user.id) or {}
DASHBOARD = "app_pages/dashboard.py"

STEPS = [
    ("Your organization", "Who you are, and where you work. Funders screen on these first."),
    ("What you do", "Your mission, the people you serve, and your programs. These decide which grants fit."),
    ("What you are looking for", "The size of grant you want, and the results you can point to."),
]


def _state_options() -> list[str]:
    return [""] + sorted(v.US_STATES, key=v.US_STATES.get)


def _index(options: list[str], value) -> int:
    return options.index(value) if value in options else 0


def save(fields: dict, step: int) -> None:
    """Save one step onto the existing profile, then move on. Only the fields on this step are touched."""
    try:
        repo.save_organization(user.id, {**{k: org.get(k) for k in repo.PROFILE_FIELDS}, **fields})
    except v.ValidationError as err:
        st.session_state["setup_warning"] = str(err)
        return
    st.session_state["setup_step"] = step + 1
    st.rerun()


filled, total, missing = c.profile_meter(org)
step = int(st.session_state.get("setup_step", 0))
done = step >= len(STEPS)

c.header("Set up your organization", ":material/rocket_launch:",
         "GrantBridge checks every grant against these facts. It takes about three minutes, you can skip any part, "
         "and nothing is shared with funders.")

warning = st.session_state.pop("setup_warning", None)
if warning:
    st.warning(warning, icon=":material/info:")

st.progress(filled / total, text=f"Profile completeness: {filled} of {total} key fields"
            + (f" · still missing: {', '.join(missing)}" if missing else " · complete"))

if done:
    with st.container(border=True, key="card-setup-done"):
        st.markdown("#### :material/check_circle: That is everything GrantBridge needs to start")
        if missing:
            st.markdown("You skipped some fields. Checks that depend on them will say **Unknown** rather than guess, "
                        "and you can fill them in at any time on the Organization Profile page.")
            st.caption("Still blank: " + ", ".join(missing))
        else:
            st.markdown("Every key field is filled in. Next: find grants that fit, and check one before you write "
                        "anything.")
        with st.container(horizontal=True, key="setup-done-actions"):
            if st.button("Find funding", type="primary", icon=":material/travel_explore:", key="setup_find"):
                st.session_state.pop("setup_step", None)
                st.switch_page("app_pages/find_grants.py")
            if st.button("Go to the dashboard", icon=":material/space_dashboard:", key="setup_dash"):
                st.session_state.pop("setup_step", None)
                st.switch_page(DASHBOARD)
            if st.button("Edit the full profile", icon=":material/apartment:", key="setup_profile"):
                st.session_state.pop("setup_step", None)
                st.switch_page("app_pages/profile.py")
    st.stop()

title, blurb = STEPS[step]
with st.container(key="setup-steps"):
    for i, (name, _) in enumerate(STEPS):
        mark = ":green-badge[:material/check: Done]" if i < step else (
            ":blue-badge[:material/edit: Now]" if i == step else ":gray-badge[:material/schedule: Next]")
        st.markdown(f"{mark} **{i + 1}. {name}**")

with st.container(border=True, key=f"card-setup-{step}"):
    st.subheader(f"Step {step + 1} of {len(STEPS)}: {title}", anchor=False)
    st.caption(blurb)

    if step == 0:
        with st.form("setup_0", clear_on_submit=False, border=False):
            name = st.text_input("Organization name *", value=org.get("name", ""), max_chars=200)
            cols = st.columns(2)
            states = _state_options()
            state = cols[0].selectbox("State", states, index=_index(states, org.get("state", "")),
                                      format_func=lambda s: v.US_STATES.get(s, "Choose a state"),
                                      help="Many grants are limited to one state or region.")
            tax = [""] + v.TAX_STATUSES
            tax_status = cols[1].selectbox("501(c)(3) status (self-reported)", tax,
                                           index=_index(tax, org.get("tax_status", "")),
                                           format_func=lambda s: s or "Choose one",
                                           help="GrantBridge does not verify this with the IRS. Funders will.")
            if st.form_submit_button("Save and continue", type="primary", icon=":material/arrow_forward:"):
                save({"name": name, "state": state, "tax_status": tax_status}, step)

    elif step == 1:
        with st.form("setup_1", clear_on_submit=False, border=False):
            mission = st.text_area("Mission", value=org.get("mission", ""), max_chars=1500, height=90,
                                   placeholder="In one or two sentences, what your organization exists to do.")
            population = st.text_area("Populations served", value=org.get("population_served", ""), max_chars=1500,
                                      height=70, placeholder="Who you serve, and roughly how many.")
            programs = st.text_area("Programs", value=org.get("programs", ""), max_chars=3000, height=70,
                                    placeholder="Your main programs or services.")
            focus = st.multiselect("Focus areas", v.FOCUS_AREAS, default=org.get("focus_areas", []),
                                   help="Used to match you with grants in the same field.")
            if st.form_submit_button("Save and continue", type="primary", icon=":material/arrow_forward:"):
                save({"mission": mission, "population_served": population, "programs": programs,
                      "focus_areas": focus}, step)

    else:
        with st.form("setup_2", clear_on_submit=False, border=False):
            cols = st.columns(2)
            requested = cols[0].number_input("Typical funding request ($)", min_value=0, max_value=100_000_000,
                                             value=org.get("requested_amount") or 0, step=1000,
                                             help="Roughly what you would ask one funder for. Used to flag grants "
                                                  "whose award range does not fit.")
            budget = cols[1].number_input("Annual budget ($)", min_value=0, max_value=1_000_000_000,
                                          value=org.get("annual_budget") or 0, step=1000,
                                          help="Optional. Used to judge whether a grant is large for your "
                                               "organization, and what winning it would mean for your cash.")
            track = st.text_area("Track record and outcomes", value=org.get("track_record", ""), max_chars=3000,
                                 height=90, placeholder="Results you can evidence: numbers served, outcomes "
                                                        "measured, past grants delivered.",
                                 help="Drafts quote only facts you have entered. Anything missing is marked for "
                                      "you to fill in, never invented.")
            if st.form_submit_button("Finish setup", type="primary", icon=":material/check:"):
                save({"requested_amount": requested or None, "annual_budget": budget or None,
                      "track_record": track}, step)

with st.container(horizontal=True, key="setup-nav"):
    if step > 0 and st.button("Back", icon=":material/arrow_back:", key="setup_back"):
        st.session_state["setup_step"] = step - 1
        st.rerun()
    if st.button("Skip this step", key="setup_skip_step"):
        st.session_state["setup_step"] = step + 1
        st.rerun()
    if st.button("Skip for now", key="setup_skip_all",
                 help="Leaves your profile as it is. The Dashboard will offer to finish whenever you like."):
        st.session_state.pop("setup_step", None)
        st.switch_page(DASHBOARD)

# ---------------------------------------------------------------- exploring with sample data instead
st.space("small")
with st.container(border=True, key="card-setup-demo"):
    loaded = demo.demo_loaded(user.id)
    st.markdown("**Would you rather look around first?**")
    if loaded:
        st.markdown("The sample data is loaded: Harbor Lantern Tutoring Collective, two saved SAMPLE grants, "
                    "and one application. Remove it whenever you like — GrantBridge put your own profile back the "
                    "way it was.")
        if st.button("Remove the sample data", icon=":material/delete_sweep:", key="setup_demo_remove"):
            removed = demo.remove_demo_data(user.id)
            st.session_state["setup_warning"] = (
                f"Removed the sample data: {removed['grants']} saved grant(s) and "
                f"{removed['applications']} application(s)"
                + (", and your profile is back as it was." if removed["profile_restored"] else "."))
            st.rerun()
    else:
        st.caption("The sample organization happens to be in Connecticut; that is only an example. Every eligibility check runs against **your** state and your profile, and Find Grants searches federal opportunities nationwide.")
        st.markdown("Load a sample youth-tutoring nonprofit with two saved SAMPLE grants and one "
                    "application, and explore every feature with it.")
        replaces = demo.would_replace(user.id)
        if replaces:
            st.warning("This would replace " + ", and ".join(replaces)
                       + ". GrantBridge keeps a copy, so you can put it back with one button.",
                       icon=":material/warning:")
        if st.button("Explore with sample data", icon=":material/dataset:", key="setup_demo_load"):
            demo.load_demo_data(user.id)
            st.session_state["dashboard_notice"] = (
                "Sample demo data loaded: Harbor Lantern Tutoring Collective, two saved SAMPLE grants, and one "
                "application. You can remove it again from Set up or the Organization Profile page.")
            st.session_state.pop("setup_step", None)
            st.switch_page(DASHBOARD)
    st.caption("Everything in the demo is invented for practice. Sample grants are never real opportunities.")

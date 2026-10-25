"""Organization Profile — the facts every eligibility check and draft is grounded in."""

import streamlit as st

from grantbridge import components as c
from grantbridge import demo, repo, session, validation as v

user = session.require_user()
org = repo.get_organization(user.id) or {}

c.header("Organization Profile", ":material/apartment:",
         "GrantBridge uses only these facts when it checks eligibility and drafts answers. Anything left blank is "
         "flagged as a gap instead of being guessed. Everything here is self-reported: funders verify it.")

notice = st.session_state.pop("profile_notice", None)
if notice:
    st.success(notice, icon=":material/check_circle:")

filled, total, missing = c.profile_meter(org)
status_col, demo_col = st.columns([3, 2], gap="medium")
with status_col.container(border=True, key="card-profile-status", height="stretch"):
    st.progress(filled / total, text=f"Profile completeness: {filled} of {total} key fields")
    if missing:
        st.caption("Still missing: " + ", ".join(missing) + ". Checks show **Unknown** until you add them.")
    else:
        st.caption("Every key field is filled in. Keep them current: funders check them.")
with demo_col.container(border=True, key="card-profile-demo", height="stretch"):
    if demo.demo_loaded(user.id):
        st.markdown("**The sample data is loaded.** Harbor Lantern Tutoring Collective, two saved SAMPLE "
                    "grants, and one application.")
        st.caption("Removing it puts your own profile back as it was and takes out only what the demo added. "
                   "Anything you saved or wrote yourself stays.")
        if st.button("Remove the demo data", icon=":material/delete_sweep:"):
            removed = demo.remove_demo_data(user.id)
            st.session_state["profile_notice"] = (
                f"Removed the sample data: {removed['grants']} saved grant(s) and "
                f"{removed['applications']} application(s)"
                + (", and your profile is back as it was." if removed["profile_restored"] else "."))
            st.rerun()
    else:
        st.markdown("**Just trying GrantBridge out?** Load a sample youth-tutoring nonprofit, "
                    "two saved sample grants, and one application to explore with.")
        st.caption("The sample organization happens to be in Connecticut; that is only an example. Every eligibility check runs against **your** state and your profile, and Find Grants searches federal opportunities nationwide.")
        replaces = demo.would_replace(user.id)
        st.caption(("This would replace " + ", and ".join(replaces) + "." if replaces
                    else "This fills in the profile fields below with demo values.")
                   + " GrantBridge keeps a copy, so you can put it back with one button.")
        if st.button("Load demo data", icon=":material/dataset:"):
            demo.load_demo_data(user.id)
            st.session_state["profile_notice"] = (
                "Demo data loaded: Harbor Lantern Tutoring Collective (sample). "
                "See Find Grants and Applications to explore, or remove it again here."
            )
            st.rerun()

state_codes = [""] + sorted(v.US_STATES, key=v.US_STATES.get)
tax_options = [""] + v.TAX_STATUSES


def _index(options: list[str], value: str) -> int:
    return options.index(value) if value in options else 0


with st.form("org_profile"):
    st.subheader("Basics", anchor=False)
    c1, c2, c3 = st.columns([2, 1, 1])
    name = c1.text_input("Organization name *", value=org.get("name", ""), max_chars=200)
    state = c2.selectbox(
        "State", state_codes, index=_index(state_codes, org.get("state", "")),
        format_func=lambda c: v.US_STATES.get(c, "Choose a state"),
    )
    city = c3.text_input("City", value=org.get("city", ""), max_chars=100)
    c4, c5, c6 = st.columns([2, 1, 1])
    tax_status = c4.selectbox(
        "501(c)(3) status (self-reported)", tax_options, index=_index(tax_options, org.get("tax_status", "")),
        format_func=lambda s: s or "Choose one",
        help="GrantBridge does not verify this with the IRS. Funders will.",
    )
    ein = c5.text_input("EIN (optional)", value=org.get("ein", ""), placeholder="12-3456789", max_chars=10)
    website = c6.text_input("Website (optional)", value=org.get("website", ""), placeholder="https://", max_chars=300)

    st.subheader("Mission, people, and programs", anchor=False)
    mission = st.text_area("Mission", value=org.get("mission", ""), max_chars=1500, height=90)
    population = st.text_area(
        "Populations served", value=org.get("population_served", ""), max_chars=1500, height=100,
        help="Who you serve: ages or grades, income, geography, languages, and how many people a year.",
    )
    programs = st.text_area(
        "Programs", value=org.get("programs", ""), max_chars=3000, height=140,
        help="What you do, how often, where, and with whom. Specific numbers make stronger drafts.",
    )
    focus = st.multiselect("Focus areas", v.FOCUS_AREAS, default=org.get("focus_areas", []))

    st.subheader("Funding request", anchor=False)
    c7, c8 = st.columns([1, 3])
    requested = c7.number_input(
        "Requested funding (USD)", min_value=0, max_value=100_000_000, step=1_000,
        value=org.get("requested_amount"), placeholder="e.g. 25000",
        help="The amount you usually ask a single funder for. Find Grants compares it with each award range.",
    )
    purpose = c8.text_area(
        "What the funding would pay for", value=org.get("funding_purpose", ""), max_chars=1500, height=90,
    )

    st.subheader("Track record and outcomes", anchor=False)
    track = st.text_area(
        "Track record and outcomes", value=org.get("track_record", ""), max_chars=3000, height=140,
        label_visibility="collapsed",
        help="Years running, people served, and measured results. Only put numbers here you can back up.",
        placeholder="e.g. Since 2017 we have served 900 students; last year 72% gained a grade level in reading.",
    )

    st.subheader("Size (optional)", anchor=False)
    c9, c10, c11 = st.columns(3)
    budget = c9.number_input(
        "Annual budget (USD)", min_value=0, max_value=1_000_000_000, step=10_000,
        value=org.get("annual_budget"), placeholder="e.g. 285000",
    )
    staff = c10.number_input(
        "Staff (full-time equivalent)", min_value=0, max_value=100_000, step=1,
        value=org.get("staff_size"), placeholder="e.g. 3",
    )
    founded = c11.number_input(
        "Year founded", min_value=1800, max_value=2100, step=1,
        value=org.get("founded_year"), placeholder="e.g. 2017",
    )

    saved = st.form_submit_button("Save profile", type="primary", icon=":material/save:")

if saved:
    try:
        repo.save_organization(user.id, {
            "name": name, "state": state, "city": city, "tax_status": tax_status, "ein": ein,
            "website": website, "mission": mission, "population_served": population,
            "programs": programs, "focus_areas": focus, "requested_amount": requested,
            "funding_purpose": purpose, "track_record": track, "annual_budget": budget,
            "staff_size": staff, "founded_year": founded,
        })
    except v.ValidationError as err:
        st.error(str(err), icon=":material/error:")
    else:
        st.session_state["profile_notice"] = "Profile saved."
        st.rerun()

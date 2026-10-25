"""Dashboard — where the user's grant work stands, and the one next step that matters most."""

from datetime import date

import streamlit as st

from grantbridge import components as c
from grantbridge import demo, drafting, repo, session, timeline, ui

user = session.require_user()
org = repo.get_organization(user.id) or {}
filled, total, missing = c.profile_meter(org)
saved = repo.list_saved_grants(user.id)
apps = repo.list_applications(user.id)
progress = {p["application_id"]: p for p in drafting.application_progress(user.id)}


def go(page: str, application_id: int | None = None) -> None:
    if application_id is not None:
        st.session_state["open_application_id"] = application_id
    st.switch_page(page)


name = org.get("name") or "your organization"
attention = c.attention_items(user.id)
pipeline = c.priority_grants(user.id)
if not (saved or apps):
    standing = "Nothing is in your pipeline yet. Start by finding a grant worth your time."
else:
    parts = [f"{len(saved)} saved grant(s)", f"{len(apps)} application(s)"]
    standing = (f"{ui.md_safe(name)} has {' and '.join(parts)} in progress. "
                + (f"{len(attention)} thing(s) need your attention below." if attention
                   else "Nothing needs your attention right now."))
c.header("Your funding workspace", ":material/space_dashboard:", standing)

notice = st.session_state.pop("dashboard_notice", None)
if notice:
    st.success(notice, icon=":material/check_circle:")

# ---------------------------------------------------------------- first run: three steps, one obvious next action
first_run = bool(missing) or not (saved or apps)
if first_run:
    steps = [
        (not missing, "Tell GrantBridge about your organization",
         "Every eligibility check and draft uses only the facts in your profile, so start here."),
        (bool(saved), "Find grants that fit",
         "Search practice grants or live federal opportunities, and save the ones worth a closer look."),
        (bool(apps), "Start an application",
         "Gather your facts, get a suggested draft, and review it before you submit anything."),
    ]
    current = next((i for i, (done, *_) in enumerate(steps) if not done), None)
    st.subheader("Get started in three steps", anchor=False, icon=":material/flag:")
    # Status is shown with words and icons, not color alone.
    for i, (col, (done, title, body)) in enumerate(zip(st.columns(3), steps)):
        with col.container(border=True, key=f"card-step-{i}", height="stretch"):
            st.markdown(":green-badge[:material/check: Done]" if done else (
                ":blue-badge[:material/arrow_forward: Next step]" if i == current else ":gray-badge[:material/schedule: Later]"))
            st.markdown(f"**{i + 1}. {title}**")
            st.caption(body)
            if i != current:
                continue
            if i == 0:
                if st.button("Set up your organization", type="primary", icon=":material/rocket_launch:",
                             key="start_profile", help="Three short steps, about three minutes. You can skip any "
                                                       "part and come back to it."):
                    go("app_pages/setup.py")
                if st.button("Try it with sample data", icon=":material/dataset:", key="start_demo",
                             help="Loads a sample youth-tutoring nonprofit, two saved sample grants, and "
                                  "one application. GrantBridge keeps a copy of your own profile, so you can "
                                  "remove the demo data again."):
                    demo.load_demo_data(user.id)
                    st.session_state["dashboard_notice"] = ("Demo data loaded: Harbor Lantern Tutoring Collective "
                                                            "(sample), two saved sample grants, and one "
                                                            "application. Next: press Find funding. You can remove "
                                                            "it again from Set up.")
                    st.rerun()
            elif i == 1:
                if st.button("Find funding", type="primary", icon=":material/travel_explore:", key="start_find"):
                    go("app_pages/find_grants.py")
            elif st.button("Go to Applications", type="primary", icon=":material/description:", key="start_apps"):
                go("app_pages/applications.py")
else:
    if missing:  # setup was skipped: offer to finish it, without nagging about it twice
        with st.container(border=True, key="card-finish-setup"):
            st.markdown(f"**Finish setting up** · {len(missing)} key field(s) still blank: "
                        f"{', '.join(missing)}. Checks that need them say **Unknown** instead of guessing.")
            if st.button("Finish setup", icon=":material/rocket_launch:", key="act_setup"):
                go("app_pages/setup.py")
    with st.container(horizontal=True):
        if st.button("Find funding", type="primary", icon=":material/travel_explore:", key="act_find"):
            go("app_pages/find_grants.py")
        if st.button("Ask the AI Grant Advisor", icon=":material/forum:", key="act_advisor"):
            go("app_pages/advisor.py")
        if st.button("Continue an application", icon=":material/description:", key="act_apps"):
            go("app_pages/applications.py")

# ---------------------------------------------------------------- at a glance
answered = sum(p["answered"] for p in progress.values())
questions = sum(p["questions"] for p in progress.values())
open_items = sum(p["open_items"] for p in progress.values())
samples = sum(g["is_example"] for g in saved)
col1, col2, col3 = st.columns(3)
col1.metric("Profile", f"{filled} of {total}", help="Key fields filled in. Checks show Unknown for missing ones.",
            border=True, height="stretch")
col2.metric("Saved grants", len(saved), help=f"{samples} sample, {len(saved) - samples} live Grants.gov",
            border=True, height="stretch")
col3.metric("Applications", len(apps), help=f"{answered} of {questions} questions answered; "
                                            f"{open_items} verification item(s) open", border=True, height="stretch")
st.progress(filled / total, text=f"Profile completeness: {filled} of {total} key fields"
            + (f" · still missing: {', '.join(missing)}" if missing else " · complete"))

# ---------------------------------------------------------------- what needs your attention
URGENCY = {"overdue": ":red-badge[:material/error: Overdue]", "soon": ":orange-badge[:material/schedule: Soon]",
           "open": ":blue-badge[:material/radio_button_unchecked: Open]"}
if attention:
    st.subheader("What needs your attention", anchor=False, icon=":material/priority_high:",
                 help="Only items GrantBridge can see in your own records: late or due workback steps, "
                      "verification items left open, verified deadlines within three weeks, and saved grants "
                      "you have not assessed.")
    for i, item in enumerate(attention):
        with st.container(border=True, key=f"card-attention-{i}"):
            cols = st.columns([5, 1], vertical_alignment="center")
            with cols[0]:
                st.markdown(f"{URGENCY[item['urgency']]} **{ui.md_safe(item['title'])}**")
                st.caption(item["detail"])
            if cols[1].button(item["action"], key=f"attention_{i}", icon=":material/arrow_forward:"):
                if item["grant_id"]:
                    st.session_state["pursue_target"] = f"grant:{item['grant_id']}"
                go(item["page"], item["application_id"])

# ---------------------------------------------------------------- the pipeline, one row per saved grant
if pipeline:
    st.subheader("Your grant pipeline", anchor=False, icon=":material/table_rows:",
                 help="Every grant you have saved, what GrantBridge decided about it, and the next step. "
                      "Dates on SAMPLE grants are invented for practice.")
    st.dataframe(
        [{"Grant": r["title"], "Funder": r["funder"],
          "Deadline": (r["deadline"] or "none listed") + (" (SAMPLE)" if r["sample"] and r["deadline"] else ""),
          "Assessment": r["assessment"] + (f" · {r['assessed_on']}" if r["assessed_on"] else ""),
          "Next action": r["action"]} for r in pipeline],
        hide_index=True, width="stretch")

# ---------------------------------------------------------------- applications, saved grants, deadlines
left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader("Applications in progress", anchor=False, icon=":material/description:",
                 help="Newest first. Open one to keep writing.")
    if not apps:
        if c.empty_state(":material/description:", "No applications yet",
                         "Save a grant that looks promising, then choose **Work on application** on its card.",
                         action="Find funding", key="no-apps", primary=not first_run):  # one primary action only
            go("app_pages/find_grants.py")
    for a in apps[:4]:
        p = progress.get(a["id"], {"answered": 0, "questions": 0, "open_items": 0, "ready": 0})
        grant = repo.get_grant(a["grant_id"]) if a["grant_id"] else None
        with st.container(border=True, key=f"card-app-{a['id']}"):
            st.markdown(f"{c.application_badge(grant)} :gray-badge[{ui.md_safe(a['status'])}]")
            st.markdown(f"**{ui.md_safe(a['title'])}**")
            share = p["answered"] / p["questions"] if p["questions"] else 0.0
            st.progress(share, text=f"{p['answered']} of {p['questions']} questions answered · "
                                    f"{p['ready']} ready · {p['open_items']} verification item(s) open")
            st.caption(c.due_date_note(a, grant))
            if st.button("Continue", key=f"dash_open_{a['id']}", icon=":material/arrow_forward:"):
                go("app_pages/applications.py", a["id"])
with right:
    st.subheader("Saved grants", anchor=False, icon=":material/bookmarks:")
    if not saved:
        if c.empty_state(":material/bookmarks:", "Nothing saved yet",
                         "Use **Save** on any grant card to keep it here.", action="Find funding", key="no-saved",
                         primary=False):
            go("app_pages/find_grants.py")
    for g in saved[:4]:
        with st.container(border=True, key=f"card-{'sample' if g['is_example'] else 'live'}-dash-{g['id']}"):
            st.markdown(c.SAMPLE_BADGE if g["is_example"] else c.LIVE_BADGE)
            st.markdown(f"**{ui.md_safe(g['title'])}**  \n{ui.md_safe(g['funder'])}")
    if saved and st.button("View all saved grants", key="dash_saved", icon=":material/bookmarks:"):
        go("app_pages/saved_grants.py")

    st.subheader("Deadlines", anchor=False, icon=":material/event:",
                 help="Only trustworthy dates: close dates listed on Grants.gov, and due dates you entered yourself. "
                      "GrantBridge does not send reminders.")
    reminders = c.deadline_reminders(user.id)
    if not reminders:
        with st.container(border=True, key="card-empty-deadlines"):
            st.markdown("**:material/event_available: No upcoming verified deadlines**")
            st.markdown("Close dates appear here for Grants.gov opportunities you save or apply to, and due dates "
                        "for applications you create yourself.")
            st.caption("Sample grants never appear here: their dates are invented for practice.")
    for item in reminders[:5]:
        days = (item["date"] - date.today()).days
        when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
        with st.container(border=True, key=f"card-deadline-{c.slug(item['title'])}-{item['date']}"):
            st.markdown(f"**{item['date'].strftime('%b %d, %Y')}** ({when}) · {ui.md_safe(item['title'])}")
            if item["kind"] == "grants.gov":
                st.caption(f"Close date listed on Grants.gov when GrantBridge copied it ({item['copied']}). "
                           f"[Confirm on Grants.gov]({item['url']}) before relying on it.")
            else:
                st.caption("A due date you entered or corrected yourself.")

    st.subheader("Next steps", anchor=False, icon=":material/checklist:",
                 help="From the workback plans on your applications' Timeline tabs. GrantBridge does not send "
                      "reminders.")
    steps = timeline.upcoming(user.id, limit=5)
    if not steps:
        st.caption("No workback plans yet. Open an application's **Timeline** tab to plan back from its deadline.")
    for step in steps:
        badge = {"overdue": f":red-badge[:material/error: {step['words']}]",
                 "today": ":orange-badge[:material/today: Due today]"}.get(step["status"], f":blue-badge[{step['words']}]")
        practice = " :orange-badge[Practice plan: SAMPLE date]" if step["practice"] else ""
        with st.container(border=True, key=f"card-step-{step['application_id']}-{c.slug(step['step'])}"):
            st.markdown(f"{badge}{practice}  \n**{step['step']}** · due {step['due']} · {ui.md_safe(step['title'])}")

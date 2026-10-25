"""Saved Grants — the grants this account kept from Find Grants or the AI Grant Advisor."""

import streamlit as st

from grantbridge import components as c
from grantbridge import grant_search as gs
from grantbridge import repo, session, ui

user = session.require_user()
org = repo.get_organization(user.id) or {}
saved = repo.list_saved_grants(user.id)

c.header("Saved Grants", ":material/bookmarks:",
         "Grants you saved from Find Grants or the AI Grant Advisor. Live ones are dated copies of a Grants.gov "
         "listing: confirm them on Grants.gov before you apply.")

notice = st.session_state.pop("saved_notice", None)
if notice:
    st.success(notice, icon=":material/check_circle:")

if not saved:
    if c.empty_state(":material/bookmarks:", "You haven't saved any grants yet",
                     "On **Find Grants**, press **Save** on any grant to keep it here with its checks and source. "
                     "The AI Grant Advisor can also save a grant when you ask it to.",
                     action="Find funding", key="saved-none"):
        st.switch_page("app_pages/find_grants.py")
    st.stop()

samples = [g for g in saved if g["is_example"]]
live = [g for g in saved if not g["is_example"]]
show = st.segmented_control("Show", ["all", "sample", "live"], key="saved_filter", required=True, default="all",
                            format_func={"all": f"All ({len(saved)})", "sample": f"Sample ({len(samples)})",
                                         "live": f"Grants.gov ({len(live)})"}.get)


def open_application(grant_id: str) -> None:
    st.session_state["open_application_id"] = repo.create_application_from_grant(user.id, grant_id)
    st.switch_page("app_pages/applications.py")


def pursue(grant_id: str) -> None:
    st.session_state["pursue_target"] = f"grant:{grant_id}"
    st.switch_page("app_pages/pursue.py")


def remove(grant_id: str, title: str) -> None:
    repo.unsave_grant(user.id, grant_id)
    st.session_state["saved_notice"] = f"Removed {title} from your saved grants."
    st.rerun()


filters = gs.filters_from_profile(org)
if show in ("all", "sample"):
    for g in samples:
        r = gs.sample_result(g, filters)  # re-checked against the current profile
        with c.grant_card(r, key=f"saved-{g['id']}"):
            existing = repo.application_for_grant(user.id, g["id"])
            with st.container(horizontal=True):
                if st.button("Continue application" if existing else "Start application",
                             key=f"saved_apply_{g['id']}", type="primary", icon=":material/description:"):
                    open_application(g["id"])
                if st.button("Should we pursue?", key=f"saved_pursue_{g['id']}", icon=":material/thumbs_up_down:",
                             type="tertiary", help="A go/no-go check: eligibility, fit, readiness, time, and budget"):
                    pursue(g["id"])
                if st.button("Remove", key=f"saved_remove_{g['id']}", icon=":material/bookmark_remove:",
                             type="tertiary"):
                    remove(g["id"], g["title"])
            with st.expander("Eligibility checks and what to verify", icon=":material/checklist:"):
                c.grant_details(r)

if show in ("all", "live"):
    for g in live:
        with st.container(border=True, key=f"card-live-saved-{g['id']}"):
            copied = (g.get("retrieved_at") or "")[:16].replace("T", " ")
            deadline = (f"Close date listed on Grants.gov: {g['deadline']}" if g["deadline"] not in ("", "unknown")
                        else "Grants.gov listed no close date")
            st.markdown(f"{c.LIVE_BADGE} :gray-badge[Copied {copied} UTC]")
            st.subheader(g["title"], anchor=False)
            award = (ui.amount_range(g["amount_min"], g["amount_max"]) if (g["amount_min"] or g["amount_max"])
                     else "Not listed in the copy")
            st.markdown(f"{ui.md_safe(g['funder'])} · **Award:** {award} · **Source:** "
                        f"[Grants.gov page]({g['source_url']})")
            st.markdown(f":material/event: {deadline} (as of the copy). Saved copy from Grants.gov, {copied} UTC: "
                        "the listing may have changed since, so confirm its status on Grants.gov.")
            st.markdown(":material/fact_check: **Fit:** run a live search on Find Grants to re-check this listing "
                        "against your current profile.")
            existing = repo.application_for_grant(user.id, g["id"])
            with st.container(horizontal=True):
                if st.button("Continue application" if existing else "Start application",
                             key=f"saved_apply_{g['id']}", type="primary", icon=":material/description:"):
                    open_application(g["id"])
                if st.button("Should we pursue?", key=f"saved_pursue_{g['id']}", icon=":material/thumbs_up_down:",
                             type="tertiary", help="A go/no-go check: eligibility, fit, readiness, time, and budget"):
                    pursue(g["id"])
                if st.button("Remove", key=f"saved_remove_{g['id']}", icon=":material/bookmark_remove:",
                             type="tertiary"):
                    remove(g["id"], g["title"])
                st.link_button("Open on Grants.gov", g["source_url"], icon=":material/open_in_new:", type="tertiary")
            if g["eligibility"]:
                with st.expander("Eligibility and description", icon=":material/checklist:"):
                    st.markdown("**Eligible applicant types listed by Grants.gov**")
                    st.markdown("\n".join(f"- {ui.external_md(e)}" for e in g["eligibility"]))
                    if g["summary"]:
                        st.markdown("**Description (excerpt)**")
                        st.markdown(ui.external_md(ui.clip(g["summary"], 1200)))

if show == "sample" and not samples:
    st.caption("No sample grants saved.")
if show == "live" and not live:
    st.caption("No Grants.gov grants saved. Switch Find Grants to **Grants.gov (live federal search)** to find some.")

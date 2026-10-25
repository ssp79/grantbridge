"""Find Grants — search practice samples or live Grants.gov, check fit with code, and explain it with AI."""

import os

import streamlit as st

from grantbridge import components as c
from grantbridge import fit_explainer, grant_search as gs, grants_gov as gg, repo, session, trace, ui
from grantbridge import validation as v
from grantbridge.db import SAMPLE_LABEL

LIVE_ENABLED = os.getenv("GRANTBRIDGE_LIVE_SEARCH", "on").strip().lower() not in ("0", "off", "false", "no")
SOURCE_LABELS = {gs.SAMPLE: "Practice grants (samples)", gs.LIVE: "Real federal grants (Grants.gov)"}
# Round stops rather than a linear slider: awards run from a few thousand to several million, and a linear
# scale spends most of its travel on sums no small nonprofit would request.
AWARD_STOPS = (0, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 5_000_000)


def award_label(amount: int) -> str:
    if amount == 0:
        return "Any"
    if amount >= AWARD_STOPS[-1]:
        return "$5M+"
    if amount >= 1_000_000:
        return f"${amount // 1_000_000}M"
    return f"${amount // 1000}k"

user = session.require_user()
org = repo.get_organization(user.id) or {}
saved = repo.saved_grant_ids(user.id)
explanations = st.session_state.setdefault("fit_explanations", {})

c.header("Find Grants", ":material/travel_explore:",
         "Search real federal grants from Grants.gov, or practice on GrantBridge's samples. For each grant, "
         "GrantBridge compares its rules with your profile and lists what you still need to check yourself. "
         "Then save the ones you like, or start an application.")

# Real funding first: the samples are for learning the tool, not for finding money. Seeded here instead of
# passing default=, because the "practice grants instead" button sets it too.
SOURCES = [gs.LIVE, gs.SAMPLE] if LIVE_ENABLED else [gs.SAMPLE]
if st.session_state.get("search_source") not in SOURCES:
    st.session_state["search_source"] = SOURCES[0]
source = st.segmented_control(
    "Where to search", SOURCES, format_func=SOURCE_LABELS.get, key="search_source", required=True,
)
if source == gs.SAMPLE:
    st.warning(
        f"**{SAMPLE_LABEL}.** These are illustrative opportunities for exploring GrantBridge. Choose "
        "**Real federal grants (Grants.gov)** above to search live federal funding.",
        icon=":material/science:",
    )
else:
    st.info(
        "**Live results from Grants.gov.** Statuses and dates are what Grants.gov reported when GrantBridge "
        "retrieved them, shown with the retrieval time. Always confirm on the linked Grants.gov page before "
        "applying. Only your search filters (keyword, Grants.gov category codes, and organization type) are "
        "sent to Grants.gov, never your profile text.",
        icon=":material/public:",
    )
    st.caption(gg.ATTRIBUTION)
if not LIVE_ENABLED:
    st.caption("Live Grants.gov search is turned off on this server (GRANTBRIDGE_LIVE_SEARCH=off).")

missing = repo.missing_profile_fields(org)
if missing:
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f":material/apartment: Your profile is missing {len(missing)} key field(s) "
                    f"({', '.join(missing)}), so some checks will say **Unknown**.")
        st.page_link("app_pages/profile.py", label="Complete your profile", icon=":material/arrow_forward:")

defaults = gs.filters_from_profile(org)
with st.form(f"search_form_{source}"):
    k_col, b_col = st.columns([4, 1], vertical_alignment="bottom")
    keyword = k_col.text_input(
        "Keyword (optional)", max_chars=100,
        placeholder="e.g. tutoring" if source == gs.SAMPLE else "e.g. literacy, after school",
    )
    submitted = b_col.form_submit_button("Search", type="primary", icon=":material/search:", width="stretch")
    with st.expander("Filters", icon=":material/tune:"):
        f1, f2 = st.columns(2)
        focus = f1.multiselect("Focus areas", v.FOCUS_AREAS, default=list(defaults.focus_areas),
                               help="Starts from your Organization Profile.")
        low, high = f2.select_slider(
            "Award size you would consider", options=list(AWARD_STOPS), value=(AWARD_STOPS[0], AWARD_STOPS[-1]),
            format_func=award_label,
            help="Keeps grants whose award range overlaps yours. A grant whose award size the funder did not "
                 "state is always kept: GrantBridge does not treat unknown as a no.")
        award_range = None if (low, high) == (AWARD_STOPS[0], AWARD_STOPS[-1]) else (
            low, None if high == AWARD_STOPS[-1] else high)
        if source == gs.LIVE:
            codes = defaults.live_params()
            f2.caption("Sent to Grants.gov: categories " + (", ".join(gs.categories_for(focus)) or "none")
                       + " · applicant type " + (", ".join(codes.eligibilities) or "any")
                       + " · statuses posted and forecasted. Grants.gov cannot filter by award size, so "
                         "GrantBridge applies that to the results it gets back.")
        hide = f1.toggle("Hide grants that fail a required check", value=False)
        hide_research = False
        if source == gs.LIVE:
            hide_research = f2.toggle(
                "Hide research-type grants", value=True,
                help="Hides grants whose title or number looks like a research award (for example NIH R01, "
                     "R21, or clinical trials). These usually fund universities and research institutions.",
            )
    st.caption("GrantBridge compares each grant with your profile: " + ui.profile_basis(org))

outcome_key, filters_key = f"search_outcome_{source}", f"search_filters_{source}"
version_key = f"search_profile_version_{source}"
# Checks are computed from the profile, so results from before a profile edit are stale.
if outcome_key in st.session_state and st.session_state.get(version_key) != org.get("version"):
    del st.session_state[outcome_key]
    if source == gs.LIVE:
        st.info("Your profile changed since the last search. Press **Search** to refresh the checks.",
                icon=":material/sync:")
if submitted or (source == gs.SAMPLE and outcome_key not in st.session_state):
    filters = gs.filters_from_profile(org, keyword=keyword, focus_areas=tuple(focus),
                                      award_range=award_range, hide_failing=hide,
                                      hide_research=hide_research)
    with st.spinner("Searching Grants.gov…" if source == gs.LIVE else "Searching sample grants…"):
        st.session_state[outcome_key] = gs.run_search(user.id, filters, source)
    st.session_state[filters_key] = filters
    st.session_state[version_key] = org.get("version")

outcome: gs.SearchOutcome | None = st.session_state.get(outcome_key)
filters: gs.SearchFilters = st.session_state.get(filters_key, defaults)

if outcome is None:
    st.info("Choose your filters and press **Search** to query Grants.gov. Nothing is sent until you do.",
            icon=":material/search:")
    st.stop()

if outcome.error:
    st.error(outcome.error, icon=":material/cloud_off:")
    st.button("Show the practice grants instead", icon=":material/science:", key="fallback_to_samples",
              on_click=lambda: st.session_state.update(search_source=gs.SAMPLE))
elif not outcome.results:
    st.info("No grants match these filters. Try a different keyword, fewer focus areas, or a lower minimum "
            "award, or turn off the hiding toggles under **Filters**.", icon=":material/filter_alt_off:")

notes = []
if outcome.source == gs.SAMPLE and outcome.results:
    notes.append(f"{len(outcome.results)} sample grant(s) match. {SAMPLE_LABEL}.")
if outcome.source == gs.LIVE and not outcome.error:
    stamp = gs.fmt_time(outcome.retrieved_at) if outcome.retrieved_at else "unknown time"
    notes.append(f"Grants.gov reported {outcome.total_matches:,} match(es); GrantBridge retrieved up to "
                 f"{gg.MAX_ROWS} on {stamp}" + (" (from a 15-minute cache)." if outcome.from_cache else "."))
    notes.append("Grants.gov's keyword search is broad, so some results may not mention your keyword.")
    if outcome.hidden_award:
        notes.append(f"Hid {outcome.hidden_award} grant(s) whose award size is outside the range you set. "
                     "Grants with no stated award size were kept.")
    if outcome.duplicates_merged:
        notes.append(f"Merged {outcome.duplicates_merged} duplicate listing(s): Grants.gov returned the same "
                     "opportunity number more than once.")
    if outcome.hidden_closed:
        notes.append(f"Hid {outcome.hidden_closed} result(s) whose close date has passed, including forecasts "
                     "whose estimated close date is already in the past.")
    if outcome.hidden_research:
        notes.append(f"Hid {outcome.hidden_research} research-type grant(s) (for example NIH R01s); "
                     "turn off \"Hide research-type grants\" under Filters to see them.")
    if outcome.skipped_malformed:
        notes.append(f"Skipped {outcome.skipped_malformed} result(s) Grants.gov sent in an unreadable format.")
if outcome.hidden_failing:
    notes.append(f"Hid {outcome.hidden_failing} grant(s) that fail a required check.")
if notes:
    st.caption(" ".join(notes))
if outcome.results:
    st.caption("Best matches first, sorted by GrantBridge's rules (not AI): grants that fail a required rule go "
               "last and research-type grants next to last; the rest by deadline status, checks met, and close date.")


def explanation_key(r: gs.GrantResult) -> tuple:
    return (r.source, r.id, r.details_loaded, org.get("version"))


def open_application(grant_id: str) -> None:
    st.session_state["open_application_id"] = repo.create_application_from_grant(user.id, grant_id)
    st.switch_page("app_pages/applications.py")


def ask_advisor(question: str) -> None:
    st.session_state["advisor_pending"] = question
    st.switch_page("app_pages/advisor.py")


def render_card(i: int, r: gs.GrantResult) -> None:
    with c.grant_card(r, key=f"{source}-{r.id}"):
        # One primary next step per card; saving and the AI explanation are secondary.
        with st.container(horizontal=True, key=f"actions-{source}-{r.id}"):
            if r.is_live:
                gid = f"gg-{r.id}"
                existing = repo.application_for_grant(user.id, gid)
                if st.button("Continue application" if existing else "Start application",
                             key=f"apply_{source}_{r.id}", type="primary", icon=":material/description:",
                             help="Saves a dated copy of this listing, then opens its application"):
                    open_application(repo.save_live_grant_snapshot(r))
                is_saved = gid in saved
                if st.button("Saved" if is_saved else "Save", key=f"save_live_{r.id}",
                             icon=":material/bookmark:" if is_saved else ":material/bookmark_border:",
                             help="Remove from saved" if is_saved else "Saves a dated copy of this Grants.gov listing"):
                    if is_saved:
                        repo.unsave_grant(user.id, gid)
                    else:
                        repo.save_grant(user.id, repo.save_live_grant_snapshot(r))
                    st.rerun()
                if not r.details_loaded and st.button(
                        "Load details", key=f"details_{source}_{r.id}", icon=":material/download:",
                        help="Fetch award amounts and eligibility from Grants.gov"):
                    updated, error = gs.run_details(user.id, r, filters)
                    if error:
                        st.session_state["find_notice"] = error
                    else:
                        outcome.results[i] = updated
                    st.rerun()
            else:
                existing = repo.application_for_grant(user.id, r.id)
                if st.button("Continue application" if existing else "Start application", key=f"apply_{r.id}",
                             type="primary", icon=":material/description:"):
                    open_application(r.id)
                is_saved = r.id in saved
                if st.button("Saved" if is_saved else "Save", key=f"save_{r.id}",
                             icon=":material/bookmark:" if is_saved else ":material/bookmark_border:",
                             help="Remove from saved" if is_saved else "Keep it on your Saved Grants page"):
                    (repo.unsave_grant if is_saved else repo.save_grant)(user.id, r.id)
                    st.rerun()
            if st.button("Should we pursue?", key=f"pursue_{source}_{r.id}", icon=":material/thumbs_up_down:",
                         type="tertiary", help="A go/no-go check: eligibility, fit, readiness, time, and budget"):
                grant_id = repo.save_live_grant_snapshot(r) if r.is_live else r.id  # a dated copy, not a save
                st.session_state["pursue_target"] = f"grant:{grant_id}"
                st.switch_page("app_pages/pursue.py")
            if st.button("Explain fit (AI)", key=f"explain_{source}_{r.id}", icon=":material/smart_toy:",
                         type="tertiary", help="Sends your profile facts and this grant's text to the AI model"):
                with st.spinner("Asking the AI model…"):
                    explanations[explanation_key(r)] = fit_explainer.run_explain(user.id, org, r)
                st.rerun()
            if r.is_live:
                st.link_button("Open on Grants.gov", r.source_url, icon=":material/open_in_new:", type="tertiary")
        cached = explanations.get(explanation_key(r))
        if cached:
            with st.expander("AI explanation of the fit", expanded=True, icon=":material/smart_toy:"):
                c.explanation_block(cached, key=f"{source}-{r.id}")
        with st.expander("Eligibility checks and what to verify", icon=":material/checklist:"):
            c.grant_details(r)
            if st.button("Ask the AI Grant Advisor about this grant", key=f"ask_{source}_{r.id}",
                         icon=":material/forum:", type="tertiary"):
                ask_advisor(f"What does {r.title} ({r.id}) require, and what should we check before applying?")


notice = st.session_state.pop("find_notice", None)
if notice:
    st.warning(notice, icon=":material/cloud_off:")

for index, result in enumerate(outcome.results):
    render_card(index, result)

with st.expander("Technical details: how this search ran (privacy-safe trace)", icon=":material/account_tree:"):
    if outcome.run_id:
        st.markdown("**Steps in the last search**")
        st.dataframe(ui.trace_rows(trace.run_steps(user.id, outcome.run_id)), hide_index=True,
                     width="stretch")
    st.markdown("**Your recent agent activity**")
    st.dataframe(ui.run_rows(trace.list_runs(user.id, limit=10)), hide_index=True, width="stretch")
    st.caption(
        "Recorded: step names, timings, statuses, counts, filter categories, public grant ids, and token counts. "
        "Not recorded: your keyword text (only its length), profile text, email, or the AI's prompts and replies."
    )

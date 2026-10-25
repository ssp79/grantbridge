"""Applications — a workspace per application: the grant's requirements and source, your answers, AI help, and
everything that still needs a person to verify it."""

import os
from collections import Counter
from datetime import date

import streamlit as st

from grantbridge import components as c
from grantbridge import budget, drafting, outline as outline_mod, outline_docx, proposal_review, repo, session, start_application, timeline, ui, validation as v
from grantbridge.config import ConfigError, resolve_settings

STATUS_COLORS = {"not_started": "gray", "draft_waiting": "violet", "in_progress": "orange",
                 "needs_verification": "red", "ready": "green"}
REQUIREMENT_STATUS = {"met": "Met", "partly": "Partly", "missing": "Missing",
                      "unverified": "Evidence not found", "not reviewed": "Not reviewed"}
PRIORITY_BADGES = {"high": ":red-badge[:material/priority_high: High priority]",
                   "medium": ":orange-badge[Medium priority]", "low": ":gray-badge[Low priority]"}

user = session.require_user()
apps = repo.list_applications(user.id)
try:
    resolve_settings()
    key_found = True
except ConfigError:
    key_found = False
default_mock = (not key_found) or os.getenv("GRANTBRIDGE_ADVISOR_MODE", "").strip().lower() == "mock"

c.header("Applications", ":material/description:",
         "Start an application and write it here. Each one keeps the funder's own requirements beside your "
         "writing, and AI suggestions never change your text until you choose to use them.")

# Always present, so elements below (the tabs) keep their position: Streamlit resets the selected
# tab when an element appears or disappears above it.
with st.container():
    notice = st.session_state.pop("apps_notice", None)
    if notice:
        st.success(notice, icon=":material/check_circle:")
    warning = st.session_state.pop("apps_warning", None)
    if warning:
        st.warning(warning, icon=":material/info:")


# ---------------------------------------------------------------- start one, or work on one
# Starting an application and working on one used to be separate pages, which made people hunt for the upload.
# They are the same page now: the start flow takes over the whole page while it is open.
if not apps:
    st.info("You have no applications yet. Start one below — from a grant you saved, from the funder's own "
            "solicitation, or from scratch.", icon=":material/waving_hand:")
    start_application.render(user, key_found=key_found, default_mock=default_mock, has_applications=False)
    st.stop()

if st.session_state.get(start_application.MODE) == "new":
    start_application.render(user, key_found=key_found, default_mock=default_mock, has_applications=True)
    st.stop()

progress = drafting.application_progress(user.id)
ids = [a["id"] for a in apps]
wanted = st.session_state.pop("open_application_id", None)
if wanted in ids:
    st.session_state["app_picker"] = wanted
elif st.session_state.get("app_picker") not in ids:
    st.session_state["app_picker"] = ids[0]
by_id = {a["id"]: a for a in apps}
pick_col, new_col = st.columns([4, 1], vertical_alignment="bottom")
app_id = pick_col.selectbox("Application you are working on", ids, key="app_picker",
                            format_func=lambda i: f"{by_id[i]['title']} (#{i})")  # stable label: see the Question picker
if new_col.button("New application", icon=":material/add:", width="stretch"):
    st.session_state[start_application.MODE] = "new"
    st.rerun()

with st.expander("All applications at a glance", icon=":material/table_view:"):
    st.dataframe(
        [{"Application": p["title"], "Status": p["status"], "Due": p["due_date"] or "—",
          "Answered": f"{p['answered']} of {p['questions']}", "Ready": p["ready"],
          "Needs verification": p["needs_verification"], "Not reviewed": p["in_progress"],
          "Open checks": p["open_items"]} for p in progress],
        hide_index=True, width="stretch",
    )
    st.caption("Ready means reviewed after the last edit, with every verification item ticked. "
               "Not reviewed means the answer changed since its last review.")

app = repo.get_application(user.id, app_id)
if app is None:  # deleted in another tab
    st.rerun()
sections = repo.list_sections(user.id, app_id)
requirements = repo.list_requirements(user.id, app_id)
grant = repo.get_grant(app["grant_id"]) if app["grant_id"] else None
mine = next(p for p in progress if p["application_id"] == app_id)

# The same five elements on every run (see the note above the notices).
with st.container(border=True, key="card-app-header"):
    st.markdown(f"{c.application_badge(grant)} :gray-badge[{ui.md_safe(app['status'])}]")
    st.subheader(app["title"], anchor=False)
    if grant is None:
        source = "your own application (no catalog grant)"
    elif grant["is_example"]:
        source = "a sample opportunity, for exploring GrantBridge"
    else:
        source = (f"[Grants.gov page]({grant['source_url']}), copied {grant['retrieved_at'].replace('T', ' ')[:16]} UTC. "
                  "The listing may have changed since: confirm its status and requirements there.")
    award = ui.amount_range(grant["amount_min"], grant["amount_max"]) if grant else "—"
    st.markdown(f"{ui.md_safe(app['funder'] or 'Funder not set')} · **Award range:** {award} · **Source:** {source}")
    st.caption(c.due_date_note(app, grant))
    share = mine["answered"] / mine["questions"] if mine["questions"] else 0.0
    st.progress(share, text=f"{mine['answered']} of {mine['questions']} questions answered · {mine['ready']} ready · "
                            f"{mine['open_items']} verification item(s) open")
    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        # One switch for every AI feature on this page (facts, drafts, reviews, revisions), rendered before the
        # tabs so that each tab reads the same choice.
        mock_on = st.toggle("Practice mode (no AI, free)", value=default_mock, disabled=not key_found,
                            key="draft_mock",
                            help="Fact questions, drafts, reviews, and revisions on this page come from GrantBridge's "
                                 "fixed rules instead of the AI, labeled MOCK. Useful for practice; they cost nothing.")
        if st.button("Should we pursue this grant?" if grant else "Should we pursue this?",
                     key=f"pursue_app_{app_id}", icon=":material/thumbs_up_down:", type="tertiary",
                     help="A go/no-go check: eligibility, fit, readiness, time, budget, and proposal quality"):
            st.session_state["pursue_target"] = f"grant:{grant['id']}" if grant else f"application:{app_id}"
            st.switch_page("app_pages/pursue.py")
        if grant is not None and st.button("Ask the AI Grant Advisor about this grant", key=f"ask_app_{app_id}",
                                           icon=":material/forum:", type="tertiary"):
            st.session_state["advisor_pending"] = (f"What does {grant['title']} ({grant['id']}) require, and what "
                                                   "should we check before applying?")
            st.switch_page("app_pages/advisor.py")

# Fixed labels: Streamlit keeps the selected tab across reruns only while the labels stay the same.
outline_tab, write_tab, review_tab, budget_tab, timeline_tab, source_tab, details_tab, export_tab = st.tabs(
    ["Proposal outline", "Write answers", "Review proposal", "Budget & narrative", "Timeline",
     "Requirements & source", "Details", "Export"])

# ---------------------------------------------------------------- the funder's outline, and writing to it
with outline_tab:
    st.markdown("##### The outline the funder asked for")
    st.markdown(
        "Most solicitations do not ask questions. They name the sections you must write and list what each one "
        "has to contain. This tab holds that outline exactly as the funder gave it, with the sentence each "
        "requirement came from.")
    st.info(
        "**Two ways to write, and you can mix them.**\n\n"
        ":material/description: **Here, or in Word.** Write each section in the boxes below, or use **Work in "
        "Word instead** to download the outline as a Word document, write and circulate it for comment, then "
        "upload it back. Your writing lands in the same sections either way, and you can move between the two "
        "as often as you like.\n\n"
        ":material/edit_note: **Or use the Write answers tab** if this grant asks numbered questions rather "
        "than prescribing sections. That tab is where the AI help lives: finding missing facts, drafting an "
        "answer from your own records, reviewing it, and suggesting revisions. Nothing on this tab is written "
        "by AI.", icon=":material/alt_route:")
    outline_sections = repo.list_outline_sections(user.id, app_id)
    stored_outline = repo.get_application_outline(user.id, app_id)

    if not outline_sections and not stored_outline:
        st.info(
            "**No outline yet for this application.** Upload the funder's solicitation and GrantBridge will "
            "read out the sections you are expected to write, what each one must contain, how it will be "
            "scored, and what you must file — all shown beside the sentence in the document it came from, for "
            "you to check before any of it is saved here.", icon=":material/format_list_numbered:")
        if st.button("Read a solicitation into this application", type="primary",
                     icon=":material/document_scanner:", key=f"outline_import_{app_id}"):
            # Open the start flow already pointed at this application, so the outline lands here.
            st.session_state[start_application.MODE] = "new"
            st.session_state["new_app_route"] = "documents"
            st.session_state["imp_target"] = "An application I already have"
            st.session_state["imp_app"] = app_id
            st.rerun()
        st.caption("You can also work without an outline: the **Write answers** tab handles grants that ask "
                   "questions outright, and **Requirements & source** takes requirements pasted as text.")
    else:
        payload = (stored_outline or {}).get("payload") or {}
        ticks = (stored_outline or {}).get("objective_ticks") or {}
        states = (stored_outline or {}).get("component_state") or {}

        done = sum(1 for s in outline_sections if s["status"] == "ready")
        drafted = sum(1 for s in outline_sections if (s["response"] or "").strip())
        elements_total = sum(len(s["elements"]) for s in outline_sections)
        elements_done = sum(len(s["ticked"]) for s in outline_sections)
        if outline_sections:
            st.progress(done / len(outline_sections) if outline_sections else 0.0,
                        text=f"{done} of {len(outline_sections)} section(s) marked ready · {drafted} started · "
                             f"{elements_done} of {elements_total} required element(s) ticked")

        # ------------------------------------------------ work in Word instead, then bring it back
        st.markdown("##### Work in Word instead")
        st.markdown(
            "Not everyone wants to write in a browser, and most organizations circulate a draft for comment "
            "before anyone types it anywhere. Download the outline as a Word document, write in it, and upload "
            "it back — GrantBridge matches your writing to these sections by heading and shows you exactly what "
            "would change before it saves anything.")
        down, up = st.columns(2, gap="large")
        with down:
            st.markdown("**1. Download**")
            st.caption("The funder's order, with each section's requirements in a boxed note and anything you "
                       "have already written here included.")
            try:
                document = outline_docx.build(app["title"], app["funder"] or "", outline_sections, payload)
            except Exception:  # a malformed outline must not take the whole tab down
                st.warning("The Word file could not be built for this outline.", icon=":material/error:")
            else:
                st.download_button(
                    "Download the outline (.docx)", data=document,
                    file_name=f"{c.slug(app['title'])[:60] or 'application'}-outline.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    icon=":material/download:", width="stretch")
        with up:
            st.markdown("**2. Upload it back**")
            st.caption("Keep the headings as they are and leave them styled Heading 1. The boxed notes are "
                       "ignored, so only your own paragraphs come back.")
            returned = st.file_uploader("Edited outline", type=["docx"], key=f"outline_back_{app_id}",
                                        label_visibility="collapsed")
            if returned is not None:
                try:
                    drafts, problems = outline_docx.read_back(returned.getvalue(), outline_sections)
                except ValueError as err:
                    st.error(str(err), icon=":material/error:")
                else:
                    counts = outline_docx.summarise(drafts, outline_sections)
                    for problem in problems:
                        st.warning(problem, icon=":material/help:")
                    if not counts["changed"]:
                        st.info("Nothing in that file differs from what is already here.",
                                icon=":material/check_circle:")
                    else:
                        st.markdown(
                            f"**{counts['changed']} section(s) would change**: {counts['new_text']} newly "
                            f"written, {counts['replaced']} replaced"
                            + (f", {counts['emptied']} emptied" if counts["emptied"] else "")
                            + f". {counts['unchanged']} unchanged.")
                        for draft in drafts:
                            if not draft.changed:
                                continue
                            with st.expander(f"{draft.heading} — {draft.words} word(s)",
                                             icon=":material/difference:"):
                                st.markdown(ui.md_safe(ui.clip(draft.text, 1200)) or "_(emptied)_")
                        if counts["emptied"]:
                            st.warning(f"{counts['emptied']} section(s) are empty in the file and would be "
                                       "cleared here. If that is not what you meant, write in them and upload "
                                       "again.", icon=":material/warning:")
                        if st.button("Save these drafts into the outline", type="primary",
                                     icon=":material/save:", key=f"outline_apply_{app_id}"):
                            written = outline_docx.apply(user.id, app_id, drafts, repo)
                            st.session_state["apps_notice"] = (
                                f"Saved {written} section(s) from your Word document.")
                            st.rerun()
        st.divider()

        # ------------------------------------------------ the sections themselves
        for section in outline_sections:
            limit = ""
            if section["limit_pages"]:
                limit = f" :blue-badge[{section['limit_pages']} pages]"
            elif section["limit_words"]:
                limit = f" :blue-badge[{section['limit_words']} words]"
            ticked = set(section["ticked"])
            total = len(section["elements"])
            badge = {"ready": ":green-badge[Ready]", "drafting": ":orange-badge[Drafting]",
                     "not started": ":gray-badge[Not started]"}[section["status"]]
            label = (f"{section['position'] + 1}. {section['heading']}  —  {len(ticked)} of {total} covered"
                     if total else f"{section['position'] + 1}. {section['heading']}")
            with st.expander(label, icon=":material/edit_note:"):
                st.markdown(f"{badge}{limit}")
                if section["purpose"]:
                    st.caption(ui.md_safe(section["purpose"]))
                if section["scored_by"]:
                    st.caption("Judged against: " + ", ".join(ui.md_safe(s) for s in section["scored_by"]))

                if section["elements"]:
                    st.markdown("**What this section must contain**")
                    st.caption("Tick each one when your draft covers it. These come from the funder's own "
                               "wording; hover or read the quote beneath each to check.")
                    chosen = []
                    for i, element in enumerate(section["elements"]):
                        if st.checkbox(element["text"], value=i in ticked,
                                       key=f"oe_{section['id']}_{i}"):
                            chosen.append(i)
                        st.caption(f"“{ui.clip(element['excerpt'], 200)}”")
                    if chosen != sorted(ticked):
                        repo.set_outline_ticks(user.id, section["id"], chosen)
                        st.rerun()
                if section["evidence"]:
                    st.markdown("**Attach or show in this section**")
                    for element in section["evidence"]:
                        st.markdown(f"- {ui.external_md(element['text'])}")

                with st.form(f"outline_response_{section['id']}"):
                    st.markdown("**Your draft for this section**")
                    text = st.text_area("Draft", value=section["response"], height=220,
                                        max_chars=repo.MAX_OUTLINE_RESPONSE_CHARS,
                                        label_visibility="collapsed",
                                        placeholder="Write this section here, or paste what you already have.")
                    status = st.radio("Status", repo.OUTLINE_STATUSES,
                                      index=repo.OUTLINE_STATUSES.index(section["status"]), horizontal=True,
                                      key=f"os_{section['id']}")
                    words = ui.word_count(text)
                    over = section["limit_words"] and words > section["limit_words"]
                    st.caption(f"{words} words" + (f" of {section['limit_words']} — **over the limit**" if over
                                                   else f" of {section['limit_words']}" if section["limit_words"]
                                                   else ""))
                    if st.form_submit_button("Save this section", icon=":material/save:"):
                        try:
                            repo.save_outline_response(user.id, section["id"], text, status=status)
                        except v.ValidationError as err:
                            st.error(str(err), icon=":material/error:")
                        else:
                            st.session_state["apps_notice"] = f"Saved {section['heading']}."
                            st.rerun()
                st.caption("AI drafting is on the **Write answers** tab and works on questions, not outline "
                           "sections yet. What you write here is yours alone: GrantBridge does not change it.")

        # ------------------------------------------------ the rubric, and what your draft covers
        criteria = outline_mod.coverage(payload, ticks) if payload.get("criteria") else []
        scored = [c for c in criteria if c["kind"] != "rollup"]
        if scored:
            st.divider()
            st.markdown("##### How this will be scored, and what you have covered")
            st.markdown(
                "Tick the objectives your draft genuinely addresses. GrantBridge then applies the funder's own "
                "counting rule — it does not judge your writing, predict a score, or guess whether you will be "
                "funded. Anything the funder did not state a rule for is left without a verdict.")
            for row in scored:
                with st.container(border=True, key=f"card-criterion-{row['index']}"):
                    head = f"**{ui.external_md(row['name'])}**"
                    bits = []
                    if row.get("weight_percent"):
                        bits.append(f"{row['weight_percent']}% of the score")
                    if row.get("max_points"):
                        bits.append(f"max {row['max_points']} points")
                    if row["kind"] == "threshold":
                        bits.append("pass or fail")
                    st.markdown(f"{head}" + (f" · {' · '.join(bits)}" if bits else ""))
                    verdict = row["verdict"]
                    if row["total"]:
                        if verdict:
                            colour = "green" if not verdict["shortfall"] else "orange"
                            more = (f" — {verdict['shortfall']} more for **{verdict['next']}**"
                                    if verdict["shortfall"] else "")
                            st.markdown(f":{colour}-badge[{verdict['rating']}] "
                                        f"{row['covered']} of {row['total']} objectives covered{more}")
                            st.caption(f"The funder's rule: {ui.external_md(verdict['rule'])}")
                        else:
                            st.markdown(f":gray-badge[{row['covered']} of {row['total']} covered] "
                                        "The document states no counting rule, so GrantBridge gives no rating.")
                    marked = set(row["marked"])
                    picked = []
                    for i, objective in enumerate(row["objectives"]):
                        if st.checkbox(objective["text"], value=i in marked,
                                       key=f"oc_{row['index']}_{i}"):
                            picked.append(i)
                        st.caption(f"“{ui.clip(objective['excerpt'], 200)}”")
                    if picked != sorted(marked):
                        repo.set_objective_ticks(user.id, app_id, row["index"], picked)
                        st.rerun()
                    if row.get("threshold"):
                        st.caption(f":material/flag: {ui.external_md(row['threshold'])}")

        rollups = [c for c in criteria if c["kind"] == "rollup"]
        if rollups:
            with st.expander("How the ratings combine into an overall result", icon=":material/account_tree:"):
                for row in rollups:
                    st.markdown(f"**{ui.external_md(row['name'])}**")
                    for rule in row.get("rating_rules") or []:
                        st.markdown(f"- **{ui.md_safe(rule['rating'])}**: {ui.external_md(rule['rule'])}")

        # ------------------------------------------------ what must be filed
        components = payload.get("components") or []
        if components:
            st.divider()
            st.markdown("##### What you must file")
            st.markdown("Forms, attachments, certifications and disclosures. Several only apply in certain "
                        "cases, so the funder's own condition is kept with each one — mark the ones that do "
                        "not apply to you rather than deleting them, so the reason stays visible.")
            in_hand = sum(1 for i in range(len(components)) if states.get(str(i)) == "in hand")
            na = sum(1 for i in range(len(components)) if states.get(str(i)) == "not applicable")
            st.caption(f"{in_hand} in hand · {na} marked not applicable · "
                       f"{len(components) - in_hand - na} outstanding")
            for i, component in enumerate(components):
                state = states.get(str(i), "not started")
                with st.container(border=True, key=f"card-component-{i}"):
                    mark = {"in hand": ":green-badge[In hand]", "not applicable": ":gray-badge[Not applicable]",
                            "not started": ":orange-badge[Outstanding]"}[state]
                    st.markdown(f"{mark} :gray-badge[{component['kind']}] "
                                f"**{ui.external_md(component['name'])}**")
                    st.caption("When it applies: " + ui.external_md(component["condition"]))
                    for content in component.get("contents") or []:
                        st.markdown(f"- {ui.external_md(content['text'])}")
                    picked = st.radio("Status", repo.COMPONENT_STATES,
                                      index=repo.COMPONENT_STATES.index(state), horizontal=True,
                                      key=f"cs_{app_id}_{i}", label_visibility="collapsed")
                    if picked != state:
                        repo.set_component_state(user.id, app_id, i, picked)
                        st.rerun()


        # ------------------------------------------------ registrations and format rules
        registrations = payload.get("registrations") or []
        rules = payload.get("format_rules") or []
        if registrations or rules:
            with st.expander("Registrations and format rules", icon=":material/rule:"):
                if registrations:
                    st.markdown("**Register before you can submit**")
                    st.caption("These take real time and are a common reason an application cannot be filed. "
                               "Start them before you start writing.")
                    for registration in registrations:
                        lead = registration.get("lead_time")
                        st.markdown(f"- **{ui.external_md(registration['name'])}**"
                                    + (f" — {ui.external_md(lead)}" if lead else ""))
                        st.caption(f"“{ui.clip(registration['excerpt'], 200)}”")
                if rules:
                    st.markdown("**Format and submission rules**")
                    for rule in rules:
                        st.markdown(f"- {ui.external_md(rule['text'])}")

        if stored_outline:
            with st.expander("Where this outline came from", icon=":material/fact_check:"):
                read_from = payload.get("documents") or []
                st.caption("Read from " + (", ".join(f"**{ui.md_safe(d['name'])}**" for d in read_from) or "—")
                           + (" in practice mode, with fixed text patterns" if payload.get("mode") == "mock"
                              else f" by {ui.md_safe(payload.get('model') or 'the model')}")
                           + f", {stored_outline['updated_at'][:16].replace('T', ' ')}.")
                st.caption("Every section, requirement, objective and rule above had to carry a sentence found "
                           "word for word in that document. Anything GrantBridge could not place there was "
                           "dropped before you saw it.")
                if st.button("Remove this outline", icon=":material/delete:",
                             help="Deletes the outline and its sections. Sections you have written in are kept "
                                  "unless you clear them first."):
                    try:
                        for section in outline_sections:
                            if (section["response"] or "").strip():
                                raise v.ValidationError(
                                    f"“{section['heading']}” has writing in it. Clear the drafts you want to "
                                    "discard first, so an outline can never take your work with it.")
                        repo.delete_application_outline(user.id, app_id)
                    except v.ValidationError as err:
                        st.error(str(err), icon=":material/error:")
                    else:
                        st.session_state["apps_notice"] = "Removed the outline."
                        st.rerun()


# ---------------------------------------------------------------- write answers
def _toggle_tick(section_id: int, item_key: str, widget_key: str) -> None:
    repo.set_tick(user.id, section_id, item_key, bool(st.session_state.get(widget_key)))


def _run(action, *args, **kwargs):
    """Run a drafting step, turning a fallback notice into a page warning."""
    try:
        outcome = action(*args, **kwargs)
    except (v.ValidationError, repo.NotFound) as err:
        st.session_state["apps_warning"] = str(err)
        return None
    if outcome.notice:
        st.session_state["apps_warning"] = outcome.notice
    return outcome


def attention_items(section: dict, facts: list[dict], review: dict | None, stale: bool, ticks: set) -> list[str]:
    """Everything about this answer that a person still has to do, in plain words."""
    answer = section["answer"]
    items = []
    skipped = sum(f["status"] == "skipped" for f in facts)
    if skipped:
        items.append(f"{skipped} fact(s) marked unknown. Drafts leave a [NEEDS: …] placeholder for each.")
    placeholders, markers = drafting.open_markers(answer)
    if placeholders:
        items.append(f"Fill in {len(placeholders)} [NEEDS: …] placeholder(s) in your answer.")
    if markers:
        items.append(f"Resolve {len(markers)} [VERIFY: …] marker(s): figures or names your facts do not support.")
    limit = ui.word_limit(section["question"])
    if limit and ui.word_count(answer) > limit:
        items.append(f"Cut the answer to {limit} words (it has {ui.word_count(answer)}).")
    if answer.strip() and review is None:
        items.append("Not reviewed yet: press **Review my answer** when it is ready.")
    elif review is not None and stale:
        items.append("Your answer changed since its last review: review it again.")
    elif review is not None:
        open_items = sum(i["key"] not in ticks for i in review["payload"]["checklist"])
        if open_items:
            items.append(f"Confirm {open_items} verification item(s) below, after checking each one yourself.")
    return items


with write_tab:
    st.markdown("##### Answer the funder's questions, with AI help")
    st.markdown(
        "This tab is for grants that ask numbered questions. Pick a question, let GrantBridge find the facts "
        "it would need from your records, draft an answer from those facts alone, and review it. **Every AI "
        "suggestion is a suggestion:** your answer does not change until you press the button that uses it.")
    st.info(
        "**Writing to a prescribed outline instead?** Many solicitations name the sections you must write "
        "rather than asking questions. Those live on the **Proposal outline** tab, with each section's "
        "requirements, its limits and the rubric it is scored against — and you can download that outline as "
        "a Word document, write in it, and upload it back.", icon=":material/alt_route:")

    if not sections:
        c.empty_state(":material/help:", "This application has no questions yet",
                      "Add the funder's questions on the **Requirements & source** tab: paste them all at once, or "
                      "type them one at a time.", key="no-questions")
    else:
        statuses ={s.id: drafting.section_status(user.id, {"id": s.id, "answer": s.answer}) for s in sections}
        by_sid = {s.id: s for s in sections}
        # Labels must not change between reruns (no status in them): Streamlit matches the browser's
        # selection by label, and a changed label silently resets the choice to the first question.
        sid = st.selectbox(
            "Question", [s.id for s in sections], key=f"section_pick_{app_id}",
            format_func=lambda i: f"{by_sid[i].position + 1}. {ui.clip(by_sid[i].question, 90)}",
        )
        section = repo.get_section(user.id, sid)
        status = statuses[sid]
        st.markdown(f"#### {section['position'] + 1}. {ui.external_md(section['question'])}")
        st.markdown(f":{STATUS_COLORS[status['code']]}-badge[{status['label']}]")
        if requirements:
            with st.expander(f"Requirements this answer is reviewed against ({len(requirements)})"):
                st.markdown("\n".join(f"- {ui.external_md(r['text'])}" for r in requirements))

        facts = repo.list_section_facts(user.id, sid)
        review = repo.latest_review(user.id, sid)
        stale = bool(review) and review["answer_hash"] != drafting.answer_hash(section["answer"])
        ticks = repo.list_ticks(user.id, sid) if review else set()
        todo = attention_items(section, facts, review, stale, ticks)
        if todo:
            st.warning("**Needs your attention**\n" + "\n".join(f"- {ui.md_safe(t)}" for t in todo),
                       icon=":material/priority_high:")
        elif status["code"] == "ready":
            st.success("Ready for your final read: reviewed after your last edit, with every item confirmed.",
                       icon=":material/task_alt:")

        answer_col, help_col = st.columns([3, 2], gap="large")

        # The user's own answer: nothing else ever writes to it without a click.
        with answer_col:
            st.markdown("##### Your answer")
            versions = repo.list_versions(user.id, sid)
            editor_key = f"answer_{sid}_{len(versions)}_{versions[0]['id'] if versions else 0}"
            text = st.text_area("Your answer", value=section["answer"], height=320, max_chars=repo.MAX_ANSWER_CHARS,
                                key=editor_key, label_visibility="collapsed",
                                placeholder="Write here, or use the AI help on the right to draft a suggestion first.")
            limit = ui.word_limit(section["question"])
            count = ui.word_count(text)
            unsaved = text != section["answer"]
            st.caption(f"{count}{f' / {limit}' if limit else ''} words"
                       + (" · over the limit" if limit and count > limit else "")
                       + (" · :orange[unsaved changes]" if unsaved else " · saved"))
            # Always clickable: Streamlit commits typed text when the box loses focus, so a button that was
            # disabled until then would swallow the user's first click.
            with st.container(horizontal=True):
                if st.button("Save answer", key=f"save_{sid}", type="primary", icon=":material/save:"):
                    try:
                        changed = repo.save_section_answer(user.id, sid, text)
                    except v.ValidationError as err:
                        st.error(str(err), icon=":material/error:")
                    else:
                        st.session_state["apps_notice"] = ("Answer saved. Earlier versions are kept in the history."
                                                           if changed else "No changes to save.")
                        st.rerun()
                if st.button("Review my answer", key=f"review_{sid}", icon=":material/rule:",
                             help="Saves any unsaved edits as a new version, then reviews exactly what you see."):
                    try:
                        repo.save_section_answer(user.id, sid, text)
                    except v.ValidationError as err:
                        st.session_state["apps_warning"] = str(err)
                    else:
                        with st.spinner("Reviewing against the requirements…"):
                            _run(drafting.review_answer, user.id, sid, want_mock=mock_on)
                    st.rerun()
            if versions:
                with st.expander(f"Version history ({len(versions)})", icon=":material/history:"):
                    for i, ver in enumerate(versions):
                        c1, c2 = st.columns([5, 1], vertical_alignment="center")
                        c1.markdown(f"**{ver['created_at'].replace('T', ' ')[:16]} UTC** · {ver['source']}"
                                    + (" · current" if i == 0 else "")
                                    + f"  \n{ui.external_md(ui.clip(ver['text'], 160))}")
                        if i and c2.button("Restore", key=f"restore_{ver['id']}"):
                            repo.restore_version(user.id, sid, ver["id"])
                            st.session_state["apps_notice"] = ("Version restored. The text it replaced is still in "
                                                               "the history.")
                            st.rerun()

        # AI help: facts first, then a suggested draft. Suggestions only.
        with help_col:
            with st.container(border=True, key="card-ai-help"):
                st.markdown("##### AI help")
                st.caption("Find the facts this answer needs, then draft a suggestion from them. Nothing changes "
                           "your answer until you choose **Use this draft**. "
                           + ("Practice mode is on (no AI)." if mock_on else "Uses the AI; switch to practice mode "
                                                                            "above to try it for free."))
                st.markdown("**Step 1 · Facts for this answer**")
                st.caption("The AI may use only your Organization Profile and the facts you give here. If you do "
                           "not know something, skip it: the draft will leave a [NEEDS: …] placeholder.")
                if not facts:
                    st.caption(":material/manage_search: No fact questions yet. Press **Find missing facts** to see "
                               "what this answer needs.")
                pending = [f for f in facts if f["status"] == "pending"]
                for f in facts:
                    with st.chat_message("assistant", avatar=":material/help:"):
                        st.markdown(f["prompt"])
                    if f["status"] == "answered":
                        with st.chat_message("user"):
                            st.markdown(ui.md_safe(f["answer"]))
                    elif f["status"] == "skipped":
                        with st.chat_message("user"):
                            st.caption("Skipped: unknown. The draft will leave a placeholder.")
                    if pending and f["id"] == pending[0]["id"]:
                        with st.form(f"fact_{f['id']}", clear_on_submit=True):
                            reply = st.text_area("Your reply to this question", max_chars=repo.MAX_FACT_CHARS,
                                                 height=90)
                            b1, b2 = st.columns(2)
                            save = b1.form_submit_button("Send reply", type="primary", icon=":material/send:")
                            skip = b2.form_submit_button("I don't know (skip)", icon=":material/skip_next:")
                        if save or skip:
                            try:
                                repo.answer_section_fact(user.id, f["id"], None if skip else reply)
                            except v.ValidationError as err:
                                st.error(str(err), icon=":material/error:")
                            else:
                                st.rerun()
                        break  # later pending questions wait their turn
                with st.container(horizontal=True):
                    if st.button("Find missing facts", key=f"plan_{sid}", icon=":material/manage_search:"):
                        with st.spinner("Checking what this answer needs…"):
                            out = _run(drafting.plan_facts, user.id, sid, want_mock=mock_on)
                        if out:
                            cost = ui.usage_line(out.data.get("usage")) if out.mode == "live" else ""
                            st.session_state["apps_notice"] = (
                                (f"{len(out.data['added'])} new fact question(s)." if out.data["added"]
                                 else "No new facts needed right now.") + (f" AI use: {cost}." if cost else ""))
                        st.rerun()
                    with st.popover("Add a fact of your own", icon=":material/add_comment:"):
                        with st.form(f"own_fact_{sid}", clear_on_submit=True):
                            own = st.text_area("Fact", max_chars=repo.MAX_FACT_CHARS, height=90,
                                               placeholder="e.g. Our program director, Dana Reyes, has led it since 2019.")
                            if st.form_submit_button("Add fact", icon=":material/add:"):
                                try:
                                    repo.add_section_fact(user.id, sid, "A fact you added", answer=own,
                                                          status="answered")
                                except v.ValidationError as err:
                                    st.error(str(err), icon=":material/error:")
                                else:
                                    st.rerun()

                st.markdown("**Step 2 · Suggested draft**")
                if st.button("Draft this answer", key=f"draft_{sid}", type="primary", icon=":material/edit_note:"):
                    with st.spinner("Drafting from your facts…"):
                        _run(drafting.draft_section, user.id, sid, want_mock=mock_on)
                    st.rerun()
                draft = repo.latest_draft(user.id, sid)
                if draft:
                    flags = draft["payload"]["flags"]
                    used = any(ver["source"] == "ai draft" and ver["text"].strip() == draft["text"].strip()
                               for ver in versions)
                    with st.container(border=True, key="card-draft"):
                        kind = {"revision": "REVISION", "budget narrative": "BUDGET NARRATIVE"}.get(
                            draft["payload"].get("kind"), "DRAFT")
                        label = (f":gray-badge[MOCK {kind} · practice mode, no AI]" if draft["mode"] == "mock" else
                                 f":violet-badge[:material/smart_toy: AI {kind} · gpt-6-luna]")
                        state = (":green-badge[:material/check: Used in your answer]" if used else
                                 ":blue-badge[Suggestion only: not in your answer until you use it]")
                        st.markdown(f"{label} {state}")
                        if kind == "REVISION":
                            st.caption("A revision of your answer that follows this review feedback: "
                                       + ui.md_safe(draft["payload"].get("feedback", "")))
                        st.markdown(ui.md_safe(draft["text"]))
                        limit_text = f" of {flags['word_limit']}" if flags["word_limit"] else ""
                        st.caption(f"{flags['word_count']}{limit_text} words"
                                   + (" · over the limit" if flags["over_limit"] else ""))
                        if draft["mode"] == "live" and draft["payload"].get("usage"):
                            st.caption(ui.usage_line(draft["payload"]["usage"]))
                        if flags["flagged"]:
                            st.warning("Marked [VERIFY] because your profile and facts do not contain them: "
                                       + ", ".join(ui.md_safe(x) for x in flags["flagged"]),
                                       icon=":material/fact_check:")
                        if flags["placeholders"]:
                            st.info("Missing facts left as placeholders: " + ", ".join(flags["placeholders"]),
                                    icon=":material/edit:")
                        if flags["injection_signals"]:
                            st.warning("The funder text contains wording aimed at AI tools. It was treated as plain "
                                       "text.", icon=":material/shield:")
                        with st.container(horizontal=True):
                            if not used and st.button("Use this draft as my answer", key=f"use_{sid}", type="primary",
                                                      icon=":material/input:",
                                                      help="Your current answer is kept in the version history."):
                                drafting.use_draft(user.id, sid, draft["id"])
                                st.session_state["apps_notice"] = ("Draft copied into your answer. Your previous text "
                                                                   "is in the version history.")
                                st.rerun()
                            if st.button("Dismiss draft" if used else "Discard draft", key=f"discard_{sid}",
                                         icon=":material/delete:"):
                                repo.delete_drafts(user.id, sid)
                                st.rerun()
                        if used:
                            st.caption("This draft is now your answer. Edit it on the left; earlier text is in the "
                                       "version history.")

        # Review and verification: what a person must still confirm.
        st.markdown("##### Review and verify")
        if review is None:
            st.caption(":material/rule: No review yet. When your answer is ready, press **Review my answer**: it checks "
                       "the answer against the question and requirements and lists what you must verify.")
        else:
            p = review["payload"]
            with st.container(border=True, key="card-review"):
                st.markdown(":gray-badge[MOCK REVIEW · practice mode, keyword matching, no AI]" if review["mode"] == "mock"
                            else ":violet-badge[:material/smart_toy: AI REVIEW · gpt-6-luna, checked by code]")
                if stale:
                    st.warning("Your answer changed since this review. Review it again before relying on these "
                               "results.", icon=":material/update:")
                st.markdown(ui.md_safe(p["summary"]))
                for r in p["requirements"]:
                    mark = {"met": ":green[:material/check_circle:]", "partly": ":orange[:material/timelapse:]"}.get(
                        r["status"], ":red[:material/cancel:]")
                    quote = f'  \n_Evidence:_ "{ui.md_safe(r["evidence_quote"])}"' if r["evidence_quote"] else ""
                    st.markdown(f"{mark} **{REQUIREMENT_STATUS.get(r['status'], r['status'])}:** "
                                f"{ui.md_safe(r['requirement'])}  \n{ui.md_safe(r['note'])}{quote}")
                if p["findings"]["unsupported_numbers"] or p["findings"]["unrecognized_names"]:
                    st.warning("Not found in your profile or facts: "
                               + ", ".join(ui.md_safe(x) for x in p["findings"]["unsupported_numbers"]
                                           + p["findings"]["unrecognized_names"]), icon=":material/fact_check:")
                if p["claims"]:
                    st.markdown("**Statements the review could not support**\n"
                                + "\n".join(f'- "{ui.md_safe(cl["quote"])}": {cl["why"]}' for cl in p["claims"]))
                if p["missing_evidence"]:
                    st.markdown("**Missing evidence**\n" + "\n".join(f"- {ui.md_safe(e)}" for e in p["missing_evidence"]))
                if review["mode"] == "live" and p.get("usage"):
                    st.caption(ui.usage_line(p["usage"]))

            items = p["checklist"]
            done = sum(i["key"] in ticks for i in items)
            with st.container(border=True, key="card-checklist"):
                st.markdown(f"**:material/fact_check: Needs human verification** · {done} of {len(items)} confirmed")
                st.caption("Tick an item only after you have checked it yourself. GrantBridge cannot verify these "
                           "for you.")
                for item in items:
                    widget = f"tick_{sid}_{item['key']}"
                    st.checkbox(ui.md_safe(item["text"]), value=item["key"] in ticks, key=widget,
                                on_change=_toggle_tick, args=(sid, item["key"], widget), disabled=stale)

# ---------------------------------------------------------------- review the whole proposal
FUNDER = proposal_review.FUNDER


def _rating_text(rating) -> str:
    return "—" if rating is None else f"{rating:g} / 5"


def _change_text(change) -> str:
    """Words and arrows, not color alone."""
    if change is None:
        return "—"
    change = round(change, 1)
    return f"▲ up {change:g}" if change > 0 else f"▼ down {-change:g}" if change < 0 else "no change"


def _edit_lines(edits: list[dict]) -> str:
    return "\n".join(f"- {'Added' if e['change'] == 'added' else 'Removed'}: {ui.external_md(ui.clip(e['text'], 220))}"
                     for e in edits)


def _pending_revisions() -> list[tuple[int, object, dict]]:
    """(question number, section, draft) for each revision suggestion that is not in the answer yet."""
    pending = []
    for n, s in enumerate(sections, 1):
        d = repo.latest_draft(user.id, s.id)
        if d and d["payload"].get("kind") == "revision" and d["text"].strip() != s.answer.strip():
            pending.append((n, s, d))
    return pending


with review_tab:
    if not sections:
        c.empty_state(":material/rate_review:", "Nothing to review yet",
                      "Add the funder's questions on the **Requirements & source** tab, then write or draft your "
                      "answers. The review rates the whole application at once.", key="review-no-questions")
    else:
        reviews = repo.list_proposal_reviews(user.id, app_id)
        latest = reviews[0] if reviews else None
        with st.container(border=True, key="card-proposal-review"):
            st.markdown("##### Review my proposal")
            st.caption("Rates the whole application on clarity, specificity, alignment, evidence of impact, and "
                       "completeness, lists what is missing or unsupported, and orders the improvements. It reads "
                       "your saved answers and never changes them.")
            if st.button("Review my proposal", key=f"proposal_review_{app_id}", type="primary",
                         icon=":material/rate_review:",
                         help="Practice mode uses fixed rules and is free. Otherwise it makes one AI call, and code "
                              "checks the result."):
                with st.spinner("Reviewing every answer…"):
                    out = _run(proposal_review.review_proposal, user.id, app_id, want_mock=mock_on)
                if out:
                    cost = ui.usage_line(out.data.get("usage")) if out.mode == "live" else ""
                    st.session_state["apps_notice"] = "Proposal review saved." + (f" AI use: {cost}." if cost else "")
                st.rerun()
            st.caption(":material/info: " + proposal_review.ADVISORY_NOTE)

        if latest is None:
            st.caption(":material/rate_review: No proposal review yet. When your answers are ready, press **Review "
                       "my proposal**. You can review again after each round of edits to see what improved.")
        else:
            p, t = latest["payload"], latest["payload"]["totals"]
            snapshot_sections = latest["snapshot"]["sections"]
            current = proposal_review.is_current(user.id, app_id, latest)
            with st.container(border=True, key="card-proposal-scorecard"):
                badge = (":gray-badge[MOCK REVIEW · practice mode, fixed rules, no AI]" if latest["mode"] == "mock"
                         else ":violet-badge[:material/smart_toy: AI REVIEW · gpt-6-luna, checked by code]")
                fresh = (":green-badge[:material/check: Matches your saved answers]" if current else
                         ":orange-badge[:material/update: Your answers changed since this review]")
                st.markdown(f"{badge} {fresh}")
                st.caption(f"Reviewed {latest['created_at'].replace('T', ' ')[:16]} UTC"
                           + (f" · {ui.usage_line(p['usage'])}" if latest["mode"] == "live" and p.get("usage") else "")
                           + (f" · Why practice mode: {ui.md_safe(p['notice'])}" if p.get("notice") else ""))
                st.markdown(ui.md_safe(p["summary"]))
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Average rating (advisory)", _rating_text(p["overall"]), border=True,
                          help=proposal_review.ADVISORY_NOTE)
                m2.metric("Questions answered", f"{t['answered']} of {t['questions']}", border=True)
                m3.metric("Not in your records", t["unsupported"], border=True,
                          help="Figures or names in your answers that your profile and facts do not contain "
                               "(code check).")
                m4.metric("Open markers", t["placeholders"] + t["verify_markers"], border=True,
                          help="[NEEDS: …] placeholders and [VERIFY: …] markers still in your answers (code check).")
                for d in p["dimensions"]:
                    with st.container(border=True, key=f"card-dimension-{c.slug(d['dimension'])}"):
                        name_col, why_col = st.columns([1, 3], gap="medium")
                        with name_col:
                            st.markdown(f"**{d['dimension'].capitalize()}**",
                                        help=proposal_review.DIMENSION_HELP[d["dimension"]])
                            if d["rating"] is None:
                                st.markdown(":gray-badge[Not assessed]")
                            else:
                                st.progress(d["rating"] / 5, text=f"{d['rating']} / 5 · {d['label']}")
                        with why_col:
                            st.markdown(ui.md_safe(d["explanation"]))
                            if d["cap"]:
                                st.markdown(f":orange[:material/vertical_align_top:] **Capped by code at "
                                            f"{d['cap']['to']}** (the reviewer gave {d['cap']['from']}): "
                                            f"{ui.md_safe(d['cap']['reason'])}")
                            if d["based_on"]:
                                st.caption(("Funder requirement · " if d["basis"] == FUNDER else "Best practice · ")
                                           + ui.external_md(d["based_on"]))

            st.markdown("##### What to improve first")
            if not p["recommendations"]:
                st.caption("This review has no recommendations.")
            answers_now = {s.id: s.answer for s in sections}
            for i, r in enumerate(p["recommendations"], 1):
                q = r["question"]
                target = snapshot_sections[q - 1]["id"] if q and q <= len(snapshot_sections) else None
                with st.container(border=True, key=f"card-recommendation-{i}"):
                    where = f":blue-badge[Question {q}]" if q else ":gray-badge[Whole proposal]"
                    basis = (":green-badge[:material/verified: Funder requirement]" if r["basis"] == FUNDER
                             else ":gray-badge[Best practice]")
                    st.markdown(f"{PRIORITY_BADGES[r['priority']]} {where} {basis}")
                    st.markdown(f"**{i}. {ui.md_safe(r['action'])}**  \n{ui.md_safe(r['why'])}")
                    if r["requirement"]:
                        st.caption(f"{ui.md_safe(r['source'])}: “{ui.external_md(r['requirement'])}”")
                    else:
                        st.caption("General grant-writing practice. This funder's text in GrantBridge does not "
                                   "state it.")
                    if target and answers_now.get(target, "").strip() and st.button(
                            f"Revise question {q} with {'practice rules' if mock_on else 'AI'}",
                            key=f"revise_{latest['id']}_{i}", icon=":material/auto_fix_high:",
                            help="Creates a suggested revision. Your answer does not change until you choose to "
                                 "use it."):
                        with st.spinner("Writing a suggested revision…"):
                            out = _run(drafting.revise_section, user.id, target, f"{r['action']} {r['why']}",
                                       want_mock=mock_on)
                        if out and out.data["unchanged"]:
                            notes = " ".join(ui.md_safe(x) for x in out.data["changes"])
                            fallback = st.session_state.get("apps_warning")
                            st.session_state["apps_warning"] = (
                                (f"{fallback} " if fallback else "")
                                + f"The reviser suggested no changes to question {q}" + (f": {notes}" if notes else ".")
                                + " Add the missing details to the answer or its facts, then revise again.")
                        elif out:
                            st.session_state["apps_notice"] = (f"A suggested revision of question {q} is ready under "
                                                               "**Suggested revisions** below. Your answer has not "
                                                               "changed.")
                        st.rerun()

            gaps_col, claims_col = st.columns(2, gap="medium")
            questions_by_n = {i + 1: s["question"] for i, s in enumerate(snapshot_sections)}
            with gaps_col, st.container(border=True, key="card-review-missing"):
                st.markdown("##### Missing or unanswered")
                lines = [f"- **Question {n} has no answer:** {ui.external_md(ui.clip(questions_by_n.get(n, ''), 110))}"
                         for n in p["unanswered"]]
                lines += [f"- **Question {g['question']} does not yet cover:** {ui.md_safe(g['gap'])}"
                          for g in p["unanswered_parts"]]
                lines += [f"- {ui.md_safe(m['text'])} _({'AI' if m['source'] == 'ai' else 'code check'})_"
                          for m in p["missing_information"]]
                st.markdown("\n".join(lines) if lines else "Nothing missing was found.")
            with claims_col, st.container(border=True, key="card-review-claims"):
                st.markdown("##### Statements to check")
                code_lines = [f"- **Question {q['question']}:** "
                              + ", ".join(ui.external_md(x) for x in q["unsupported_figures"] + q["unrecognized_names"])
                              for q in p["findings"]["questions"] if q["unsupported_figures"] or q["unrecognized_names"]]
                if code_lines:
                    st.markdown("**Not in your profile or facts** _(code check)_\n" + "\n".join(code_lines))
                if p["unsupported_claims"]:
                    st.markdown("**Statements the review could not support** _(AI, quoted from your answers)_\n"
                                + "\n".join(f'- **Question {cl["question"]}:** "{ui.external_md(cl["quote"])}" '
                                            f'{ui.md_safe(cl["why"])}' for cl in p["unsupported_claims"]))
                if not code_lines and not p["unsupported_claims"]:
                    st.markdown("No unsupported statements were found.")
                if p["findings"]["injection_signals"]:
                    st.warning("The funder text contains wording aimed at AI tools. The review treated it as plain "
                               "text and did not follow it.", icon=":material/shield:")

            with st.container(border=True, key="card-review-compliance"):
                st.markdown("##### The funder's requirements, one by one")
                checklist = p.get("compliance") or []
                if not checklist:
                    st.caption("No funder requirements have been entered for this application yet. Import the "
                               "solicitation with **New application** above, or add them on the **Requirements & "
                               "source** tab, and the next review will check your answers against each one.")
                else:
                    st.caption("A requirement counts as addressed only when the review can quote the sentence in "
                               "your own answer that covers it. Whether you are eligible to apply at all is a "
                               "different question, answered on **Should We Pursue?** against your profile.")
                    tally = Counter(row["status"] for row in checklist)
                    st.markdown(" ".join(
                        f":{proposal_review.COMPLIANCE_COLORS[s]}-badge[{tally[s]} "
                        f"{proposal_review.COMPLIANCE_LABELS[s].lower()}]"
                        for s in proposal_review.COMPLIANCE if tally[s]))
                    for row in checklist:
                        status = row["status"]
                        with st.container(border=True, key=f"row-compliance-{c.slug(row['requirement'])[:40]}"):
                            st.markdown(
                                f":{proposal_review.COMPLIANCE_COLORS[status]}-badge"
                                f"[{proposal_review.COMPLIANCE_LABELS[status]}] "
                                + (f":blue-badge[Question {row['question_number']}]"
                                   if row["question_number"] else ""))
                            st.markdown(f"**{ui.external_md(ui.clip(row['requirement'], 300))}**")
                            if row["evidence_quote"]:
                                st.markdown("> " + ui.external_md(ui.clip(row["evidence_quote"], 300)))
                            if row["note"]:
                                st.caption(ui.md_safe(row["note"]))
                    if p["rules"].get("compliance_downgraded"):
                        st.caption(f"{p['rules']['compliance_downgraded']} requirement(s) the review called covered "
                                   "were moved to **not found**, because it could not quote a sentence in your "
                                   "answers that covers them.")

            with st.expander("Checked by code (no AI): question by question", icon=":material/fact_check:"):
                st.dataframe(
                    [{"Question": q["question"], "Answered": "yes" if q["answered"] else "no",
                      "Words": q["word_count"], "Limit": str(q["word_limit"]) if q["word_limit"] else "—",
                      "Over the limit": "yes" if q["over_limit"] else "no",
                      "[NEEDS] or [VERIFY]": len(q["placeholders"]) + len(q["verify_markers"]),
                      "Not in your records": len(q["unsupported_figures"]) + len(q["unrecognized_names"])}
                     for q in p["findings"]["questions"]], hide_index=True, width="stretch")
                rules = p["rules"]
                st.caption(f"Rules applied to this review: {rules['caps_applied']} rating(s) capped, "
                           f"{rules['recs_relabeled']} recommendation(s) relabeled as best practice, "
                           f"{rules['quotes_dropped']} quote(s) dropped because they were not in your answers, "
                           f"{rules['predictions_removed']} funding prediction(s) removed, and "
                           f"{rules['figures_replaced']} unsupported figure(s) replaced.")
                st.markdown("**Requirements this review may cite** (everything else counts as best practice)\n"
                            + "\n".join(f"- {ui.md_safe(item['source'])}: {ui.external_md(ui.clip(item['text'], 160))}"
                                        for item in p["requirements"]))

        pending = _pending_revisions()
        if pending:
            st.markdown("##### Suggested revisions: before and after")
        for n, s, d in pending:
            with st.container(border=True, key=f"card-revision-{s.id}"):
                label = (":gray-badge[MOCK REVISION · practice mode, no AI]" if d["mode"] == "mock"
                         else ":violet-badge[:material/smart_toy: AI REVISION · gpt-6-luna]")
                st.markdown(f"{label} :blue-badge[Question {n}] "
                            ":blue-badge[Suggestion only: your answer has not changed]")
                st.caption("Follows this feedback: " + ui.md_safe(d["payload"].get("feedback", "")))
                before_col, after_col = st.columns(2, gap="medium")
                with before_col:
                    st.markdown("**Before: your saved answer**")
                    st.markdown(ui.external_md(s.answer))
                    st.caption(f"{ui.word_count(s.answer)} words")
                with after_col:
                    st.markdown("**After: the suggestion**")
                    st.markdown(ui.md_safe(d["text"]))
                    limit_text = f" of {d['payload']['flags']['word_limit']}" if d["payload"]["flags"]["word_limit"] else ""
                    st.caption(f"{d['payload']['flags']['word_count']}{limit_text} words")
                edits = proposal_review.sentence_changes(s.answer, d["text"])
                if edits:
                    st.markdown("**What changed**\n" + _edit_lines(edits))
                if d["payload"]["flags"]["flagged"]:
                    st.warning("Marked [VERIFY] because your profile and facts do not contain them: "
                               + ", ".join(ui.md_safe(x) for x in d["payload"]["flags"]["flagged"]),
                               icon=":material/fact_check:")
                if d["payload"].get("changes"):
                    st.caption("The reviser's notes: " + " · ".join(ui.md_safe(x) for x in d["payload"]["changes"]))
                if d["mode"] == "live" and d["payload"].get("usage"):
                    st.caption(ui.usage_line(d["payload"]["usage"]))
                with st.container(horizontal=True):
                    if st.button("Use this revision as my answer", key=f"use_revision_{d['id']}", type="primary",
                                 icon=":material/input:", help="Your current answer is kept in the version history."):
                        drafting.use_draft(user.id, s.id, d["id"])
                        st.session_state["apps_notice"] = (f"Revision copied into question {n}. Your previous text is "
                                                           "in the version history. Review the proposal again to see "
                                                           "what changed.")
                        st.rerun()
                    if st.button("Discard revision", key=f"discard_revision_{d['id']}", icon=":material/delete:"):
                        repo.delete_drafts(user.id, s.id)
                        st.rerun()

        if len(reviews) >= 2:
            diff = proposal_review.compare(reviews[1], reviews[0])
            with st.expander(f"Before and after: compared with your review from "
                             f"{diff['previous_at'].replace('T', ' ')[:16]} UTC", expanded=True,
                             icon=":material/compare_arrows:"):
                if not diff["same_mode"]:
                    st.info("These two reviews ran in different modes (practice rules and AI), so a rating change "
                            "may come from the reviewer rather than from your edits.", icon=":material/info:")
                overall = diff["overall"]
                st.dataframe(
                    [{"Dimension": d["dimension"].capitalize(), "Before": _rating_text(d["before"]),
                      "After": _rating_text(d["after"]), "Change": _change_text(d["change"])}
                     for d in diff["dimensions"]]
                    + [{"Dimension": "Average (advisory)", "Before": _rating_text(overall["before"]),
                        "After": _rating_text(overall["after"]),
                        "Change": _change_text(None if None in (overall["before"], overall["after"])
                                               else overall["after"] - overall["before"])}],
                    hide_index=True, width="stretch")
                st.dataframe([{"Code check": x["label"], "Before": x["before"], "After": x["after"]}
                              for x in diff["counts"].values()], hide_index=True, width="stretch")
                for ch in diff["changed"]:
                    st.markdown(f"**Question {ch['question']}** · {ch['before_words']} → {ch['after_words']} words")
                    st.markdown(_edit_lines(ch["edits"]) or "- Wording changed within sentences.")
                if not diff["changed"]:
                    st.caption("No answer changed between these two reviews.")
            with st.expander(f"Review history ({len(reviews)})", icon=":material/history:"):
                st.dataframe(
                    [{"Reviewed (UTC)": r["created_at"].replace("T", " ")[:16],
                      "Mode": "AI" if r["mode"] == "live" else "Practice (no AI)",
                      "Average (advisory)": _rating_text(r["payload"]["overall"]),
                      "Answered": f"{r['payload']['totals']['answered']} of {r['payload']['totals']['questions']}"}
                     for r in reviews], hide_index=True, width="stretch")

# ---------------------------------------------------------------- budget and narrative
SOURCE_CODES = list(v.FUNDING_SOURCES)


def budget_form(key: str, item: dict | None = None) -> dict | None:
    """The fields of one budget line. Returns the entered values when the form is submitted."""
    item = item or {}
    with st.form(key, clear_on_submit=item == {}):
        c1, c2 = st.columns([1, 2])
        category = c1.selectbox("Category", v.BUDGET_CATEGORIES, key=f"{key}-category",
                                index=v.BUDGET_CATEGORIES.index(item.get("category", "Personnel")))
        description = c2.text_input("Description *", value=item.get("description", ""), max_chars=200,
                                    key=f"{key}-description",
                                    placeholder="e.g. Volunteer coordinator (part time)")
        c3, c4, c5 = st.columns(3)
        quantity = c3.number_input("Quantity *", min_value=0.0, max_value=1_000_000.0, step=1.0, format="%.2f",
                                   value=float(item.get("quantity", 1)), key=f"{key}-quantity")
        unit = c4.text_input("Unit", value=item.get("unit", ""), max_chars=30, placeholder="e.g. FTE, hours, kits",
                             key=f"{key}-unit")
        unit_cost = c5.number_input("Unit cost (USD) *", min_value=0.0, max_value=10_000_000.0, step=1.0,
                                    format="%.2f", value=item.get("unit_cost_cents", 0) / 100, key=f"{key}-unit_cost")
        c6, c7 = st.columns(2)
        source = c6.selectbox("Paid by *", SOURCE_CODES, format_func=v.FUNDING_SOURCES.get,
                              index=SOURCE_CODES.index(item.get("funding_source", "grant")), key=f"{key}-source",
                              help="Only you know whether a match is committed. The narrative calls pending money "
                                   "pending.")
        source_name = c7.text_input("Who provides it (for a match or other funding)", max_chars=120,
                                    key=f"{key}-source_name",
                                    value=item.get("source_name", ""), placeholder="e.g. a local foundation")
        justification = st.text_area("Justification: why this cost is needed", value=item.get("justification", ""),
                                     max_chars=1000, height=80, key=f"{key}-justification",
                                     placeholder="e.g. Recruits, trains, and schedules 20 new volunteer tutors.")
        if st.form_submit_button("Save line" if item else "Add line", type="primary",
                                 icon=":material/save:" if item else ":material/add:"):
            return {"category": category, "description": description, "quantity": quantity, "unit": unit,
                    "unit_cost": unit_cost, "funding_source": source, "source_name": source_name,
                    "justification": justification}
    return None


def _save_line(action, *args) -> None:
    try:
        action(*args)
    except (v.ValidationError, repo.NotFound) as err:
        st.error(str(err), icon=":material/error:")
    else:
        st.session_state["apps_notice"] = "Budget saved. The totals and checks are updated."
        st.rerun()


with budget_tab:
    b = budget.summarize(user.id, app_id)
    checks = b.checks()
    narrative = repo.latest_budget_narrative(user.id, app_id)
    st.markdown("##### Budget & narrative")
    st.caption("Enter each cost once. GrantBridge does all the arithmetic and checks the totals; the AI only "
               "describes the lines you entered. Never enter a match or commitment you do not have.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total budget", budget.usd(b.total_cents), border=True)
    m2.metric("Requested from this grant", budget.usd(b.requested_cents), border=True,
              help="The lines paid by this grant, added up by code.")
    m3.metric("Committed match & other", budget.usd(b.committed_cents), border=True,
              help="Cash and in-kind matches and other funding that you marked committed.")
    m4.metric("Pending match & other", budget.usd(b.pending_cents), border=True,
              help="Cash and in-kind matches and other funding that you marked pending: not yet confirmed.")
    asked = b.amount_requested_cents
    if asked is not None and asked == b.requested_cents and b.lines:
        st.success(f"The lines charged to this grant match the amount requested on the Details tab "
                   f"({budget.usd(asked)}).", icon=":material/check_circle:")
    for check in checks:
        if check["level"] == "warning":
            st.warning(ui.md_safe(check["text"]), icon=":material/warning:")
        else:
            st.info(ui.md_safe(check["text"]), icon=":material/info:")

    with st.container(border=True, key="card-budget-lines"):
        st.markdown(f"**Budget lines ({len(b.lines)})**")
        if not b.lines:
            st.caption("No lines yet. Add the first one below: what it is, how many, the cost of one, and who pays.")
        for line in b.lines:
            text_col, edit_col, remove_col = st.columns([6, 1, 1], vertical_alignment="center")
            amount = f"{line['quantity']} {ui.md_safe(line['unit'])}".strip()
            source = line["source_label"] + (f" ({ui.md_safe(line['source_name'])})" if line["source_name"] else "")
            justification = (ui.md_safe(line["justification"]) if line["justification"].strip()
                             else ":orange-badge[:material/warning: No justification yet]")
            text_col.markdown(f"**{line['number']}. {ui.md_safe(line['description'])}** · {line['category']}  \n"
                              f"{amount} × {ui.md_safe(budget.usd(line['unit_cost_cents']))} = "
                              f"**{ui.md_safe(budget.usd(line['total_cents']))}** · {source}  \n{justification}")
            with edit_col.popover("Edit", icon=":material/edit:", width="stretch"):
                entered = budget_form(f"budget_edit_{line['id']}", line)
                if entered is not None:
                    _save_line(repo.update_budget_item, user.id, line["id"], entered)
            if remove_col.button("Remove", key=f"budget_remove_{line['id']}", type="tertiary",
                                 icon=":material/delete:"):
                repo.delete_budget_item(user.id, line["id"])
                st.session_state["apps_notice"] = f"Removed line {line['number']}."
                st.rerun()
        if b.lines:
            sub_col, src_col = st.columns(2, gap="medium")
            sub_col.markdown("**By category**\n\n| Category | Subtotal |\n|---|---:|\n"
                             + "\n".join(f"| {cat} | {ui.md_safe(budget.usd(c))} |" for cat, c in b.by_category.items())
                             + f"\n| **Total** | **{ui.md_safe(budget.usd(b.total_cents))}** |")
            src_col.markdown("**By who pays**\n\n| Paid by | Amount |\n|---|---:|\n"
                             + "\n".join(f"| {v.FUNDING_SOURCES[code]} | {ui.md_safe(budget.usd(c))} |"
                                         for code, c in b.by_source.items()))
    with st.expander("Add a budget line", icon=":material/add:", expanded=not b.lines):
        entered = budget_form(f"budget_add_{app_id}")
        if entered is not None:
            _save_line(repo.add_budget_item, user.id, app_id, entered)

    with st.container(border=True, key="card-budget-narrative"):
        st.markdown("##### Budget narrative")
        st.caption("Written only from the lines above. Code checks it afterwards: a figure that is not in your "
                   "budget is marked [VERIFY], a sentence calling pending money committed is removed, and a line "
                   "without a justification gets a [NEEDS: …] placeholder.")
        question = budget.funds_question(user.id, app_id)
        limit = ui.word_limit(question.question) if question else None
        words = st.number_input("Length (words)", min_value=budget.MIN_WORDS, max_value=budget.MAX_WORDS, step=25,
                                value=min(max(limit or budget.DEFAULT_WORDS, budget.MIN_WORDS), budget.MAX_WORDS),
                                key=f"budget_words_{app_id}",
                                help="Defaults to the word limit of the application's question about funds.")
        if st.button("Write the budget narrative", key=f"budget_narrative_{app_id}", type="primary",
                     icon=":material/edit_note:"):
            with st.spinner("Writing from your budget lines…"):
                out = _run(budget.write_narrative, user.id, app_id, target_words=int(words), want_mock=mock_on)
            if out:
                cost = ui.usage_line(out.data.get("usage")) if out.mode == "live" else ""
                st.session_state["apps_notice"] = "Budget narrative saved." + (f" AI use: {cost}." if cost else "")
            st.rerun()
        if narrative is None:
            st.caption(":material/edit_note: No narrative yet. Add your lines, then press **Write the budget "
                       "narrative**.")
        else:
            flags = narrative["payload"]["flags"]
            label = (":gray-badge[MOCK NARRATIVE · practice mode, fixed template, no AI]" if narrative["mode"] == "mock"
                     else ":violet-badge[:material/smart_toy: AI NARRATIVE · gpt-6-luna, checked by code]")
            fresh = (":green-badge[:material/check: Matches your current budget]"
                     if budget.is_current(user.id, app_id, narrative)
                     else ":orange-badge[:material/update: Your budget changed since: write it again]")
            st.markdown(f"{label} {fresh}")
            st.markdown(ui.md_safe(narrative["text"]))
            st.caption(f"{flags['word_count']} words (target {narrative['payload']['target_words']}) · written "
                       f"{narrative['created_at'].replace('T', ' ')[:16]} UTC"
                       + (f" · {ui.usage_line(narrative['payload']['usage'])}"
                          if narrative["mode"] == "live" and narrative["payload"].get("usage") else ""))
            if flags["flagged"]:
                st.warning("Marked [VERIFY] because your budget and profile do not contain them: "
                           + ", ".join(ui.md_safe(x) for x in flags["flagged"]), icon=":material/fact_check:")
            if flags["commitments_removed"]:
                st.warning(f"Removed {flags['commitments_removed']} sentence(s) that described pending money as "
                           "committed.", icon=":material/shield:")
            if flags["not_mentioned"]:
                st.info("Not mentioned in the narrative: line(s) " + ", ".join(map(str, flags["not_mentioned"])) + ".",
                        icon=":material/info:")
            if flags["placeholders"]:
                st.info(f"{len(flags['placeholders'])} [NEEDS: …] placeholder(s) to fill in.", icon=":material/edit:")
            with st.container(horizontal=True):
                if question is not None and st.button(
                        f"Use as a suggestion for question {question.position + 1}", key=f"budget_suggest_{app_id}",
                        icon=":material/input:", help="Puts the narrative on the Write answers tab as a suggested "
                                                      "draft. Your answer does not change until you use it."):
                    budget.suggest_for_question(user.id, app_id, question.id)
                    st.session_state["apps_notice"] = (f"The narrative is waiting as a suggestion for question "
                                                       f"{question.position + 1} on the Write answers tab.")
                    st.rerun()
                st.download_button("Download narrative", narrative["text"], file_name=f"budget-narrative-{app_id}.txt",
                                   mime="text/plain", icon=":material/download:", key=f"budget_download_{app_id}")
    if st.button("Ask the AI Grant Advisor about this budget", key=f"ask_budget_{app_id}", icon=":material/forum:",
                 type="tertiary"):
        st.session_state["advisor_pending"] = (f"Check the budget for my application \"{app['title']}\" (application "
                                               f"{app_id}): do the totals match the amount requested, and what is "
                                               "missing?")
        st.switch_page("app_pages/advisor.py")
    if st.button("Can we afford to win? Check the cash this award would need", key=f"afford_budget_{app_id}",
                 icon=":material/account_balance_wallet:", type="tertiary",
                 help="Opens Should We Pursue? for this grant: the match, reimbursement delays, and your reserves, "
                      "worked out by code. It uses this budget's committed match money."):
        st.session_state["pursue_target"] = (f"grant:{app['grant_id']}" if app["grant_id"]
                                             else f"application:{app_id}")
        st.session_state["pursue_tab"] = "afford"
        st.switch_page("app_pages/pursue.py")

# ---------------------------------------------------------------- timeline
SOURCE_BADGES = {"grants.gov": ":blue-badge[:material/public: From Grants.gov]",
                 "sample": ":orange-badge[:material/science: SAMPLE example date · not a real deadline]",
                 "user": ":gray-badge[:material/edit_calendar: Entered by you]"}
STEP_BADGES = {"done": ":green-badge[:material/check: Done]", "overdue": ":red-badge[:material/error: {words}]",
               "today": ":orange-badge[:material/today: Due today]", "upcoming": ":blue-badge[{words}]"}
FLAG_BOXES = {"error": (st.error, ":material/error:"), "warning": (st.warning, ":material/warning:"),
              "info": (st.info, ":material/info:")}


def _build_plan(days: dict | None = None, early: int | None = None) -> None:
    try:
        out = timeline.build_plan(user.id, app_id, days=days, submit_early=early)
    except (v.ValidationError, repo.NotFound) as err:
        st.session_state["apps_warning"] = str(err)
    else:
        st.session_state["apps_notice"] = (f"Workback plan saved: {len(out['plan']['milestones'])} steps to "
                                           f"{out['plan']['deadline']}, computed by code in {out['elapsed_ms']} ms.")
    st.rerun()


def _set_deadline(due) -> None:
    try:
        repo.update_application(user.id, app_id, {"status": app["status"], "due_date": due,
                                                  "amount_requested": app["amount_requested"], "notes": app["notes"]})
    except (v.ValidationError, repo.NotFound) as err:
        st.session_state["apps_warning"] = str(err)
    else:
        st.session_state["apps_notice"] = "Deadline saved." + (" Rebuild the plan to use it."
                                                               if repo.get_timeline(user.id, app_id) else "")
    st.rerun()


with timeline_tab:
    deadline = timeline.resolve_deadline(app, grant)
    plan = repo.get_timeline(user.id, app_id)
    today = timeline.current_date()
    st.markdown("##### Application timeline")
    st.caption("A workback plan from the deadline: seven steps, each with a due date, fitted to the time left. "
               "GrantBridge never guesses a deadline and does not send reminders.")
    with st.container(border=True, key="card-timeline-deadline"):
        if deadline.date is None:
            st.markdown("**Deadline: not set**")
            st.info(ui.md_safe(deadline.note), icon=":material/event:")
        else:
            left = (deadline.date - today).days
            when = "passed" if left < 0 else "today" if left == 0 else f"in {left} day(s)"
            st.markdown(f"{SOURCE_BADGES[deadline.source]} **Deadline: {deadline.date:%B %d, %Y}** ({when})")
            st.caption(ui.md_safe(deadline.note))
        with st.container(horizontal=True, vertical_alignment="bottom"):
            with st.form(f"tl_deadline_{app_id}", border=False):
                new_deadline = st.date_input("Enter or correct the deadline", value=deadline.date, format="YYYY-MM-DD",
                                             key=f"tl_deadline_value_{app_id}",
                                             help="Use the funder's own date. A date you enter is labeled as yours.")
                if st.form_submit_button("Save deadline", icon=":material/save:"):
                    _set_deadline(new_deadline)
            if deadline.official_source == "grants.gov" and deadline.official and deadline.date != deadline.official:
                if st.button(f"Use the Grants.gov date ({deadline.official})", key=f"tl_use_official_{app_id}",
                             icon=":material/public:"):
                    _set_deadline(deadline.official)

    settings = (plan or {}).get("settings", {})
    days_now = settings.get("days") or {key: d for key, (_, d, _) in timeline.STEPS.items()}
    with st.expander("Plan assumptions: days per step (you can change them)", icon=":material/tune:"):
        with st.form(f"tl_days_{app_id}", border=False):
            cols = st.columns(4)
            entered = {}
            for i, (key, (step_label, default, what)) in enumerate(timeline.STEPS.items()):
                entered[key] = cols[i % 4].number_input(step_label, min_value=0, max_value=timeline.MAX_STEP_DAYS,
                                                        value=int(days_now.get(key, default)), step=1,
                                                        key=f"tl_days_{app_id}_{key}", help=what)
            early = cols[3].number_input("Submit early by (days)", min_value=0, max_value=timeline.MAX_SUBMIT_EARLY,
                                         value=int(settings.get("default_submit_early", timeline.DEFAULT_SUBMIT_EARLY)),
                                         step=1, key=f"tl_early_{app_id}")
            st.caption("The defaults (34 days of work, then submit 2 days early) are GrantBridge's assumptions for a "
                       "small team, not a funder's rule. Change them to fit yours.")
            if st.form_submit_button("Rebuild with these days" if plan else "Build the plan with these days",
                                     icon=":material/restart_alt:"):
                _build_plan(entered, early)

    if plan is None:
        if st.button("Create a workback plan", type="primary", key=f"tl_build_{app_id}", icon=":material/event_note:",
                     disabled=deadline.date is None,
                     help="Works back from the deadline through eligibility review, documents, budget, first draft, "
                          "internal review, final revisions, and submission."):
            _build_plan()
        if deadline.date is None:
            st.caption("Set the deadline above first.")
    else:
        done = sum(bool(m["done_at"]) for m in plan["milestones"])
        st.markdown(f"**Plan to {plan['deadline']}** · {SOURCE_BADGES[plan['deadline_source']]} · built "
                    f"{settings.get('built_on', '')} · {done} of {len(plan['milestones'])} steps done")
        for flag in timeline.check_plan(plan, deadline, today):
            box, icon = FLAG_BOXES[flag["level"]]
            box(ui.md_safe(flag["text"]), icon=icon)
        with st.form(f"tl_steps_{app_id}"):
            chosen = {}
            for m in plan["milestones"]:
                step_label, _, what = timeline.STEPS[m["step"]]
                code, words = timeline.status(m, today)
                text_col, date_col, done_col = st.columns([4, 2, 1], vertical_alignment="center")
                text_col.markdown(f"**{step_label}** {STEP_BADGES[code].format(words=words)}"
                                  + (" :gray-badge[date changed by you]" if m["edited"] else "") + f"  \n{what}")
                chosen[m["id"]] = (date_col.date_input(f"{step_label}: due", value=date.fromisoformat(m["due_date"]),
                                                       format="YYYY-MM-DD", key=f"tl_due_{m['id']}",
                                                       label_visibility="collapsed"),
                                   done_col.checkbox("Done", value=bool(m["done_at"]), key=f"tl_done_{m['id']}",
                                                     help=f"Mark {step_label.lower()} as done"))
            if st.form_submit_button("Save changes", type="primary", icon=":material/save:"):
                try:
                    for milestone_id, (due, is_done) in chosen.items():
                        repo.update_milestone(user.id, milestone_id, due, is_done)
                except (v.ValidationError, repo.NotFound) as err:
                    st.session_state["apps_warning"] = str(err)
                else:
                    st.session_state["apps_notice"] = "Timeline saved."
                st.rerun()
        with st.container(horizontal=True):
            if st.button("Rebuild from the deadline", key=f"tl_rebuild_{app_id}", icon=":material/restart_alt:",
                         help="Recomputes every date from the current deadline. Steps marked done stay done."):
                _build_plan()
            st.download_button("Download calendar (.ics)", timeline.to_ics(app, plan),
                               file_name=f"grantbridge-timeline-{app_id}.ics", mime="text/calendar",
                               icon=":material/calendar_month:", key=f"tl_ics_{app_id}")
            if st.button("Delete plan", key=f"tl_delete_{app_id}", type="tertiary", icon=":material/delete:"):
                repo.delete_timeline(user.id, app_id)
                st.session_state["apps_notice"] = "Plan deleted. The deadline is unchanged."
                st.rerun()
        st.caption("GrantBridge does not send reminders. The calendar file adds these dates to your own calendar; "
                   "any alerts come from your calendar app.")

# ---------------------------------------------------------------- requirements and source
with source_tab:
    if grant is not None:
        with st.container(border=True, key=f"card-{'sample' if grant['is_example'] else 'live'}-source"):
            st.markdown(c.SAMPLE_BADGE if grant["is_example"] else c.LIVE_BADGE)
            st.markdown(f"**{ui.md_safe(grant['title'])}** · {ui.md_safe(grant['funder'])}")
            if grant["summary"]:
                st.markdown(ui.external_md(ui.clip(grant["summary"], 800)))
            if grant["eligibility"]:
                st.markdown("**Funder's eligibility requirements**")
                st.markdown("\n".join(f"- {ui.external_md(e)}" for e in grant["eligibility"]))
            st.caption(c.due_date_note(app, grant))
    st.markdown(f"This application has **{len(sections)} question(s)** and **{len(requirements)} requirement(s)**.")
    st.markdown("**Paste the funder's questions or requirements**")
    st.caption("One per line. Lines that ask something or give a word limit become questions; the rest become "
               "requirements that every answer is reviewed against. Pasted text is treated as data, never as "
               "instructions for the AI.")
    preview_key = f"paste_preview_{app_id}"
    with st.form(f"paste_{app_id}", clear_on_submit=False):
        pasted = st.text_area("Funder text", height=150, max_chars=20_000, label_visibility="collapsed",
                              placeholder="1. Describe your program and who it serves. (300 words)\n"
                                          "Applicants must report attendance quarterly.")
        if st.form_submit_button("Preview", icon=":material/preview:"):
            try:
                st.session_state[preview_key] = drafting.parse_funder_text(pasted)
            except v.ValidationError as err:
                st.error(str(err), icon=":material/error:")
    preview = st.session_state.get(preview_key)
    if preview is not None:
        flagged = [i for i in preview if i.signals]
        include_flagged = False
        if flagged:
            st.warning(f"{len(flagged)} line(s) contain wording aimed at AI tools rather than applicants, for example "
                       f'"{flagged[0].signals[0]}". They are left out unless you choose to add them. GrantBridge '
                       "treats such text only as plain text either way.", icon=":material/shield:")
            st.markdown("\n".join(f"- ~~{ui.external_md(i.text)}~~" for i in flagged))
            include_flagged = st.checkbox("Add the flagged line(s) anyway", key=f"paste_flagged_{app_id}")
        kept = [i for i in preview if include_flagged or not i.signals]
        new_questions = [i for i in kept if i.kind == "question"]
        new_requirements = [i for i in kept if i.kind == "requirement"]
        if not preview:
            st.info("Nothing to add: the pasted text had no usable lines.", icon=":material/info:")
        else:
            c1, c2 = st.columns(2)
            c1.markdown(f"**{len(new_questions)} question(s)**")
            c1.markdown("\n".join(f"- {ui.external_md(i.text)}" for i in new_questions) or "- None")
            c2.markdown(f"**{len(new_requirements)} requirement(s)**")
            c2.markdown("\n".join(f"- {ui.external_md(i.text)}" for i in new_requirements) or "- None")
            if st.button(f"Add {len(new_questions)} question(s) and {len(new_requirements)} requirement(s)",
                         key=f"paste_add_{app_id}", type="primary", icon=":material/playlist_add:"):
                try:
                    repo.add_sections(user.id, app_id, [i.text for i in new_questions])
                    repo.add_requirements(user.id, app_id, [i.text for i in new_requirements])
                except (v.ValidationError, repo.NotFound) as err:
                    st.error(str(err), icon=":material/error:")
                else:
                    st.session_state.pop(preview_key, None)
                    st.session_state["apps_notice"] = "Added the pasted questions and requirements."
                    st.rerun()

    st.markdown("**Questions**")
    if not sections:
        st.caption("No questions yet.")
    for s in sections:
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        c1.markdown(f"{s.position + 1}. {ui.external_md(s.question)}")
        if c2.button("Remove", key=f"rmq_{s.id}", disabled=bool(s.answer.strip()),
                     help="Clear the answer first: questions with answers cannot be removed."):
            repo.delete_section(user.id, s.id)
            st.rerun()
    with st.form(f"add_q_{app_id}", clear_on_submit=True):
        question = st.text_input("Add a question", max_chars=1000,
                                 placeholder="e.g. Describe your evaluation plan. (200 words)")
        if st.form_submit_button("Add question", icon=":material/add:"):
            try:
                repo.add_section(user.id, app_id, question)
            except (v.ValidationError, repo.NotFound) as err:
                st.error(str(err), icon=":material/error:")
            else:
                st.rerun()

    st.markdown("**Requirements every answer is reviewed against**")
    if not requirements:
        st.caption("None yet.")
    for r in requirements:
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        c1.markdown(f"- {ui.external_md(r['text'])}")
        if c2.button("Remove", key=f"rmr_{r['id']}"):
            repo.delete_requirement(user.id, r["id"])
            st.rerun()
    with st.form(f"add_r_{app_id}", clear_on_submit=True):
        requirement = st.text_input("Add a requirement", max_chars=repo.MAX_REQUIREMENT_CHARS,
                                    placeholder="e.g. Include at least one measurable outcome with its source.")
        if st.form_submit_button("Add requirement", icon=":material/add:"):
            try:
                repo.add_requirements(user.id, app_id, [requirement])
            except (v.ValidationError, repo.NotFound) as err:
                st.error(str(err), icon=":material/error:")
            else:
                st.rerun()

# ---------------------------------------------------------------- details
with details_tab:
    with st.form(f"details_{app_id}"):
        c1, c2, c3 = st.columns(3)
        status_value = c1.selectbox("Status", v.APPLICATION_STATUSES,
                                    index=v.APPLICATION_STATUSES.index(app["status"]))
        due = c2.date_input("Due date", value=date.fromisoformat(app["due_date"]) if app["due_date"] else None,
                            format="YYYY-MM-DD", help="For a sample grant this is only an example date.")
        amount = c3.number_input("Amount requested (USD)", min_value=0, max_value=100_000_000, step=500,
                                 value=app["amount_requested"], placeholder="e.g. 15000")
        if grant:
            st.caption(f"Funder's range: {ui.amount_range(grant['amount_min'], grant['amount_max'])}")
        notes = st.text_area("Notes", value=app["notes"], max_chars=5000, height=120)
        if st.form_submit_button("Save details", type="primary", icon=":material/save:"):
            try:
                repo.update_application(user.id, app_id, {"status": status_value, "due_date": due,
                                                          "amount_requested": amount, "notes": notes})
            except (v.ValidationError, repo.NotFound) as err:
                st.error(str(err), icon=":material/error:")
            else:
                st.session_state["apps_notice"] = "Details saved."
                st.rerun()
    with st.expander("Delete this application", icon=":material/delete:"):
        st.write("This permanently removes the application, its answers, drafts, and history.")
        confirm = st.checkbox("I understand this cannot be undone.", key=f"del_ok_{app_id}")
        if st.button("Delete application", disabled=not confirm, key=f"del_{app_id}"):
            repo.delete_application(user.id, app_id)
            st.session_state.pop("app_picker", None)
            st.session_state["apps_notice"] = "Application deleted."
            st.rerun()

# ---------------------------------------------------------------- export
with export_tab:
    lines = [f"# {app['title']}", "", f"Funder: {app['funder'] or '—'}", f"Status: {app['status']}"]
    if app["due_date"]:
        lines.append(f"Due: {app['due_date']}" + (" (example date from a SAMPLE grant)"
                                                   if grant and grant["is_example"] else ""))
    if app["amount_requested"] is not None:
        lines.append(f"Amount requested: {ui.money(app['amount_requested'])}")
    for s in sections:
        st_info = drafting.section_status(user.id, {"id": s.id, "answer": s.answer})
        lines += ["", f"## {s.position + 1}. {s.question}", "", f"_Status: {st_info['label']}_", "",
                  s.answer or "_(not answered yet)_"]
    if b.lines:
        def cell(text: str) -> str:
            return str(text).replace("|", "/")

        lines += ["", "## Budget", "", "| # | Category | Description | Quantity × unit cost | Line total | Paid by |",
                  "|---|---|---|---|---:|---|"]
        lines += [f"| {x['number']} | {x['category']} | {cell(x['description'])} | {x['quantity']} {cell(x['unit'])} × "
                  f"{budget.usd(x['unit_cost_cents'])} | {budget.usd(x['total_cents'])} | {x['source_label']}"
                  + (f" ({cell(x['source_name'])})" if x["source_name"] else "") + " |" for x in b.lines]
        lines += ["", f"Total budget: {budget.usd(b.total_cents)}. Requested from this grant: "
                      f"{budget.usd(b.requested_cents)}. Totals computed by GrantBridge."]
    if plan is not None:
        lines += ["", "## Timeline", "", f"Deadline: {plan['deadline']} ({timeline.SOURCE_LABELS[plan['deadline_source']]})",
                  ""]
        lines += [f"- {m['due_date']} · {timeline.STEPS[m['step']][0]}" + (" (done)" if m["done_at"] else "")
                  for m in plan["milestones"]]
    if narrative is not None:
        stale_note = "" if budget.is_current(user.id, app_id, narrative) else (
            " _(written for an earlier version of the budget)_")
        lines += ["", "## Budget narrative" + stale_note, "", narrative["text"]]
    text = "\n".join(lines) + "\n"
    if mine["open_items"]:
        st.warning(f"{mine['open_items']} verification item(s) are still open for this application.",
                   icon=":material/fact_check:")
    st.download_button("Download as Markdown", text, file_name=f"application-{app_id}.md",
                       mime="text/markdown", icon=":material/download:")
    with st.container(border=True, key="card-export"):
        st.markdown(ui.external_md(text))  # answers may hold pasted text: no remote images or unknown links

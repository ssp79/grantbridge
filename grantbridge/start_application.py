"""Starting an application: from a grant you saved, from the funder's own documents, or from nothing.

This is the top half of the Applications page rather than a page of its own, because "start one" and "work on
one" are the same job at different moments. It is kept in its own module so the Applications page stays
readable.

The document route is the only place in GrantBridge that accepts an upload, and the restrictions on it are in
docs/SECURITY.md. What it reads is turned into two things: the grant's own details, questions and requirements
(grantbridge.solicitation), and the outline of sections the funder expects you to write, with the rubric your
writing will be scored against (grantbridge.outline). Nothing reaches an application until the review screen is
confirmed.
"""

from __future__ import annotations

import streamlit as st

from grantbridge import components as c
from grantbridge import documents as docs
from grantbridge import outline, repo, solicitation as sol, ui, validation as v

MAX_FILES = 3
PAYLOAD = "import_payload"        # the checked extraction, waiting for the user to confirm it
OUTLINE = "import_outline"
MODE = "apps_mode"                # "new" while the start flow is open

ROUTES = {
    "saved": "From a grant you saved",
    "documents": "From the funder's documents",
    "blank": "Blank application",
}
ROUTE_HELP = {
    "saved": "GrantBridge already has its questions, funder and deadline, so there is nothing to upload.",
    "documents": "Upload or paste the solicitation. GrantBridge reads out the outline, the requirements and "
                 "how it will be scored.",
    "blank": "Just a title. You add the sections and requirements yourself.",
}


def opening() -> None:
    """What this screen is for, before any choice is made."""
    st.subheader("Start an application", anchor=False)
    st.markdown(
        "An application in GrantBridge is a workspace: the funder's requirements on one side, your writing on "
        "the other, and a record of what still needs checking. Nothing here is submitted to a funder — "
        "GrantBridge is where you prepare and check the work, and you file it on the funder's own portal.")
    st.caption("Pick how you want to start. You can change or add to any of it afterwards.")


# ---------------------------------------------------------------- route 1: a grant already saved

def from_saved_grant(user) -> None:
    st.markdown("**What this does:** copies the grant's title, funder, deadline and any questions GrantBridge "
                "already holds into a new application, so you start with the requirements already in place.")
    saved = repo.list_saved_grants(user.id)
    if not saved:
        if c.empty_state(":material/bookmarks:", "No saved grants yet",
                         "Save a grant on Find Grants and it will appear here, with its questions and deadline "
                         "ready to copy.", action="Find a grant", key="new-app-nosaved"):
            st.switch_page("app_pages/find_grants.py")
        return
    labels = {g["id"]: f"{g['title']} · {g['funder']}" for g in saved}
    pick = st.selectbox("Which saved grant?", list(labels), format_func=labels.get, key="new_app_grant")
    chosen = next(g for g in saved if g["id"] == pick)
    st.markdown(c.SAMPLE_BADGE if chosen["is_example"] else c.LIVE_BADGE)
    existing = repo.application_for_grant(user.id, pick)
    if existing:
        st.info("You already have an application for this grant, so this will open that one rather than making a "
                "second.", icon=":material/info:")
    if st.button("Open the application" if existing else "Create the application", type="primary",
                 icon=":material/arrow_forward:"):
        st.session_state["open_application_id"] = repo.create_application_from_grant(user.id, pick)
        st.session_state["apps_notice"] = (f"Opened your application for {chosen['title']}." if existing
                                           else f"Created an application for {chosen['title']}.")
        st.session_state.pop(MODE, None)
        st.rerun()


# ---------------------------------------------------------------- route 2: a blank application

def blank_application(user) -> None:
    st.markdown("**What this does:** makes an empty workspace with just a title and funder. Use it when the "
                "grant is not in GrantBridge and you do not have the solicitation as a file — you can paste the "
                "funder's questions in later on the **Requirements & source** tab.")
    with st.form("new_app_blank"):
        title = st.text_input("Application title *", max_chars=200,
                              placeholder="e.g. Harborview Reading Fund 2027")
        funder = st.text_input("Funder", max_chars=200, placeholder="Who is giving the money?")
        if st.form_submit_button("Create application", icon=":material/add:", type="primary"):
            try:
                st.session_state["open_application_id"] = repo.create_application(user.id, title, funder)
            except v.ValidationError as err:
                st.error(str(err), icon=":material/error:")
            else:
                st.session_state["apps_notice"] = "Created a blank application."
                st.session_state.pop(MODE, None)
                st.rerun()


# ---------------------------------------------------------------- route 3: the funder's own documents

def read_documents(user, *, key_found: bool, default_mock: bool) -> None:
    st.markdown(
        "**What this does:** reads the funder's solicitation and pulls out four things — the **outline** of "
        "sections you are expected to write and what each must contain, the **rubric** your writing will be "
        "scored against, the **forms and attachments** you must file and when each one applies, and the grant's "
        "own details such as the deadline, award range and match. You check all of it on the next screen before "
        "anything is saved.")
    st.markdown("**What it will not do:** invent anything. Every item has to carry a sentence copied from your "
                "document, and GrantBridge drops any item whose sentence it cannot find there. If the funder "
                "did not say it, it will not appear.")
    with st.container(border=True, key="card-upload-limits"):
        st.markdown("**Before you upload**")
        st.caption(
            f"PDF, Word (.docx) or plain text, up to {docs.MAX_BYTES // 1_048_576} MB and {docs.MAX_PAGES} "
            f"pages each, {MAX_FILES} at a time. GrantBridge checks what a file really is rather than trusting "
            "its name, reads the text in memory and keeps the text, not the file. A scanned PDF with no text "
            "layer cannot be read, because GrantBridge has no OCR — paste the text instead. GrantBridge has had "
            "no independent security review, so please do not upload confidential documents.")
    uploaded = st.file_uploader("Funder documents", type=["pdf", "docx", "txt"], accept_multiple_files=True,
                                key="import_files",
                                help="The solicitation, notice of funding opportunity, or application guidance.")
    pasted = st.text_area("Or paste the text instead", height=140, max_chars=docs.MAX_CHARS,
                          placeholder="Paste the funder's notice here if you do not have a file.",
                          key="import_pasted")
    mock_on = st.toggle("Practice mode (no AI, free)", value=default_mock, disabled=not key_found,
                        key="import_mock",
                        help="Practice mode uses fixed text patterns instead of the model. It finds far less on "
                             "a real notice, but it costs nothing and every item is still checked against the "
                             "document.")
    if not key_found:
        st.caption("No model key was found, so this runs in practice mode.")
    st.caption("Reading a long federal notice takes about ten seconds and costs a fraction of a cent.")

    if st.button("Analyze the solicitation", type="primary", icon=":material/document_scanner:",
                 disabled=not (uploaded or pasted.strip())):
        if uploaded and len(uploaded) > MAX_FILES:
            st.error(f"Please add at most {MAX_FILES} documents at a time.", icon=":material/error:")
            return
        read, problems = sol.read_uploads(uploaded)
        for problem in problems:
            st.error(problem, icon=":material/error:")
        if pasted.strip():
            try:
                read.append(docs.read(pasted.encode("utf-8"), "pasted text"))
            except docs.UploadError as err:
                st.error(f"Pasted text: {err}", icon=":material/error:")
        if not read:
            return
        with st.spinner("Analyzing the solicitation: details, requirements, outline and rubric…"):
            try:
                found = sol.extract(user.id, read, want_mock=mock_on)
                shape = outline.extract(user.id, read, want_mock=mock_on)
            except v.ValidationError as err:
                st.error(str(err), icon=":material/error:")
                return
        st.session_state[PAYLOAD] = {**found.data, "notice": found.notice}
        st.session_state[OUTLINE] = {**shape.data, "notice": shape.notice}
        st.rerun()


# ---------------------------------------------------------------- the review screen

def source_note(item: dict, text: str | None = None) -> str:
    """The sentence an item came from, which is the only reason it is on the screen.

    Where the item simply is that sentence, quoting it back would say the same thing twice, so only the
    document it came from is named.
    """
    same = text is not None and " ".join(text.split()).lower() == " ".join(item["excerpt"].split()).lower()
    note = f"From {item['source']}" if same else f"“{ui.clip(item['excerpt'], 240)}” — {item['source']}"
    if not item.get("certain", True):
        note += f" · **Unclear:** {item.get('note') or 'the document is ambiguous here.'}"
    return note


def _outline_review(shape: dict) -> dict:
    """The outline and rubric, with a tick box on everything. Returns the indexes the user kept."""
    sections = shape.get("sections") or []
    criteria = shape.get("criteria") or []
    components = shape.get("components") or []
    chosen: dict[str, list[int]] = {"sections": [], "criteria": [], "components": []}

    if sections:
        with st.expander(f"The outline you must write to · {len(sections)} section(s)", expanded=True,
                         icon=":material/format_list_numbered:"):
            st.caption("These are the sections the funder named, in the funder's order, with the discrete things "
                       "each one has to contain. They become your writing checklist.")
            for i, section in enumerate(sections):
                keep_col, body = st.columns([1, 14], vertical_alignment="top")
                keep = keep_col.checkbox("Include", value=True, key=f"out_s_{i}", label_visibility="collapsed")
                limit = ""
                if section.get("limit_pages"):
                    limit = f" :blue-badge[{section['limit_pages']} pages]"
                elif section.get("limit_words"):
                    limit = f" :blue-badge[{section['limit_words']} words]"
                body.markdown(f"**{i + 1}. {ui.external_md(section['heading'])}**{limit}")
                if section.get("purpose"):
                    body.caption(ui.md_safe(section["purpose"]))
                for element in section["elements"]:
                    body.markdown(f"- {ui.external_md(element['text'])}")
                for evidence in section["evidence"]:
                    body.markdown(f"- :material/attach_file: {ui.external_md(evidence['text'])}")
                if section.get("scored_by"):
                    body.caption("Scored against: " + ", ".join(ui.md_safe(s) for s in section["scored_by"]))
                if keep:
                    chosen["sections"].append(i)

    scored = [c for c in criteria if c.get("kind") != "rollup"]
    if criteria:
        with st.expander(f"How it will be scored · {len(scored)} criteri{'on' if len(scored) == 1 else 'a'}",
                         icon=":material/grading:"):
            st.caption("GrantBridge keeps these so it can tell you which parts of the rubric your draft covers "
                       "and which it does not. It does not predict a score or a decision.")
            for i, criterion in enumerate(criteria):
                keep_col, body = st.columns([1, 14], vertical_alignment="top")
                keep = keep_col.checkbox("Include", value=True, key=f"out_c_{i}", label_visibility="collapsed")
                body.markdown(f"{_criterion_badges(criterion)} **{ui.external_md(criterion['name'])}**")
                for objective in criterion["objectives"]:
                    body.markdown(f"- {ui.external_md(objective['text'])}")
                for rule in criterion.get("rating_rules") or []:
                    needed = (f" — needs {rule['min_objectives']} of {len(criterion['objectives'])}"
                              if rule.get("min_objectives") else "")
                    body.caption(f"**{ui.md_safe(rule['rating'])}**{needed}: {ui.external_md(rule['rule'])}")
                if criterion.get("threshold"):
                    body.caption(f":material/flag: {ui.external_md(criterion['threshold'])}")
                if keep:
                    chosen["criteria"].append(i)

    if components:
        with st.expander(f"What you must file · {len(components)} item(s)", icon=":material/checklist:"):
            st.caption("Forms, attachments, certifications and disclosures. Several of these only apply in "
                       "certain cases, so the funder's own condition is kept with each one.")
            for i, component in enumerate(components):
                keep_col, body = st.columns([1, 14], vertical_alignment="top")
                keep = keep_col.checkbox("Include", value=True, key=f"out_m_{i}", label_visibility="collapsed")
                body.markdown(f":gray-badge[{component['kind']}] **{ui.external_md(component['name'])}**")
                body.caption(ui.external_md(component["condition"]))
                for content in component["contents"]:
                    body.markdown(f"- {ui.external_md(content['text'])}")
                if keep:
                    chosen["components"].append(i)

    registrations = shape.get("registrations") or []
    rules = shape.get("format_rules") or []
    if registrations or rules:
        with st.expander("Registrations and format rules", icon=":material/rule:"):
            if registrations:
                st.markdown("**Register before you can submit**")
                st.caption("These are the ones that sink applications: they take time you have to plan for.")
                for registration in registrations:
                    lead = registration.get("lead_time")
                    st.markdown(f"- **{ui.external_md(registration['name'])}**"
                                + (f" — {ui.external_md(lead)}" if lead else ""))
            if rules:
                st.markdown("**Format and submission rules**")
                for rule in rules:
                    st.markdown(f"- {ui.external_md(rule['text'])}")
    return chosen


def _criterion_badges(criterion: dict) -> str:
    if criterion.get("kind") == "threshold":
        return ":red-badge[Pass or fail]"
    if criterion.get("kind") == "rollup":
        return ":gray-badge[How the ratings combine]"
    bits = []
    if criterion.get("weight_percent"):
        bits.append(f"{criterion['weight_percent']}% of the score")
    if criterion.get("max_points"):
        bits.append(f"max {criterion['max_points']} pts")
    return f":violet-badge[{' · '.join(bits)}]" if bits else ":violet-badge[Scored]"


def review(user, payload: dict, shape: dict | None) -> None:
    """Everything read out of the documents, with a tick on each item, before anything is written."""
    st.subheader("Check what GrantBridge found", anchor=False)
    read_docs = payload.get("documents", [])
    stats = payload.get("stats", {})
    st.markdown(
        "Nothing below has been saved yet. Untick anything you do not want, edit any wording that is off, then "
        "choose where it should go. Each item shows the sentence in your document it came from, so you can "
        "check it rather than trust it.")
    st.caption("Read " + ", ".join(f"**{ui.md_safe(d['name'])}**" for d in read_docs) +
               (" · practice mode, fixed text patterns" if payload.get("mode") == "mock" else
                f" · read by {ui.md_safe(payload.get('model') or 'the model')}"))
    if payload.get("notice"):
        st.warning(payload["notice"], icon=":material/info:")
    for d in read_docs:
        if d["truncated"]:
            st.warning(f"{d['name']} was longer than GrantBridge reads, so only the first "
                       f"{docs.MAX_CHARS:,} characters were used. Check that nothing you need was in the rest.",
                       icon=":material/content_cut:")
    dropped = sum(stats.get(k, 0) for k in ("dropped_no_excerpt", "dropped_not_found", "dropped_numbers"))
    if dropped:
        st.info(f"{dropped} item(s) were left out because GrantBridge could not find a sentence in your document "
                "that says them. Nothing is shown here unless the document states it.", icon=":material/shield:")
    if stats.get("dropped_injected"):
        st.warning(f"{stats['dropped_injected']} item(s) came from wording in the document aimed at AI tools "
                   "rather than at applicants. They were dropped. The document is only ever read as text.",
                   icon=":material/shield:")

    fields = payload.get("fields", {})
    groups = payload.get("groups", {})
    if not fields and not any(groups.values()) and not (shape or {}).get("sections"):
        st.warning("GrantBridge could not find anything it could attribute to the document. You can still "
                   "create the application and add the sections yourself.", icon=":material/info:")

    chosen: dict = {"fields": {}}
    writable = [f for f in ("title", "funder", "deadline") if f in fields]
    if writable:
        st.markdown("**The grant's details**")
        st.caption("These are written only where your application leaves them blank, so an import can never "
                   "overwrite something you typed.")
        for name in writable:
            item = fields[name]
            box, _ = st.columns([3, 2])
            value = box.text_input(sol.FIELD_LABELS[name], value=str(item["value"]), max_chars=200,
                                   key=f"imp_f_{name}")
            if value.strip():
                chosen["fields"][name] = value.strip()
            st.caption(source_note(item))
    other = {k: val for k, val in fields.items() if k not in writable}
    if other:
        with st.expander("Also found in the document", icon=":material/info:"):
            st.caption("GrantBridge records these with the import. They are not written into the application "
                       "record, so nothing you have entered is changed.")
            for name, item in other.items():
                st.markdown(f"**{sol.FIELD_LABELS[name]}:** {ui.md_safe(str(item['value']))}")
                st.caption(source_note(item))

    outline_chosen = _outline_review(shape) if shape else {}

    picked: dict[str, list[str]] = {}
    labels = {"questions": "Questions the funder asks outright",
              "eligibility": "Eligibility and restrictions",
              "financial": "Financial and budget requirements",
              "attachments": "Required attachments",
              "submission": "Submission and deadline"}
    for group, label in sol.SECTIONS.items():
        rows = groups.get(group) or []
        if not rows:
            continue
        with st.expander(f"{labels.get(group, label)} · {len(rows)} found", icon=":material/list:"):
            if group == "questions":
                st.caption("Most solicitations prescribe sections rather than asking questions. Anything the "
                           "funder does ask outright lands here and becomes a question on the Write answers tab.")
            else:
                st.caption("These become requirements your draft is checked against on the Review proposal tab.")
            for i, item in enumerate(rows):
                tick, text = st.columns([1, 12], vertical_alignment="center")
                keep = tick.checkbox("Include", value=True, key=f"imp_{group}_{i}", label_visibility="collapsed")
                limit = (f" · **{item['word_limit']} words**"
                         if item.get("word_limit") and str(item["word_limit"]) not in item["text"] else "")
                edited = text.text_input(f"{group} item {i + 1}", value=item["text"], max_chars=1000,
                                         key=f"imp_t_{group}_{i}", label_visibility="collapsed")
                text.caption(f"{source_note(item, item['text'])}{limit}")
                if keep and edited.strip():
                    picked.setdefault(group, []).append(edited.strip())

    st.subheader("Where should it go?", anchor=False)
    apps = repo.list_applications(user.id)
    target = st.radio("Destination", ["A new application", "An application I already have"],
                      horizontal=True, key="imp_target", disabled=not apps, label_visibility="collapsed")
    application_id = None
    if target == "An application I already have" and apps:
        labels_by_id = {a["id"]: f"{a['title']} (#{a['id']})" for a in apps}
        application_id = st.selectbox("Application", list(labels_by_id), format_func=labels_by_id.get,
                                      key="imp_app")
        st.caption("Existing answers, questions, outline sections and details are left exactly as they are. "
                   "Only new items are added, and only blank details are filled in.")
    title = None
    if application_id is None:
        title = st.text_input("New application title *", value=chosen["fields"].get("title", ""), max_chars=200,
                              key="imp_title", placeholder="What do you want to call this application?")

    counts = sum(len(x) for x in picked.values()) + len(outline_chosen.get("sections") or [])
    confirm, cancel = st.columns([2, 1], vertical_alignment="center")
    if confirm.button(f"Add {counts} item(s) to the application", type="primary",
                      icon=":material/playlist_add:"):
        chosen.update({g: items for g, items in picked.items()})
        try:
            result = sol.apply_import(user.id, payload, chosen, application_id=application_id, title=title)
            extra = {}
            if shape:
                extra = outline.apply_import(user.id, result["application_id"], shape, outline_chosen)
        except (v.ValidationError, repo.NotFound) as err:
            st.error(str(err), icon=":material/error:")
        else:
            kept = (" Your existing " + ", ".join(result["kept_existing"]) + " was left unchanged."
                    if result["kept_existing"] else "")
            outlined = (f" The outline has {extra['sections_added']} section(s)."
                        if extra.get("sections_added") else "")
            st.session_state["open_application_id"] = result["application_id"]
            st.session_state["apps_notice"] = (
                f"Imported {result['questions_added']} question(s) and {result['requirements_added']} "
                f"requirement(s) from your solicitation.{outlined}{kept}")
            for key in (PAYLOAD, OUTLINE, MODE, "import_files", "import_pasted"):
                st.session_state.pop(key, None)
            st.rerun()
    if cancel.button("Start over", icon=":material/restart_alt:"):
        for key in (PAYLOAD, OUTLINE):
            st.session_state.pop(key, None)
        st.rerun()


def render(user, *, key_found: bool, default_mock: bool, has_applications: bool) -> None:
    """The whole start flow. Call it instead of the workspace when `MODE` is set or there are no applications."""
    payload = st.session_state.get(PAYLOAD)
    if payload is not None:
        review(user, payload, st.session_state.get(OUTLINE))
        return

    if has_applications and st.button("Back to your applications", icon=":material/arrow_back:",
                                      type="tertiary"):
        st.session_state.pop(MODE, None)
        st.rerun()
    opening()
    route = st.radio("How would you like to start?", list(ROUTES),
                     format_func=lambda k: ROUTES[k],
                     captions=[ROUTE_HELP[k] for k in ROUTES], horizontal=True, key="new_app_route")
    st.divider()
    if route == "saved":
        from_saved_grant(user)
    elif route == "blank":
        blank_application(user)
    else:
        read_documents(user, key_found=key_found, default_mock=default_mock)

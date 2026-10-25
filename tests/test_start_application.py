"""Starting an application from the Applications page: the three routes, the review screen, and the outline tab.

Starting one and working on one are the same page, so these drive `app_pages/applications.py` headlessly.
"""

import pytest
from streamlit.testing.v1 import AppTest

from grantbridge import auth, documents as docs, outline, repo, solicitation as sol, start_application
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text

PAGE = "app_pages/applications.py"
NOFO = """Harborview Reading Fund
Notice of Funding Opportunity HRF-2027-04

Applications are due 2027-05-12 at 5:00 p.m. Eastern.
Awards range from $20,000 to $75,000 over two years.
A cash match of 20% of the total project cost is required.

Use the following format for the Project Narrative:
Need: Describe the community you serve and the need you are addressing. (600 words)
Approach: Explain how the objectives will be attained. Include specific procedures and schedules.

Required attachments: IRS determination letter, audited financial statements.
"""


@pytest.fixture
def signed_in() -> AppTest:
    auth.sign_up("alice@example.org", PASSWORD, "Alice Pantry")
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page(PAGE).run()
    assert not at.exception
    return at


def user_id() -> int:
    return auth.log_in("alice@example.org", PASSWORD).id


# ---------------------------------------------------------------- starting one

def test_with_no_applications_the_page_opens_on_the_start_flow(signed_in):
    body = page_text(signed_in)
    assert "You have no applications yet" in body
    assert signed_in.radio[0].options == list(start_application.ROUTES.values())


def test_the_page_explains_what_each_route_does_before_you_pick(signed_in):
    body = page_text(signed_in)
    assert "An application in GrantBridge is a workspace" in body
    assert "you file it on the funder's own portal" in body


def test_the_upload_route_states_its_limits_and_takes_only_three_types(signed_in):
    at = signed_in
    at.radio[0].set_value(start_application.ROUTES["documents"]).run()
    assert not at.exception
    body = page_text(at)
    assert f"{docs.MAX_BYTES // 1_048_576} MB" in body and f"{docs.MAX_PAGES}" in body
    assert "no OCR" in body
    assert "will not do" in body and "invent" in body
    assert list(at.get("file_uploader")[0].proto.type) == [".pdf", ".docx", ".txt"]


def test_a_blank_application_can_be_created_and_the_page_switches_to_it(signed_in):
    at = signed_in
    at.radio[0].set_value(start_application.ROUTES["blank"]).run()
    at.text_input[0].input("Harborview Reading Fund")
    at.button[0].click().run()
    assert not at.exception
    assert [a["title"] for a in repo.list_applications(user_id())] == ["Harborview Reading Fund"]
    assert "Harborview Reading Fund" in page_text(at)   # now the workspace, not the start flow


def test_once_an_application_exists_the_page_opens_on_the_workspace(signed_in):
    at = signed_in
    repo.create_application(user_id(), "Existing application")
    at.switch_page(PAGE).run()
    assert "You have no applications yet" not in page_text(at)
    assert any(b.label == "New application" for b in at.button)


def test_the_new_application_button_reopens_the_start_flow(signed_in):
    at = signed_in
    repo.create_application(user_id(), "Existing application")
    at.switch_page(PAGE).run()
    next(b for b in at.button if b.label == "New application").click().run()
    assert not at.exception
    assert "Start an application" in page_text(at)
    assert any(b.label == "Back to your applications" for b in at.button)


# ---------------------------------------------------------------- the outline tab

def payload_for(uid: int) -> tuple[dict, dict]:
    document = docs.Document(name="nofo.txt", kind="txt", text=NOFO, pages=None, truncated=False)
    found = sol.extract(uid, [document], want_mock=True)
    shape = outline.extract(uid, [document], want_mock=True)
    return found.data, shape.data


def test_without_an_outline_the_tab_offers_to_read_one_into_this_application(signed_in):
    """An application that already exists must be able to gain an outline without being recreated."""
    at = signed_in
    app_id = repo.create_application(user_id(), "No outline yet")
    at.switch_page(PAGE).run()
    assert "No outline yet for this application" in page_text(at)
    start = next(b for b in at.button if b.label == "Read a solicitation into this application")
    start.click().run()
    assert not at.exception
    # the start flow opens on the upload route, already aimed at this application
    assert at.session_state[start_application.MODE] == "new"
    assert at.session_state["new_app_route"] == "documents"
    assert at.session_state["imp_app"] == app_id
    assert "Before you upload" in page_text(at)


def test_an_imported_outline_is_shown_with_its_requirements_and_source(signed_in):
    uid = user_id()
    app_id = repo.create_application(uid, "Harborview")
    _, shape = payload_for(uid)
    outline.apply_import(uid, app_id, shape, {})
    at = signed_in
    at.switch_page(PAGE).run()
    assert not at.exception
    body = page_text(at)
    assert "The outline the funder asked for" in body
    headings = [s["heading"] for s in repo.list_outline_sections(uid, app_id)]
    assert "Need" in headings and "Approach" in headings
    assert "What this section must contain" in body   # the funder's own requirements, per section


def test_the_tab_states_that_ai_drafting_is_elsewhere(signed_in):
    uid = user_id()
    app_id = repo.create_application(uid, "Harborview")
    _, shape = payload_for(uid)
    outline.apply_import(uid, app_id, shape, {})
    at = signed_in
    at.switch_page(PAGE).run()
    assert "AI drafting is on the **Write answers** tab" in page_text(at)


def test_an_outline_whose_sections_hold_writing_cannot_be_removed(signed_in):
    uid = user_id()
    app_id = repo.create_application(uid, "Harborview")
    _, shape = payload_for(uid)
    outline.apply_import(uid, app_id, shape, {})
    first = repo.list_outline_sections(uid, app_id)[0]
    repo.save_outline_response(uid, first["id"], "Work I do not want to lose.")
    at = signed_in
    at.switch_page(PAGE).run()
    remove = [b for b in at.button if b.label == "Remove this outline"]
    assert remove, "the remove control should be on the page"
    remove[0].click().run()
    assert at.error, "removing an outline with writing in it must be refused"
    assert repo.list_outline_sections(uid, app_id), "the sections are still there"

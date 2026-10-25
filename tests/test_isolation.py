"""Defense 1: server-side user-data isolation, checked for every user-scoped data function.

Each function in repo.py whose first parameter is user_id gets a case below in which Bob, using his own user
id but Alice's record ids, tries to read or change Alice's data. The coverage test fails if anyone adds a new
user-scoped function without adding its isolation case.
"""

import inspect
from pathlib import Path

import pytest

from datetime import date

from grantbridge import auth, demo, pursuit, repo, timeline

PASSWORD = "correct horse battery staple"
SECRET = "ALICE-PRIVATE-TEXT"


@pytest.fixture
def world():
    alice = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    app_id = demo.load_demo_data(alice.id)
    repo.save_organization(alice.id, {"name": "Alice Org", "mission": SECRET})
    sid = repo.list_sections(alice.id, app_id)[0].id
    repo.save_section_answer(alice.id, sid, f"{SECRET} answer")
    repo.save_section_answer(alice.id, sid, f"{SECRET} answer v2")
    ids = {
        "alice": alice.id, "app": app_id, "section": sid,
        "fact": repo.add_section_fact(alice.id, sid, "Who leads?", answer=SECRET, status="answered"),
        "pending_fact": repo.add_section_fact(alice.id, sid, "Pending?"),
        "requirement": (repo.add_requirements(alice.id, app_id, [f"{SECRET} rule"]),
                        repo.list_requirements(alice.id, app_id)[0]["id"])[1],
        "version": repo.list_versions(alice.id, sid)[-1]["id"],
        "draft": repo.add_draft(alice.id, sid, f"{SECRET} draft", "mock", {}),
        "review": repo.add_review(alice.id, sid, "hash", "mock", {"checklist": []}),
        "proposal_review": repo.add_proposal_review(alice.id, app_id, "mock", {"sections": []}, {"summary": SECRET}),
        "budget_item": repo.add_budget_item(alice.id, app_id, dict(BUDGET_LINE, description=SECRET)),
        "budget_narrative": repo.add_budget_narrative(alice.id, app_id, "mock", "hash", SECRET, {}),
    }
    timeline.build_plan(alice.id, app_id, today=date(2026, 10, 21))
    ids["milestone"] = repo.get_timeline(alice.id, app_id)["milestones"][0]["id"]
    pursuit.assess(alice.id, grant_id="sample-01", want_mock=True, today=date(2026, 10, 21))
    repo.save_capacity_settings(alice.id, {"hours_per_week": 9, "note": SECRET})
    ids["commitment"] = repo.add_commitment(alice.id, f"{SECRET} report", 5, "2026-12-01")
    repo.add_drift_assessment(alice.id, "sample-01", "hash", "mock", {"summary": SECRET, "overall": "low"})
    repo.save_award_feasibility(alice.id, "grant:sample-01", notice=f"{SECRET} notice", inputs={"award": 123})
    repo.save_award_feasibility(alice.id, f"application:{app_id}", notice=f"{SECRET} application notice")
    repo.save_finance_settings(alice.id, {"cash_reserves": 4321, "note": SECRET})
    repo.save_demo_state(alice.id, {"grant_ids": ["sample-01"], "profile_before": {"mission": SECRET}})
    repo.save_solicitation_import(alice.id, {"fields": {"title": SECRET}, "groups": {}},
                                  {"nofo.txt": f"{SECRET} solicitation text"})
    repo.add_outline_sections(alice.id, app_id, [{"heading": "Need", "purpose": SECRET,
                                                  "elements": [{"text": SECRET, "excerpt": SECRET}],
                                                  "excerpt": SECRET}])
    ids["outline_section"] = repo.list_outline_sections(alice.id, app_id)[0]["id"]
    repo.save_application_outline(alice.id, app_id, {
        "criteria": [{"name": SECRET, "kind": "scored", "objectives": [{"text": SECRET, "excerpt": SECRET}],
                      "rating_rules": [], "max_points": None, "weight_percent": None, "threshold": None,
                      "excerpt": SECRET}],
        "components": [{"name": SECRET, "kind": "form", "condition": SECRET, "contents": [],
                        "excerpt": SECRET}]})
    repo.link_solicitation_import(alice.id, app_id, {"fields": {"title": SECRET}, "groups": {}})
    repo.set_tick(alice.id, sid, "item-1", True)
    repo.add_message(alice.id, "user", f"{SECRET} question")
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    return ids, bob.id


BUDGET_LINE = {"category": "Personnel", "description": "Coordinator", "quantity": "1", "unit_cost": "100",
               "funding_source": "grant"}


def denied(call):
    with pytest.raises(repo.NotFound):
        call()


def alice_untouched(ids):
    a = ids["alice"]
    assert repo.get_organization(a)["mission"] == SECRET
    assert repo.get_section(a, ids["section"])["answer"] == f"{SECRET} answer v2"
    assert [f["answer"] for f in repo.list_section_facts(a, ids["section"])][0] == SECRET
    assert repo.latest_draft(a, ids["section"])["text"] == f"{SECRET} draft"
    assert repo.latest_review(a, ids["section"]) is not None
    assert repo.list_ticks(a, ids["section"]) == {"item-1"}
    assert len(repo.list_requirements(a, ids["app"])) == 1
    assert [r["payload"]["summary"] for r in repo.list_proposal_reviews(a, ids["app"])] == [SECRET]
    assert [(i["description"], i["unit_cost_cents"]) for i in repo.list_budget_items(a, ids["app"])] == [(SECRET, 10000)]
    assert repo.latest_budget_narrative(a, ids["app"])["text"] == SECRET
    assert repo.get_capacity_settings(a) == {"hours_per_week": 9, "note": SECRET}
    assert [c["title"] for c in repo.list_commitments(a)] == [f"{SECRET} report"]
    assert repo.latest_drift_assessment(a, "sample-01")["payload"]["summary"] == SECRET
    assert repo.get_award_feasibility(a, "grant:sample-01")["notice"] == f"{SECRET} notice"
    assert repo.get_award_feasibility(a, "grant:sample-01")["inputs"] == {"award": 123}
    assert repo.get_award_feasibility(a, f"application:{ids['app']}")["notice"] == f"{SECRET} application notice"
    assert repo.get_finance_settings(a) == {"cash_reserves": 4321, "note": SECRET}
    [assessment] = repo.list_pursuit_assessments(a, "grant:sample-01")
    assert assessment["outcome"] == "verify" and assessment["application_id"] == ids["app"]
    plan = repo.get_timeline(a, ids["app"])
    assert plan["deadline"] == "2026-12-11" and len(plan["milestones"]) == 7
    assert plan["milestones"][0]["done_at"] is None and plan["milestones"][0]["due_date"] == "2026-11-08"
    assert repo.list_messages(a)[-1]["content"] == f"{SECRET} question"
    assert "sample-01" in repo.saved_grant_ids(a)


# Bob (b) attacks Alice's records (i). Each case either proves Bob sees nothing of Alice's, or that the
# call is refused with NotFound; every case then checks Alice's data is unchanged.
CASES = {
    # reads of "my own" data return only Bob's
    "get_organization": lambda i, b: repo.get_organization(b)["mission"] != SECRET or pytest.fail("leak"),
    "list_applications": lambda i, b: repo.list_applications(b) == [] or pytest.fail("leak"),
    "saved_grant_ids": lambda i, b: repo.saved_grant_ids(b) == set() or pytest.fail("leak"),
    "list_saved_grants": lambda i, b: repo.list_saved_grants(b) == [] or pytest.fail("leak"),
    "list_messages": lambda i, b: repo.list_messages(b) == [] or pytest.fail("leak"),
    "application_for_grant": lambda i, b: repo.application_for_grant(b, "sample-01") is None or pytest.fail("leak"),
    "list_open_milestones": lambda i, b: repo.list_open_milestones(b) == [] or pytest.fail("leak"),
    "get_capacity_settings": lambda i, b: repo.get_capacity_settings(b) == {} or pytest.fail("leak"),
    "list_commitments": lambda i, b: repo.list_commitments(b) == [] or pytest.fail("leak"),
    "latest_drift_assessment": lambda i, b: repo.latest_drift_assessment(b, "sample-01") is None or pytest.fail("leak"),
    "list_outline_sections": lambda i, b: repo.list_outline_sections(b, i["app"]) == [] or pytest.fail("leak"),
    "get_application_outline": lambda i, b: repo.get_application_outline(b, i["app"]) is None or pytest.fail("leak"),
    "add_outline_sections": lambda i, b: denied(
        lambda: repo.add_outline_sections(b, i["app"], [{"heading": "Taken over"}])),
    "save_outline_response": lambda i, b: denied(
        lambda: repo.save_outline_response(b, i["outline_section"], "Taken over")),
    "set_outline_ticks": lambda i, b: denied(lambda: repo.set_outline_ticks(b, i["outline_section"], [0])),
    "delete_outline_section": lambda i, b: denied(lambda: repo.delete_outline_section(b, i["outline_section"])),
    "save_application_outline": lambda i, b: denied(
        lambda: repo.save_application_outline(b, i["app"], {"criteria": []})),
    "set_objective_ticks": lambda i, b: denied(lambda: repo.set_objective_ticks(b, i["app"], 0, [0])),
    "set_component_state": lambda i, b: denied(lambda: repo.set_component_state(b, i["app"], 0, "in hand")),
    "delete_application_outline": lambda i, b: denied(lambda: repo.delete_application_outline(b, i["app"])),
    "latest_solicitation_import": lambda i, b: (repo.latest_solicitation_import(b) is None
                                                and repo.latest_solicitation_import(b, i["app"]) is None
                                                ) or pytest.fail("leak"),
    # writes under another account's id are refused, or land in the caller's own account and leave Alice alone
    "save_solicitation_import": lambda i, b: repo.save_solicitation_import(b, {"fields": {}}, {"a.txt": "x"}),
    "link_solicitation_import": lambda i, b: denied(
        lambda: repo.link_solicitation_import(b, i["app"], {"fields": {}})),
    "delete_solicitation_imports": lambda i, b: repo.delete_solicitation_imports(b),
    "fill_blank_application_fields": lambda i, b: denied(
        lambda: repo.fill_blank_application_fields(b, i["app"], title="Taken over")),
    "list_pursuit_assessments": lambda i, b: (repo.list_pursuit_assessments(b, "grant:sample-01") == []
                                              and repo.list_pursuit_assessments(b) == []) or pytest.fail("leak"),
    "get_award_feasibility": lambda i, b: (repo.get_award_feasibility(b, "grant:sample-01") is None
                                           and repo.get_award_feasibility(b, f"application:{i['app']}") is None
                                           ) or pytest.fail("leak"),
    "list_award_feasibility": lambda i, b: repo.list_award_feasibility(b) == [] or pytest.fail("leak"),
    "get_finance_settings": lambda i, b: repo.get_finance_settings(b) == {} or pytest.fail("leak"),
    "get_demo_state": lambda i, b: repo.get_demo_state(b) == {} or pytest.fail("leak"),
    "save_demo_state": lambda i, b: (repo.save_demo_state(b, {"grant_ids": ["sample-02"]}),
                                     repo.get_demo_state(i["alice"])["grant_ids"] == ["sample-01"]
                                     or pytest.fail("leak"))[1],
    "clear_demo_state": lambda i, b: (repo.clear_demo_state(b),
                                      repo.get_demo_state(i["alice"])["grant_ids"] == ["sample-01"]
                                      or pytest.fail("leak"))[1],
    # reads with Alice's ids
    "get_application": lambda i, b: repo.get_application(b, i["app"]) is None or pytest.fail("leak"),
    "list_sections": lambda i, b: repo.list_sections(b, i["app"]) == [] or pytest.fail("leak"),
    "get_section": lambda i, b: repo.get_section(b, i["section"]) is None or pytest.fail("leak"),
    "list_requirements": lambda i, b: repo.list_requirements(b, i["app"]) == [] or pytest.fail("leak"),
    "list_section_facts": lambda i, b: denied(lambda: repo.list_section_facts(b, i["section"])),
    "latest_draft": lambda i, b: denied(lambda: repo.latest_draft(b, i["section"])),
    "list_versions": lambda i, b: denied(lambda: repo.list_versions(b, i["section"])),
    "latest_review": lambda i, b: denied(lambda: repo.latest_review(b, i["section"])),
    "list_ticks": lambda i, b: denied(lambda: repo.list_ticks(b, i["section"])),
    "list_proposal_reviews": lambda i, b: denied(lambda: repo.list_proposal_reviews(b, i["app"])),
    "list_budget_items": lambda i, b: denied(lambda: repo.list_budget_items(b, i["app"])),
    "latest_budget_narrative": lambda i, b: denied(lambda: repo.latest_budget_narrative(b, i["app"])),
    "get_timeline": lambda i, b: denied(lambda: repo.get_timeline(b, i["app"])),
    # writes with Alice's ids
    "update_application": lambda i, b: denied(lambda: repo.update_application(b, i["app"], {"status": "Declined"})),
    "delete_application": lambda i, b: denied(lambda: repo.delete_application(b, i["app"])),
    "add_section": lambda i, b: denied(lambda: repo.add_section(b, i["app"], "Injected question")),
    "add_sections": lambda i, b: denied(lambda: repo.add_sections(b, i["app"], ["Injected"])),
    "save_section_answer": lambda i, b: denied(lambda: repo.save_section_answer(b, i["section"], "Overwritten")),
    "delete_section": lambda i, b: denied(lambda: repo.delete_section(b, i["section"])),
    "add_requirements": lambda i, b: denied(lambda: repo.add_requirements(b, i["app"], ["Injected rule"])),
    "delete_requirement": lambda i, b: denied(lambda: repo.delete_requirement(b, i["requirement"])),
    "add_section_fact": lambda i, b: denied(lambda: repo.add_section_fact(b, i["section"], "Injected?")),
    "answer_section_fact": lambda i, b: denied(lambda: repo.answer_section_fact(b, i["pending_fact"], "hijack")),
    "delete_section_fact": lambda i, b: denied(lambda: repo.delete_section_fact(b, i["fact"])),
    "add_draft": lambda i, b: denied(lambda: repo.add_draft(b, i["section"], "Injected draft", "mock", {})),
    "delete_drafts": lambda i, b: denied(lambda: repo.delete_drafts(b, i["section"])),
    "restore_version": lambda i, b: denied(lambda: repo.restore_version(b, i["section"], i["version"])),
    "add_review": lambda i, b: denied(lambda: repo.add_review(b, i["section"], "h", "mock", {"checklist": []})),
    "set_tick": lambda i, b: denied(lambda: repo.set_tick(b, i["section"], "item-1", False)),
    "add_proposal_review": lambda i, b: denied(lambda: repo.add_proposal_review(b, i["app"], "mock", {}, {})),
    "add_budget_item": lambda i, b: denied(lambda: repo.add_budget_item(b, i["app"], BUDGET_LINE)),
    "update_budget_item": lambda i, b: denied(lambda: repo.update_budget_item(b, i["budget_item"],
                                                                              dict(BUDGET_LINE, unit_cost="0"))),
    "delete_budget_item": lambda i, b: denied(lambda: repo.delete_budget_item(b, i["budget_item"])),
    "add_budget_narrative": lambda i, b: denied(lambda: repo.add_budget_narrative(b, i["app"], "mock", "h", "x", {})),
    "save_timeline": lambda i, b: denied(lambda: repo.save_timeline(
        b, i["app"], "2027-01-01", "user", {}, [(step, "2026-12-01") for step in repo.TIMELINE_STEPS])),
    "update_milestone": lambda i, b: denied(lambda: repo.update_milestone(b, i["milestone"], "2026-11-01", True)),
    "delete_timeline": lambda i, b: denied(lambda: repo.delete_timeline(b, i["app"])),
    "delete_commitment": lambda i, b: denied(lambda: repo.delete_commitment(b, i["commitment"])),
    "add_pursuit_assessment": lambda i, b: denied(lambda: repo.add_pursuit_assessment(
        b, "grant:sample-01", "sample-01", i["app"], "strong", "mock", {"settings": {}})),
    # writes to "my own" data never touch Alice's
    "save_organization": lambda i, b: repo.save_organization(b, {"name": "Bob Org", "mission": "Bob's"}),
    "save_grant": lambda i, b: repo.save_grant(b, "sample-02"),
    "unsave_grant": lambda i, b: repo.unsave_grant(b, "sample-01"),
    "create_application": lambda i, b: repo.create_application(b, "Bob's application"),
    "create_application_from_grant": lambda i, b: (repo.create_application_from_grant(b, "sample-01") != i["app"]
                                                   or pytest.fail("shared application")),
    "add_message": lambda i, b: repo.add_message(b, "user", "Bob's message"),
    "clear_messages": lambda i, b: repo.clear_messages(b),
    "save_capacity_settings": lambda i, b: repo.save_capacity_settings(b, {"hours_per_week": 1}),
    "add_commitment": lambda i, b: repo.add_commitment(b, "Bob's report", 2, "2026-12-01"),
    "add_drift_assessment": lambda i, b: repo.add_drift_assessment(b, "sample-01", "h", "mock", {"overall": "high"}),
    # Bob cannot write to Alice's application's analysis; writing his own copy for a shared grant leaves hers alone
    "save_award_feasibility": lambda i, b: (
        denied(lambda: repo.save_award_feasibility(b, f"application:{i['app']}", notice="hijack")),
        repo.save_award_feasibility(b, "grant:sample-01", notice="Bob's own notice", inputs={"award": 1})),
    "save_finance_settings": lambda i, b: repo.save_finance_settings(b, {"cash_reserves": 1}),
}


def user_scoped_functions() -> set[str]:
    return {name for name, fn in inspect.getmembers(repo, inspect.isfunction)
            if fn.__module__ == repo.__name__ and list(inspect.signature(fn).parameters)[:1] == ["user_id"]}


def test_every_user_scoped_function_has_an_isolation_case():
    missing = user_scoped_functions() - set(CASES)
    assert not missing, f"Add isolation cases for: {sorted(missing)}"
    assert not set(CASES) - user_scoped_functions(), "Remove cases for functions that no longer exist"


@pytest.mark.parametrize("name", sorted(CASES))
def test_other_accounts_cannot_reach_alices_data(world, name):
    ids, bob = world
    CASES[name](ids, bob)
    alice_untouched(ids)


def test_bob_never_sees_alices_text_anywhere(world, fresh_db):
    ids, bob = world
    readable = [repo.get_organization(bob), repo.list_applications(bob), repo.list_messages(bob),
                repo.list_saved_grants(bob), repo.saved_grant_ids(bob)]
    assert SECRET not in str(readable)


def test_the_signed_in_user_comes_only_from_the_server_session():
    """Pages never take a user id from the URL; the id lives in Streamlit's server-side session state."""
    root = Path(__file__).resolve().parents[1]
    for path in [root / "streamlit_app.py", *(root / "app_pages").glob("*.py"), *(root / "grantbridge").glob("*.py")]:
        text = path.read_text(encoding="utf-8")
        assert "query_params" not in text, path.name
        assert "experimental_get_query_params" not in text, path.name

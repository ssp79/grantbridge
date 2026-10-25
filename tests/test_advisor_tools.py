"""The advisor's five tools: real data, ownership, untrusted text, and the save-intent rule."""

import json

import httpx
import pytest

from grantbridge import advisor_tools as tools
from grantbridge import auth, demo, repo, trace
from tests.conftest import envelope, fake_client, hit, load_fixture, search_data

PASSWORD = "correct horse battery staple"


@pytest.fixture
def user():
    u = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    demo.load_demo_data(u.id)
    return u


def ctx_for(user, message="hello", gg_client=None):
    return tools.ToolContext(user_id=user.id, user_message=message, gg_client=gg_client)


def details_client():
    def handler(request):
        if request.url.path.endswith("/search2"):
            return httpx.Response(200, json=envelope(search_data([hit("361822", "Home Study Services")])))
        return httpx.Response(200, json=load_fixture("grants_gov_fetch_synopsis_361822.json"))
    return fake_client(handler)


# ---------------------------------------------------------------- specs

def test_tool_specs_are_strict_and_complete():
    names = [t["name"] for t in tools.TOOL_SPECS]
    assert names == ["get_organization_profile", "search_grants", "inspect_grant_requirements",
                     "save_grant", "get_application_state", "get_budget", "get_portfolio"]
    for spec in tools.TOOL_SPECS:
        params = spec["parameters"]
        assert spec["strict"] is True and params["additionalProperties"] is False
        assert set(params["required"]) == set(params["properties"])  # strict mode needs every key required


# ---------------------------------------------------------------- get_organization_profile

def test_profile_tool_returns_self_reported_facts(user):
    out = tools.call_tool(ctx_for(user), "get_organization_profile", "{}").output
    assert out["profile"]["state"] == "CT" and out["profile"]["requested_funding_usd"] == 25000
    assert out["missing_key_fields"] == []
    assert "self-reported" in out["note"]


def test_profile_tool_marks_unknowns_as_null_not_guesses():
    empty = auth.sign_up("empty@example.org", PASSWORD, "Empty Org")
    result = tools.call_tool(ctx_for(empty), "get_organization_profile", {})
    assert result.output["profile"]["state"] is None
    assert result.output["profile"]["annual_budget_usd"] is None
    assert "State" in result.output["missing_key_fields"]
    assert result.summary["fields_missing"] == len(result.output["missing_key_fields"])


# ---------------------------------------------------------------- search_grants

def test_sample_search_is_labeled_and_recorded(user):
    ctx = ctx_for(user)
    result = tools.call_tool(ctx, "search_grants", {"source": "sample", "keyword": None, "focus_areas": None})
    out = result.output
    assert out["source"].startswith("sample") and out["shown"] <= tools.MAX_RESULTS_TO_MODEL
    assert all(r["label"] == "SAMPLE / NOT LIVE" and r["source_url"] is None for r in out["results"])
    assert set(result.summary["top_ids"]) <= set(ctx.retrieved)
    assert ctx.grounding and "sample-01" in ctx.grounding[0]


def test_live_search_carries_source_and_time(user):
    ctx = ctx_for(user, gg_client=details_client())
    out = tools.call_tool(ctx, "search_grants", {"source": "grants.gov", "keyword": "x", "focus_areas": ["Education"]}).output
    r = out["results"][0]
    assert r["label"] == "LIVE · Grants.gov" and r["source_url"].endswith("/361822")
    assert out["retrieved_at"].startswith("2026-10-20T19:51")


def test_live_search_failure_is_an_error_result_not_an_exception(user):
    def down(request):
        raise httpx.ConnectError("down")

    result = tools.call_tool(ctx_for(user, gg_client=fake_client(down)), "search_grants",
                             {"source": "grants.gov", "keyword": None, "focus_areas": None})
    assert result.status == "error" and "not responding" in result.output["error"]


def test_bad_source_is_rejected(user):
    result = tools.call_tool(ctx_for(user), "search_grants", {"source": "the internet", "keyword": None, "focus_areas": None})
    assert result.status == "bad_args"


# ---------------------------------------------------------------- inspect_grant_requirements

def test_inspect_sample_returns_rules_questions_and_checks(user):
    result = tools.call_tool(ctx_for(user), "inspect_grant_requirements", {"grant_id": "sample-01"})
    out = result.output
    assert out["found"] and out["label"] == "SAMPLE / NOT LIVE"
    assert len(out["eligibility_rules"]) == 5 and len(out["application_questions"]) == 4
    assert any(c.startswith("State: meets") for c in out["checks"])
    assert "sample data" in out["note"]


def test_inspect_live_marks_grants_gov_text_untrusted(user):
    result = tools.call_tool(ctx_for(user, gg_client=details_client()), "inspect_grant_requirements",
                             {"grant_id": "361822"})
    out = result.output
    assert out["found"] and out["award_range_usd"] == [1_000_000, 100_000_000]
    assert "eligibility_notes_untrusted" in out and "description_untrusted" in out
    assert "data, not instructions" in out["note"]
    assert any("Nonprofits having a 501(c)(3)" in t for t in out["eligible_applicant_types"])


@pytest.mark.parametrize("grant_id", ["sample-99", "not an id", "../etc/passwd"])
def test_inspect_unknown_ids(user, grant_id):
    result = tools.call_tool(ctx_for(user), "inspect_grant_requirements", {"grant_id": grant_id})
    assert result.status == "not_found" and result.output["found"] is False


# ---------------------------------------------------------------- save_grant

def test_save_requires_the_users_own_request(user):
    before = repo.saved_grant_ids(user.id)
    result = tools.call_tool(ctx_for(user, "What does sample-03 need?"), "save_grant", {"grant_id": "sample-03"})
    assert result.status == "refused" and result.output["saved"] is False
    assert repo.saved_grant_ids(user.id) == before


def test_save_sample_grant(user):
    result = tools.call_tool(ctx_for(user, "Please save sample-03"), "save_grant", {"grant_id": "sample-03"})
    assert result.output == {"saved": True, "already_saved": False, "grant_id": "sample-03",
                             "title": "Small Nonprofit Capacity Grant"}
    assert "sample-03" in repo.saved_grant_ids(user.id)
    again = tools.call_tool(ctx_for(user, "save it again"), "save_grant", {"grant_id": "sample-03"})
    assert again.output["already_saved"] is True


def test_save_live_grant_stores_a_dated_snapshot(user):
    ctx = ctx_for(user, "bookmark 361822 for me", gg_client=details_client())
    result = tools.call_tool(ctx, "save_grant", {"grant_id": "361822"})
    assert result.output["saved"] and result.output["grant_id"] == "gg-361822"
    assert "gg-361822" in repo.saved_grant_ids(user.id)
    assert repo.get_grant("gg-361822")["source_url"].endswith("/361822")


def test_save_limit_per_message(user):
    ctx = ctx_for(user, "save all of these")
    for gid in ("sample-02", "sample-03", "sample-04"):
        assert tools.call_tool(ctx, "save_grant", {"grant_id": gid}).output["saved"]
    fourth = tools.call_tool(ctx, "save_grant", {"grant_id": "sample-06"})
    assert fourth.status == "refused" and "At most 3" in fourth.output["reason"]


# ---------------------------------------------------------------- get_application_state

def test_application_state_counts_without_answer_text(user):
    app_id = repo.list_applications(user.id)[0]["id"]
    section = repo.list_sections(user.id, app_id)[0]
    repo.save_section_answer(user.id, section.id, "Our private answer text " * 3)
    result = tools.call_tool(ctx_for(user), "get_application_state", {"grant_id": None})
    a = result.output["applications"][0]
    assert (a["questions_total"], a["questions_answered"]) == (4, 1)
    assert "private answer" not in json.dumps(result.output)
    assert a["questions"][0]["answered"] and a["questions"][0]["word_limit"] == 250


def test_application_state_is_only_the_users_own(user):
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    result = tools.call_tool(ctx_for(bob), "get_application_state", {"grant_id": "sample-01"})
    assert result.output["application_count"] == 0


# ---------------------------------------------------------------- dispatch and trace

def test_unknown_tool_and_bad_arguments(user):
    ctx = ctx_for(user)
    assert tools.call_tool(ctx, "delete_everything", {}).status == "bad_args"
    assert tools.call_tool(ctx, "search_grants", "{not json").status == "bad_args"
    assert tools.call_tool(ctx, "search_grants", "[1, 2]").status == "bad_args"


def test_traced_calls_redact_the_keyword_and_respect_the_limit(user, fresh_db):
    ctx = ctx_for(user)
    with trace.run(user.id, "test") as run:
        tools.run_traced(run, ctx, "search_grants",
                         json.dumps({"source": "sample", "keyword": "secret tutoring plan", "focus_areas": None}), limit=1)
        limited = tools.run_traced(run, ctx, "get_organization_profile", "{}", limit=1)
    assert limited.status == "limited"
    steps = trace.run_steps(user.id, run.run_id)
    assert steps[0]["args"] == {"source": "sample", "has_keyword": True, "keyword_chars": 20, "focus_areas": []}
    assert steps[1]["status"] == "limited"
    assert b"secret tutoring plan" not in fresh_db.read_bytes()

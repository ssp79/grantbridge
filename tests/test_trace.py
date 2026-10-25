"""The agent trace is privacy-safe, owner-only, bounded, and survives failures."""

import httpx
import pytest

from grantbridge import auth, demo, grant_search as gs, trace
from tests.conftest import envelope, fake_client, hit, search_data

PASSWORD = "correct horse battery staple"


@pytest.fixture
def alice():
    return auth.sign_up("alice@example.org", PASSWORD, "Alice Org")


def test_safe_fields_keeps_only_allowlisted_plain_values():
    kept = trace.safe_fields({
        "source": "grants.gov", "state": "CT", "focus_areas": ["Education", "Youth"],
        "categories": ["ED"], "result_count": 3, "from_cache": True,
        "keyword": "our secret pantry", "email": "alice@example.org", "mission": "We feed families",
    })
    assert kept == {"source": "grants.gov", "state": "CT", "focus_areas": ["Education", "Youth"],
                    "categories": ["ED"], "result_count": 3, "from_cache": True}


@pytest.mark.parametrize("key, value", [
    ("focus_areas", ["Education", "my private note"]),   # not in the focus-area vocabulary
    ("state", "Connecticut, 12 Elm St"),                  # not a state code
    ("categories", ["ED", "<script>"]),
    ("grant_id", "alice@example.org"),
    ("result_count", "12 results for 'pantry'"),           # numeric keys reject strings
    ("model", "x" * 200),
])
def test_free_text_under_allowed_keys_is_dropped(key, value):
    assert trace.safe_fields({key: value}) == {}


def test_search_trace_records_shape_not_keyword_text(alice, fresh_db):
    f = gs.filters_from_profile(demo.demo_fixture()["profile"], keyword="harbor lantern confidential")
    client = fake_client(lambda r: httpx.Response(200, json=envelope(search_data([hit("1", "A")]))))
    outcome = gs.run_search(alice.id, f, gs.LIVE, client=client)
    steps = trace.run_steps(alice.id, outcome.run_id)
    assert [s["tool"] for s in steps] == ["build_query_from_profile", "search_grants_gov", "filter_and_rank"]
    assert [s["kind"] for s in steps] == ["code", "tool", "code"]
    assert steps[0]["args"]["keyword_chars"] == len("harbor lantern confidential")
    assert steps[1]["summary"]["result_count"] == 1
    raw = fresh_db.read_bytes()
    assert b"confidential" not in raw and b"alice@example.org" in raw  # email only in the users table
    assert b"alice@example.org" not in str(steps).encode()


def test_sample_search_trace(alice):
    outcome = gs.run_search(alice.id, gs.filters_from_profile(demo.demo_fixture()["profile"]), gs.SAMPLE)
    steps = trace.run_steps(alice.id, outcome.run_id)
    assert [s["tool"] for s in steps] == ["build_query_from_profile", "search_sample_grants", "rank_results"]
    assert steps[2]["summary"]["top_ids"][0].startswith("sample-")


def test_traces_are_private_to_their_owner(alice):
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    outcome = gs.run_search(alice.id, gs.filters_from_profile({}), gs.SAMPLE)
    assert trace.list_runs(bob.id) == []
    assert trace.run_steps(bob.id, outcome.run_id) == []
    assert len(trace.run_steps(alice.id, outcome.run_id)) == 3


def test_runs_are_pruned_per_user(alice):
    for _ in range(trace.MAX_RUNS_PER_USER + 5):
        with trace.run(alice.id, "test") as r:
            with r.step("noop", kind="code") as s:
                s.ok()
    assert len(trace.list_runs(alice.id, limit=500)) == trace.MAX_RUNS_PER_USER


def test_a_crashing_step_is_saved_as_an_error_with_only_the_error_type(alice):
    with pytest.raises(RuntimeError):
        with trace.run(alice.id, "boom") as r:
            with r.step("explode", kind="tool"):
                raise RuntimeError("secret details from a stack trace")
    run = trace.list_runs(alice.id)[0]
    assert run["status"] == "error"
    step = trace.run_steps(alice.id, run["id"])[0]
    assert step["status"] == "error" and step["summary"] == {"error_kind": "RuntimeError"}


def test_deleting_an_account_deletes_its_traces(alice, fresh_db):
    gs.run_search(alice.id, gs.filters_from_profile({}), gs.SAMPLE)
    auth.delete_account(alice.id, PASSWORD)
    import sqlite3
    conn = sqlite3.connect(fresh_db)
    assert conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM agent_steps").fetchone()[0] == 0

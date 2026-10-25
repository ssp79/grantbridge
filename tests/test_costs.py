"""Tokenomics: prices from a cited file, provider-reported usage only, a cost per run, and the measurement harness."""

import json
from types import SimpleNamespace

import pytest

from grantbridge import auth, config, demo, llm, pricing, trace, ui
from grantbridge import fit_explainer as fx
from grantbridge import grant_search as gs
from grantbridge import repo
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text


def usage_obj(input_tokens=10_000, cached=4_000, written=2_000, output=1_000, reasoning=600):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output,
                           input_tokens_details=SimpleNamespace(cached_tokens=cached, cache_write_tokens=written),
                           output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning))


# 4,000 ordinary x $0.10 + 4,000 cached x $0.01 + 2,000 written x $0.125 + 1,000 output x $0.50, per 1M tokens
EXPECTED = (4_000 * 0.10 + 4_000 * 0.01 + 2_000 * 0.125 + 1_000 * 0.50) / 1_000_000  # $0.00119


@pytest.fixture
def alice():
    return auth.sign_up("alice@example.org", PASSWORD, "Alice Org")


def record_call(user_id, usage: dict, model="gpt-6-luna", kind="explain_fit"):
    with trace.run(user_id, kind) as run:
        with run.step("model", kind="llm") as step:
            step.add_usage(usage, model)
            step.ok()
    return run.run_id


# ---------------------------------------------------------------- prices come from a cited, configurable file

def test_rates_come_from_the_pricing_file_with_a_source_and_date():
    price = pricing.price_for("gpt-6-luna")
    assert price.source_url == "https://developers.openai.com/api/docs/pricing" and price.checked == "2026-10-20"
    t = price.tiers[0]
    assert (t.input, t.cached_input, t.cache_write, t.output) == (0.10, 0.01, 0.125, 0.50)
    assert pricing.price_for("gpt-6-luna-global") is price  # the name Azure reports in responses


def test_cost_follows_openais_caching_rules():
    cost, ref = pricing.estimate("gpt-6-luna", {"input_tokens": 10_000, "cached_tokens": 4_000,
                                                "cache_write_tokens": 2_000, "output_tokens": 1_000})
    assert cost == pytest.approx(EXPECTED) and "checked 2026-10-20" in ref


def test_a_request_over_272k_input_tokens_is_billed_at_the_long_context_rates():
    cost, _ = pricing.estimate("gpt-6-luna", {"input_tokens": 300_000, "output_tokens": 1_000})
    assert cost == pytest.approx((300_000 * 0.20 + 1_000 * 0.75) / 1_000_000)


@pytest.mark.parametrize("model, usage, reason", [
    ("someone-elses-model", {"input_tokens": 100, "output_tokens": 10}, "no price for someone-elses-model"),
    ("gpt-6-luna", {"usage_status": "not reported"}, "no usage reported"),
    ("gpt-6-luna", {}, "no usage reported"),
])
def test_no_estimate_rather_than_a_guess(model, usage, reason):
    cost, ref = pricing.estimate(model, usage)
    assert cost is None and reason in ref


def test_a_portkey_cache_hit_costs_nothing():
    cost, ref = pricing.estimate("gpt-6-luna", {"input_tokens": 5_000, "output_tokens": 500, "gateway_cache": "hit"})
    assert cost == 0.0 and "Portkey cache hit" in ref


def test_a_broken_or_missing_pricing_file_means_no_estimates_not_a_crash(tmp_path, monkeypatch):
    bad = tmp_path / "pricing.json"
    bad.write_text('{"models": [{"model": "gpt-6-luna", "tiers": [{"input": "cheap"}]}]}', encoding="utf-8")
    monkeypatch.setenv("GRANTBRIDGE_PRICING_FILE", str(bad))
    assert pricing.price_for("gpt-6-luna") is None
    assert pricing.estimate("gpt-6-luna", {"input_tokens": 1, "output_tokens": 1})[0] is None
    monkeypatch.setenv("GRANTBRIDGE_PRICING_FILE", str(tmp_path / "missing.json"))
    assert pricing.price_for("gpt-6-luna") is None


# ---------------------------------------------------------------- usage is the provider's own numbers

def test_usage_includes_cache_writes_and_says_when_it_was_reported():
    assert llm.usage_of(SimpleNamespace(usage=usage_obj())) == {
        "input_tokens": 10_000, "cached_tokens": 4_000, "cache_write_tokens": 2_000, "output_tokens": 1_000,
        "reasoning_tokens": 600, "usage_status": "reported"}
    missing = llm.usage_of(SimpleNamespace(usage=None))
    assert missing["usage_status"] == "not reported" and missing["input_tokens"] == 0
    totals_only = SimpleNamespace(usage=SimpleNamespace(input_tokens=50, output_tokens=5))
    assert llm.usage_of(totals_only)["usage_status"] == "no cache detail"


class RawClient:
    """Like the OpenAI SDK: responses.with_raw_response.create returns headers plus .parse()."""

    def __init__(self, headers):
        response = SimpleNamespace(usage=usage_obj(), model="gpt-6-luna-global", output_text="{}")
        raw = SimpleNamespace(headers=headers, parse=lambda: response)
        self.responses = SimpleNamespace(with_raw_response=SimpleNamespace(create=lambda **kw: raw))


def test_respond_reads_the_gateway_cache_result_and_served_model_from_response_headers():
    _, usage = llm.respond(RawClient({"x-portkey-cache-status": "HIT", "x-ms-served-model": "gpt-6-luna-2026-09-22"}),
                           model="gpt-6-luna", input="hi")
    assert usage["gateway_cache"] == "hit" and usage["served_model"] == "gpt-6-luna-2026-09-22"
    _, usage = llm.respond(RawClient({"x-portkey-cache-status": "<script>" * 9}), model="gpt-6-luna", input="hi")
    assert usage["gateway_cache"] == "" and usage["served_model"] == "gpt-6-luna-global"  # odd header dropped


def test_respond_calls_plain_fakes_directly():
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: SimpleNamespace(usage=usage_obj())))
    _, usage = llm.respond(fake, model="gpt-6-luna", input="hi")
    assert usage["input_tokens"] == 10_000 and usage["gateway_cache"] == ""


def test_fresh_answers_add_portkeys_documented_refresh_header_only():
    portkey = config.Settings(provider="portkey", model="gpt-6-luna", base_url="https://api.portkey.ai/v1",
                              key_source="test", api_key="pk-test-not-real")
    assert llm.client_options(portkey)["default_headers"] == {"x-portkey-provider": "openai"}
    assert llm.client_options(portkey, fresh_answers=True)["default_headers"] == {
        "x-portkey-provider": "openai", "x-portkey-cache-force-refresh": "true"}
    openai = config.Settings(provider="openai", model="gpt-x", base_url=None, key_source="test", api_key="sk-test")
    assert "default_headers" not in llm.client_options(openai, fresh_answers=True)


# ---------------------------------------------------------------- every run records its cost

def test_a_model_step_records_model_tokens_and_estimated_cost(alice):
    run_id = record_call(alice.id, {**llm.usage_of(SimpleNamespace(usage=usage_obj())), "gateway_cache": "miss",
                                    "served_model": "gpt-6-luna-2026-09-22"})
    step = trace.run_steps(alice.id, run_id)[0]
    assert (step["model"], step["served_model"], step["gateway_cache"]) == ("gpt-6-luna", "gpt-6-luna-2026-09-22", "miss")
    assert step["cache_write_tokens"] == 2_000 and step["cost_usd"] == pytest.approx(EXPECTED)
    run = trace.list_runs(alice.id)[0]
    assert run["cost_usd"] == pytest.approx(EXPECTED) and run["model_calls"] == 1 and run["tool_calls"] == 0
    assert trace.run_summary(alice.id, run_id)["cost_usd"] == pytest.approx(EXPECTED)
    assert ui.usd(run["cost_usd"]) == "$0.00119"


def test_unreported_usage_is_shown_as_unknown_never_as_zero_cost(alice):
    run_id = record_call(alice.id, llm.usage_of(SimpleNamespace(usage=None)))
    summary = trace.run_summary(alice.id, run_id)
    assert summary["cost_usd"] is None and summary["unreported_calls"] == 1
    assert "not reported" in ui.usage_line(summary) and "cost not estimated" in ui.usage_line(summary)
    assert ui.trace_rows(trace.run_steps(alice.id, run_id))[0]["Tokens in / cached / out"] == "not reported"


def test_a_model_call_that_raised_has_unknown_cost(alice):
    with pytest.raises(RuntimeError):
        with trace.run(alice.id, "explain_fit") as run:
            with run.step("model", kind="llm"):
                raise RuntimeError("timeout")
    assert trace.list_runs(alice.id)[0]["cost_usd"] is None


def test_portkey_cache_hits_cost_nothing_and_do_not_use_the_budget(alice):
    record_call(alice.id, {"input_tokens": 9_000, "output_tokens": 1_000, "gateway_cache": "hit"})
    assert trace.list_runs(alice.id)[0]["cost_usd"] == 0.0
    assert llm.tokens_used_today(alice.id) == 0


def test_cheap_runs_cannot_push_recent_ai_runs_out_of_the_budget(alice):
    """Regression: the trace kept only the newest 50 runs, so 50 plain searches reset the daily AI budget."""
    record_call(alice.id, {"input_tokens": 90_000, "output_tokens": 5_000})
    for _ in range(trace.MAX_RUNS_PER_USER + 5):
        gs.run_search(alice.id, gs.filters_from_profile({}), gs.SAMPLE)
    assert llm.tokens_used_today(alice.id) == 95_000
    assert len(trace.list_runs(alice.id, limit=500)) == trace.MAX_RUNS_PER_USER + 1  # plain runs still pruned


def test_explain_drafting_and_advisor_use_one_prompt_cache_per_account(alice):
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    keys = []

    class Model:
        def __init__(self):
            self.responses = self

        def parse(self, **kw):
            keys.append(kw["prompt_cache_key"])
            exp = fx.FitExplanation(verdict="possible fit", confidence="low", summary="s", reasons=[],
                                    uncertainties=["u"], verify_next=["v"])
            return SimpleNamespace(output_parsed=exp, usage=usage_obj())

    for user in (alice, bob):
        demo.load_demo_data(user.id)
        org = repo.get_organization(user.id)
        fx.run_explain(user.id, org, gs.sample_result(repo.get_grant("sample-01"), gs.filters_from_profile(org)),
                       client=Model(), model="gpt-6-luna")
    assert keys == [llm.cache_key("explain", alice.id), llm.cache_key("explain", bob.id)]
    assert keys[0] != keys[1] and all(k.startswith("grantbridge-explain-") for k in keys)


def test_cache_keys_differ_between_installations_even_for_the_same_account_id(alice, tmp_path, monkeypatch):
    """Regression: every new database numbers its first account 1, so per-account keys alone let a fresh
    installation (or measurement run) read prompt caches another one had written."""
    from grantbridge.db import init_db, install_id

    first, first_install = llm.cache_key("advisor", alice.id), install_id()
    monkeypatch.setenv("GRANTBRIDGE_DB", str(tmp_path / "second-install.db"))
    init_db()
    second = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    assert second.id == alice.id and llm.cache_key("advisor", second.id) != first
    assert not first.endswith(f"-u{alice.id}") and first_install not in first  # a hash: neither id is visible


# ---------------------------------------------------------------- the pages show it

@pytest.fixture
def live_key(monkeypatch):
    """Pretend a key is configured so the pages offer live mode; the model itself is always a fake."""
    fake = config.Settings(provider="portkey", model="gpt-6-luna", base_url="https://api.portkey.ai/v1",
                           key_source="test", api_key="pk-test-not-real")
    monkeypatch.setattr(config, "resolve_settings", lambda *a, **k: fake)
    monkeypatch.delenv("GRANTBRIDGE_ADVISOR_MODE", raising=False)


def test_agent_activity_shows_tokens_cost_and_where_the_rates_come_from(alice, live_key, monkeypatch):
    body = {"reply": "Your profile says you are in Bridgeport, Connecticut.", "known_facts": [], "assumptions": [],
            "clarifying_question": None, "grant_ids_cited": []}
    model = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: SimpleNamespace(
        output=[SimpleNamespace(type="message")], output_text=json.dumps(body), usage=usage_obj())))
    monkeypatch.setattr(llm, "get_client", lambda **kw: (model, "gpt-6-luna"))
    demo.load_demo_data(alice.id)
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page("app_pages/advisor.py").run()
    at.chat_input[0].set_value("Where are we based?").run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Model calls"] == "1" and metrics["Tool calls"] == "0" and metrics["Estimated cost"] == "$0.00119"
    text = page_text(at)
    assert "**Tokens:** 10,000 in (4,000 read from the prompt cache, 2,000 written to it) · 1,000 out" in text
    assert "OpenAI API pricing, gpt-6-luna, Standard tier (checked 2026-10-20)" in text


def test_settings_lists_ai_runs_with_their_cost(alice, live_key):
    record_call(alice.id, llm.usage_of(SimpleNamespace(usage=usage_obj())))
    at = log_in(fresh_app(), "alice@example.org", PASSWORD)
    at.switch_page("app_pages/settings.py").run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["AI runs, last 24 h"] == "1" and metrics["Estimated cost, last 24 h"] == "$0.00119"
    table = at.dataframe[0].value
    assert list(table["Est. cost"]) == ["$0.00119"] and list(table["Model"]) == ["gpt-6-luna"]


# ---------------------------------------------------------------- the measurement harness

def test_offline_measurement_writes_a_labeled_report(tmp_path):
    from scripts import measure_costs as mc

    assert mc.main(["--offline", "--reps", "1", "--out", str(tmp_path)]) == 0
    data = json.loads(next(tmp_path.glob("measurements-offline-*.json")).read_text(encoding="utf-8"))
    report = next(tmp_path.glob("cost-report-offline-*.md")).read_text(encoding="utf-8")
    assert len(data["records"]) == 7 * len(mc.SETTINGS)
    explain = next(r for r in data["records"] if r["workflow"] == "Explain fit")
    # scripted usage: 1,000 input tokens all written to the cache, 300 output
    assert explain["totals"]["cost_usd"] == pytest.approx((1_000 * 0.125 + 300 * 0.50) / 1_000_000)
    assert "OFFLINE: scripted model, made-up token counts (not a measurement)" in report
    for heading in ("## Cost per run", "## Monthly cost", "## Quality checks", "## Every measured run"):
        assert heading in report
    assert "@example.org" not in report and "@example.org" not in json.dumps(data)


def test_a_run_without_usage_is_reported_as_unknown(tmp_path):
    from scripts import measure_costs as mc

    class NoUsage(mc.ScriptedModel):
        def parse(self, **kwargs):
            response = super().parse(**kwargs)
            response.usage = None
            return response

    records = mc.measure(NoUsage(), "gpt-6-luna", {"baseline": {}}, reps=1, progress=lambda *a: None)
    report = mc.render(records, {"when": "now", "mode": "test", "model": "gpt-6-luna", "reps": 1})
    explain = [r for r in records if r["workflow"] == "Explain fit"]
    assert all(r["totals"]["cost_usd"] is None for r in explain)
    assert "3 did not report usage and have no cost" in report
    assert "not reported | not reported" in report

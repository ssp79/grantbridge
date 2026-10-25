"""Can We Afford to Win?: the arithmetic, missing and ambiguous terms, what-if scenarios, the AI's terms checked by
code, the integration with Should We Pursue? and the Portfolio Strategist, and what stays private."""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from grantbridge import auth, demo, portfolio, pursuit, repo, timeline, trace
from grantbridge import award_feasibility as af
from grantbridge import validation as v

PASSWORD = "correct horse battery staple"
EVAL = json.loads((af.REPO_ROOT / "data" / "fixtures" / "award_terms_eval.json").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 21)


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    monkeypatch.setattr(timeline, "current_date", lambda: TODAY)
    monkeypatch.setenv("GRANTBRIDGE_ADVISOR_MODE", "mock")


@pytest.fixture
def user():
    u = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    demo.load_demo_data(u.id)
    return u


class Model:
    """A scripted stand-in for the model. It records every request it receives."""

    def __init__(self, reply):
        self.reply, self.requests = reply, []
        self.responses = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        usage = SimpleNamespace(input_tokens=1200, output_tokens=400,
                                input_tokens_details=SimpleNamespace(cached_tokens=0),
                                output_tokens_details=SimpleNamespace(reasoning_tokens=100))
        return SimpleNamespace(output_text=json.dumps(self.reply), usage=usage)


def cond(area, quote, **fields):
    base = {"area": area, "quote": quote, "summary": "A term.", "percent": None, "basis": None, "match_type": None,
            "payment_type": None, "every_months": None, "days": None, "months": None, "fte": None, "ambiguity": None}
    return {**base, **fields}


def values(**changes):
    """A complete set of inputs, every one 'from you', changed as asked."""
    base = {"award": 60000, "period_months": 12, "payment_type": "reimbursement", "claim_every_months": 3,
            "payment_delay_days": 30, "advance_percent": 0, "match_percent": 0, "match_basis": "award",
            "match_type": "cash", "committed_match": 0, "cash_reserves": 20000, "indirect_rate": None,
            "hours_per_report": 6, "monthly_spending": 5000}
    return {k: {"value": x, "from": "you"} for k, x in {**base, **changes}.items()}


# ---------------------------------------------------------------- the arithmetic

def test_the_match_on_the_award_and_on_the_total_project_cost():
    assert af.match_needed(60000, 25, "award") == 15000
    assert af.match_needed(60000, 50, "total_project") == 60000  # half of (award + match) is the match
    assert af.match_needed(60000, 25, "total_project") == 20000  # 25% of 80,000
    assert af.match_needed(60000, 100, "award") == 60000  # a 1:1 match
    assert af.match_needed(60000, 0, "award") == 0 and af.match_needed(0, 50, "award") == 0
    assert af.match_needed(33333, 33, "award") == 11000  # rounded half up to whole dollars
    with pytest.raises(v.ValidationError):
        af.match_needed(60000, 100, "total_project")


def test_reimbursement_cash_flow_by_hand():
    """$60,000 over 12 months, $5,000 a month, claimed quarterly and paid 30 days after each quarter."""
    sim = af.simulate(award=60000, months=12, monthly_spending=5000, cash_match=0, committed_match=0,
                      payment_type="reimbursement", advance_percent=0, claim_every_months=3, delay_days=30)
    assert sim["first_payment_day"] == 91 + 30  # the first quarter ends on day 91; payment 30 days later
    assert sim["grant_pays"] == 60000 and sim["own_spending"] == 0
    # just before each payment, a quarter (91 or 92 days) plus 30 days of spending waits: about 15,000 + 30 × 164.38
    assert 19800 < sim["peak_need"] < 20100
    assert sim["series"][0]["cash_tied_up"] == 164  # day 0: the first day's spending, 5,000 × 12 / 365


def test_payment_dates_follow_the_calendar():
    assert af.schedule(365, 12, 3) == [91, 182, 274, 365]  # four quarters, the last at the end of the year
    assert len(af.schedule(730, 24, 3)) == 8 and af.schedule(730, 24, 3)[-1] == 730  # no one-day period at the end
    assert af.schedule(395, 13, 3) == [91, 182, 274, 365, 395]  # a real final month is its own claim
    assert af.schedule(182, 6, 12) == [182]  # claims less often than the grant lasts: one, at the end


def test_installments_are_an_assumption_the_summary_states():
    d = af.demo({"payment_type": "installments", "advance_percent": 50})
    assert d["result"]["peak_need"] < af.demo()["result"]["peak_need"]
    assert any("assumed to come in equal installments every 3 months" in line and "award agreement" in line
               for line in d["summary"])


def test_an_advance_ties_up_less_cash_than_reimbursement():
    common = dict(award=60000, months=12, monthly_spending=5000, cash_match=0, committed_match=0,
                  claim_every_months=3, delay_days=30)
    reimbursed = af.simulate(payment_type="reimbursement", advance_percent=0, **common)
    paid_ahead = af.simulate(payment_type="advance", advance_percent=100, **common)
    half = af.simulate(payment_type="installments", advance_percent=50, **common)
    assert paid_ahead["peak_need"] == 0 and paid_ahead["first_payment_day"] == 0
    assert 0 < half["peak_need"] < reimbursed["peak_need"]
    # half on day 0, then 4 installments of 7,500 each 30 days after a quarter: the last arrives after the year ends
    assert half["peak_need"] == 7500 and half["peak_day"] == 364
    assert half["first_payment_day"] == 0


def test_cash_match_uses_committed_money_first():
    common = dict(award=60000, months=12, monthly_spending=7500, cash_match=30000, payment_type="advance",
                  advance_percent=100, claim_every_months=3, delay_days=0)
    none_committed = af.simulate(committed_match=0, **common)
    part_committed = af.simulate(committed_match=10000, **common)
    assert none_committed["peak_need"] == 30000  # the whole match comes from the organization's own cash
    assert part_committed["peak_need"] == 20000
    assert none_committed["own_spending"] == 30000


def test_scenarios_move_in_the_expected_direction():
    def peak(**changes):
        v_ = values(**changes)
        return af.analyze(v_, {}, annual_budget=285000, staff_size=3)["peak_need"]
    assert peak(payment_delay_days=0) < peak(payment_delay_days=30) < peak(payment_delay_days=90)
    assert peak(match_percent=0) < peak(match_percent=25) < peak(match_percent=50)
    assert peak(award=30000, monthly_spending=2500) < peak(award=60000, monthly_spending=5000)
    assert peak(claim_every_months=1) < peak(claim_every_months=3)


def test_indirect_staffing_and_reporting_numbers():
    terms = {"indirect_cap_percent": {"value": 10}, "reports_per_year": {"value": 4}, "required_fte": {"value": 0.5},
             "staffing_months": {"value": "period"}}
    r = af.analyze(values(indirect_rate=18), terms, annual_budget=285000, staff_size=3)
    assert r["indirect_unrecovered"] == 4364  # 60,000 / 1.10 of direct costs × 8 points
    assert r["report_hours"] == 24.0 and r["staffing_months"] == 12 and r["staff_share"] == 17
    assert r["monthly_operating"] == 23750


# ---------------------------------------------------------------- the verdict

def test_verdict_levels_with_known_terms():
    def level(reserves):
        v_ = values(cash_reserves=reserves)
        return af.verdict(v_, af.analyze(v_, {}, annual_budget=285000, staff_size=3))
    burden, tight, ok = level(10000), level(30000), level(200000)
    assert burden["level"] == "burden" and burden["known"] and "more than the $10,000" in burden["reasons"][0]
    assert tight["level"] == "tight"
    assert ok["level"] == "ok"


def test_an_assumed_term_is_never_a_burden_it_is_unknown():
    v_ = values(cash_reserves=1000)
    v_["payment_delay_days"] = {"value": 60, "from": "assumption"}
    out = af.verdict(v_, af.analyze(v_, {}, annual_budget=None, staff_size=None))
    assert out["level"] == "unknown" and out["projected"] == "burden" and not out["known"]
    assert any("days until a claim is paid" in r for r in out["reasons"])
    v_["cash_reserves"] = {"value": None, "from": "unknown"}
    out = af.verdict(v_, af.analyze(v_, {}, annual_budget=None, staff_size=None))
    assert out["level"] == "unknown" and "Enter your cash reserves" in out["reasons"][0]


# ---------------------------------------------------------------- reading the terms (patterns, no AI)

def test_the_sample_demonstration():
    d = af.demo()
    t, r = d["terms"], d["result"]
    assert t["period_months"]["value"] == 24 and t["payment_type"]["value"] == "reimbursement"
    assert t["claim_every_months"]["value"] == 3 and t["payment_delay_days"]["value"] == 90
    assert (t["match_percent"]["value"], t["match_basis"]["value"], t["match_type"]["value"]) == (50, "total_project", "cash")
    assert t["indirect_cap_percent"]["value"] == 10 and t["required_fte"]["value"] == 0.5
    assert all(c["quote"] in d["notice"] for c in d["conditions"])  # every term is quoted from the notice
    assert r["match_needed"] == 55000 and r["match_gap"] == 45000  # 50% of the total project = 100% of the award
    assert r["first_payment_month"] == 6.0
    assert d["verdict"]["level"] == "burden" and d["verdict"]["known"]
    assert r["peak_need"] > d["values"]["cash_reserves"]["value"]
    assert any("not check eligibility or strategic fit" in line for line in d["summary"])
    # what if the funder paid half up front and the match were 25% of the award?
    better = af.demo({"payment_type": "installments", "advance_percent": 50, "match_percent": 25,
                      "match_basis": "award"})
    assert better["result"]["peak_need"] < r["peak_need"] and better["result"]["match_needed"] == 13750


@pytest.mark.parametrize("notice", EVAL["notices"], ids=[n["id"] for n in EVAL["notices"]])
def test_patterns_never_invent_a_term(notice):
    """Whatever the patterns find must be stated in the text; a silent notice gives no terms at all."""
    conditions = af.pattern_conditions({"listing": "", "notice": notice["text"]})
    terms = af.assemble(conditions)
    for field, expected in notice["expected"].items():
        found = (terms.get(field) or {}).get("value")
        if expected is None and found is not None:
            assert field == "match_basis" or found == 0, f"{field} invented: {found}"
    if notice["id"] == "D-silent":
        assert conditions == [] and len(terms["unknown_areas"]) == len(af.AREAS)
    if notice["id"] == "E-injection":
        assert terms["match_percent"]["value"] == 100 and terms["payment_type"]["value"] == "reimbursement"
        assert all("ignore all previous" not in c["quote"].lower() for c in conditions)


def test_an_encouraged_match_is_zero_and_says_so():
    terms_text = EVAL["notices"][2]["text"]
    [match] = [c for c in af.pattern_conditions({"notice": terms_text}) if c["area"] == "match"]
    assert match["percent"] == 0 and "encouraged" in match["ambiguity"]


# ---------------------------------------------------------------- the AI's terms, checked by code

def test_ai_terms_are_kept_only_with_a_real_quote_and_their_own_numbers(user):
    notice = EVAL["notices"][0]["text"]
    reply = {"conditions": [
        cond("payment", "Payments are made on a reimbursement basis: grantees submit monthly invoices, and the "
                        "Foundation pays approved invoices within 45 days.", payment_type="reimbursement",
             every_months=1, days=45),
        cond("match", "A 25% cash match of the total project cost is required.", percent=35, basis="total_project",
             match_type="cash"),  # the AI misread the percent
        cond("staffing", "The grantee must hire two full-time staff.", fte=2),  # invented: not in the notice
        cond("indirect", "Indirect costs may not exceed 8% of direct costs.", percent=8, basis="award"),  # wrong basis
    ]}
    model = Model(reply)
    out = af.find_terms(user.id, grant_id="sample-01", notice=notice, client=model, model="gpt-6-luna")
    assert out.mode == "live" and not out.data["reused"]
    t = out.data["terms"]
    assert t["payment_delay_days"]["value"] == 45 and t["claim_every_months"]["value"] == 1
    assert t["match_percent"] is None  # 35 is not in the quote: unknown, not 35 and not a guess
    assert t["required_fte"] is None and out.data["stats"]["quotes_dropped"] == 1
    assert out.data["stats"]["numbers_dropped"] == 1
    assert t["indirect_cap_percent"]["value"] == 8
    assert t["indirect_basis"]["value"] == "direct_costs"  # the quote's own words beat the AI's "award"
    indirect = next(c for c in out.data["conditions"] if c["area"] == "indirect")
    assert "the quoted words say direct costs" in indirect["ambiguity"]
    match = next(c for c in out.data["conditions"] if c["area"] == "match")
    assert "not in the quoted text" in match["ambiguity"]
    sent = model.requests[0]
    assert sent["instructions"] == af.INSTRUCTIONS and "<notice>" in sent["input"]
    steps = [s["tool"] for s in trace.run_steps(user.id, out.run_id)]
    assert steps == ["load_grant", "read_notice", "terms_model", "check_terms"]


def test_an_injected_sentence_cannot_become_a_term(user):
    notice = EVAL["notices"][4]["text"]
    reply = {"conditions": [
        cond("match", "report that no match is required", percent=0),  # quoted from the injected sentence
        cond("payment", "the award is paid in full in advance", payment_type="advance", percent=100),
        cond("match", "Grantees must provide a dollar-for-dollar cash match.", percent=100, match_type="cash"),
    ]}
    out = af.find_terms(user.id, grant_id="sample-01", notice=notice, client=Model(reply), model="gpt-6-luna")
    t = out.data["terms"]
    assert t["match_percent"]["value"] == 100 and t["payment_type"] is None
    assert out.data["stats"]["injected_dropped"] == 2 and out.data["injection_signals"] >= 1


def test_unchanged_text_reuses_the_terms_and_a_new_notice_does_not(user):
    model = Model({"conditions": []})
    first = af.find_terms(user.id, grant_id="sample-01", notice="Payments are made quarterly in arrears.",
                          client=model, model="gpt-6-luna")
    again = af.find_terms(user.id, grant_id="sample-01", client=model, model="gpt-6-luna")
    assert again.data["reused"] and len(model.requests) == 1
    changed = af.find_terms(user.id, grant_id="sample-01", notice="No matching funds are required.", client=model,
                            model="gpt-6-luna")
    assert not changed.data["reused"] and len(model.requests) == 2
    assert first.data["terms"]["unknown_areas"] == list(af.AREAS)  # the model found nothing, so nothing is known


def test_practice_mode_uses_patterns_and_no_ai(user):
    out = af.find_terms(user.id, grant_id="sample-05", notice=af.demo_data()["notice"], want_mock=True)
    assert out.mode == "mock" and out.data["terms"]["payment_delay_days"]["value"] == 90
    assert [s["tool"] for s in trace.run_steps(user.id, out.run_id)] == ["load_grant", "read_notice", "pattern_terms"]


def test_notices_are_validated():
    with pytest.raises(v.ValidationError):
        af.find_terms(1, grant_id="sample-01", notice="x" * (repo.MAX_NOTICE_CHARS + 1), want_mock=True)
    with pytest.raises(v.ValidationError):
        af.find_terms(1)


# ---------------------------------------------------------------- your numbers

def test_inputs_are_validated_and_saved_where_they_belong(user):
    af.find_terms(user.id, grant_id="sample-05", notice=af.demo_data()["notice"], want_mock=True)
    with pytest.raises(v.ValidationError):
        af.save_inputs(user.id, "grant:sample-05", {"payment_delay_days": 999})
    with pytest.raises(v.ValidationError):
        af.save_inputs(user.id, "grant:sample-05", {"cash_reserves": -5})
    with pytest.raises(v.ValidationError):
        af.save_inputs(user.id, "grant:sample-05", {"payment_type": "barter"})
    af.save_inputs(user.id, "grant:sample-05", {"cash_reserves": 30000, "award": 55000, "committed_match": 10000})
    assert repo.get_finance_settings(user.id) == {"cash_reserves": 30000}  # shared by every grant
    assert repo.get_award_feasibility(user.id, "grant:sample-05")["inputs"] == {"award": 55000, "committed_match": 10000}
    target = pursuit.load_target(user.id, grant_id="sample-05", fetch=False)
    a = af.analysis_for(user.id, target)
    assert a["values"]["award"]["from"] == "you" and a["values"]["payment_delay_days"]["from"] == "the grant's terms"
    assert a["values"]["hours_per_report"]["from"] == "assumption"
    assert a["verdict"]["level"] == "burden"
    af.save_inputs(user.id, "grant:sample-05", {"cash_reserves": ""})  # cleared: unknown again, not zero
    assert af.analysis_for(user.id, target)["verdict"]["level"] == "unknown"


def test_defaults_come_from_the_application_and_budget(user):
    target = pursuit.load_target(user.id, grant_id="sample-01", fetch=False)
    app_id = target.application["id"]
    repo.add_budget_item(user.id, app_id, {"category": "Supplies and materials", "description": "Books",
                                           "quantity": "1", "unit_cost": "2000", "funding_source": "cash_committed",
                                           "source_name": "A local bank", "justification": "Reading materials."})
    af.find_terms(user.id, grant_id="sample-01", want_mock=True)
    a = af.analysis_for(user.id, pursuit.load_target(user.id, grant_id="sample-01", fetch=False))
    assert a["values"]["award"] == {"value": target.application["amount_requested"], "from": "your application"}
    assert a["values"]["committed_match"] == {"value": 2000, "from": "your budget"}
    assert a["values"]["cash_reserves"] == {"value": None, "from": "unknown"}


# ---------------------------------------------------------------- the AI explanation, checked by code

def test_the_explanation_may_only_use_computed_numbers(user):
    af.find_terms(user.id, grant_id="sample-05", notice=af.demo_data()["notice"], want_mock=True)
    af.save_inputs(user.id, "grant:sample-05", {"cash_reserves": 30000, "award": 55000, "committed_match": 10000})
    target = pursuit.load_target(user.id, grant_id="sample-05", fetch=False)
    reply = {"explanation": "Winning $55,000 means finding $45,000 of match money. You would need $99,999 of extra "
                            "cash. This grant will likely be funded.",
             "tradeoffs": ["Ask the funder about an advance."], "questions_for_funder": ["Can part be paid early?"]}
    out = af.explain(user.id, target, client=Model(reply), model="gpt-6-luna")
    text = out.data["explanation"]
    assert "$55,000" in text and "$45,000" in text and "99,999" not in text  # an invented figure is replaced
    assert "likely be funded" not in text  # predictions are removed
    assert out.data["tradeoffs"] == ["Ask the funder about an advance."]
    saved = repo.get_award_feasibility(user.id, "grant:sample-05")["explanation"]
    assert saved["for_hash"] == af.explanation_hash(af.analysis_for(user.id, target))
    af.save_inputs(user.id, "grant:sample-05", {"cash_reserves": 90000})
    assert saved["for_hash"] != af.explanation_hash(af.analysis_for(user.id, target))  # now out of date


def test_explaining_needs_terms_first(user):
    target = pursuit.load_target(user.id, grant_id="sample-02", fetch=False)
    with pytest.raises(v.ValidationError, match="terms first"):
        af.explain(user.id, target, want_mock=True)


# ---------------------------------------------------------------- integration

def test_should_we_pursue_takes_caution_only_from_a_known_burden(user):
    af.find_terms(user.id, grant_id="sample-05", notice=af.demo_data()["notice"], want_mock=True)
    out = pursuit.assess(user.id, grant_id="sample-05", want_mock=True, today=TODAY)
    assert out.data["outcome"] != "caution"  # no reserves entered: unknown, so no change to the outcome
    assert out.data["dimensions"]["budget"]["award_feasibility"]["level"] == "unknown"
    assert any("Can we afford to win?" in a for a in out.data["next_actions"])
    af.save_inputs(user.id, "grant:sample-05", {"cash_reserves": 30000, "award": 55000, "committed_match": 10000})
    out = pursuit.assess(user.id, grant_id="sample-05", want_mock=True, today=TODAY)
    budget = out.data["dimensions"]["budget"]
    assert budget["cash_flow_burden"] and budget["level"] == "caution" and "cash_flow_burden" in out.data["rules_fired"]
    assert out.data["outcome"] in ("caution", "do_not_pursue")  # never "strong" while the burden stands
    af.save_inputs(user.id, "grant:sample-05", {"cash_reserves": 500000})
    out = pursuit.assess(user.id, grant_id="sample-05", want_mock=True, today=TODAY)
    assert "cash_flow_burden" not in out.data["rules_fired"]


def test_the_portfolio_defers_a_known_burden_only_when_asked(user):
    repo.save_grant(user.id, "sample-05")
    af.find_terms(user.id, grant_id="sample-05", notice=af.demo_data()["notice"], want_mock=True)
    af.save_inputs(user.id, "grant:sample-05", {"cash_reserves": 30000, "award": 55000, "committed_match": 10000})

    def status(**settings):
        result = portfolio.recommend(user.id, {"hours_per_week": 20, **settings}, today=TODAY)
        return next(c for c in result["candidates"] if c["key"] == "grant:sample-05")
    default = status()
    assert default["afford"]["level"] == "burden" and default["status"] != "excluded"
    assert status(defer_cash_burden=True)["status"] == "deferred"
    assert "strain your cash" in status(defer_cash_burden=True)["reasons"][0]
    # without the notice, the payment and match terms are unknown: never a reason to defer
    repo.save_award_feasibility(user.id, "grant:sample-05", notice="")
    af.find_terms(user.id, grant_id="sample-05", want_mock=True)
    unknown = status(defer_cash_burden=True)
    assert unknown["afford"]["level"] == "unknown" and not unknown["afford"]["known"]
    assert not any("strain your cash" in reason for reason in unknown["reasons"])


def test_settings_keep_the_new_option():
    assert portfolio.clean_settings({})["defer_cash_burden"] is False
    assert portfolio.clean_settings({"defer_cash_burden": True})["defer_cash_burden"] is True


# ---------------------------------------------------------------- privacy

def test_another_account_sees_nothing(user):
    af.find_terms(user.id, grant_id="sample-05", notice="PRIVATE-NOTICE " + af.demo_data()["notice"], want_mock=True)
    af.save_inputs(user.id, "grant:sample-05", {"cash_reserves": 30000})
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    target = pursuit.load_target(bob.id, grant_id="sample-05", fetch=False)
    assert af.analysis_for(bob.id, target) is None and af.signal(bob.id, target) is None
    assert repo.get_finance_settings(bob.id) == {}
    app_id = repo.list_applications(user.id)[0]["id"]
    with pytest.raises(repo.NotFound):
        af.find_terms(bob.id, application_id=app_id, want_mock=True)
    out = af.find_terms(bob.id, grant_id="sample-05", want_mock=True)
    assert out.data["terms"]["payment_type"] is None  # Bob's own analysis has no notice: Alice's never reaches it


def test_the_trace_keeps_counts_not_money_or_text(user):
    out = af.find_terms(user.id, grant_id="sample-05", notice=af.demo_data()["notice"], want_mock=True)
    stored = json.dumps(trace.run_steps(user.id, out.run_id))
    assert "reimbursement" not in stored and "55,000" not in stored and "Grantees" not in stored

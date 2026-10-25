"""The Can we afford to win? tab of Should We Pursue? (practice mode): the sample terms, your numbers, what if,
the explanation, and the finding reaching the pursuit assessment."""

from datetime import date

import pytest

from grantbridge import auth, demo, pursuit, repo, timeline
from grantbridge import award_feasibility as af
from tests.test_pages import PASSWORD, fresh_app, log_in, page_text

PICK = "grant:sample-05"


@pytest.fixture(autouse=True)
def mock_and_pinned_clock(monkeypatch):
    monkeypatch.setenv("GRANTBRIDGE_ADVISOR_MODE", "mock")  # no test may spend tokens
    monkeypatch.setattr(timeline, "current_date", lambda: date(2026, 10, 21))


@pytest.fixture
def at():
    user = auth.sign_up("alice@example.org", PASSWORD, "Alice Org")
    demo.load_demo_data(user.id)
    app = log_in(fresh_app(), "alice@example.org", PASSWORD)
    app.session_state["pursue_target"] = PICK
    app.switch_page("app_pages/pursue.py").run()
    assert not app.exception
    return app


def save_numbers(at, **numbers):
    for key, value in numbers.items():
        at.number_input(key=f"afford_{PICK}_{key}").set_value(value)
    next(b for b in at.button if b.label == "Save my numbers").click().run()
    assert not at.exception


def test_the_tab_starts_empty_and_says_what_it_does(at):
    assert [t.label for t in at.tabs][:2] == ["Should we pursue?", "Can we afford to win?"]
    assert any("No award terms found yet" in i.value for i in at.info)
    assert "not eligibility or strategic fit" in page_text(at)


def test_the_sample_terms_become_a_burden_once_your_numbers_are_in(at):
    at.button(key=f"afford_demo_{PICK}").click().run()
    assert not at.exception
    text = page_text(at)
    assert af.LEVELS["unknown"][0] in text  # no reserves entered yet: never a burden on a guess
    assert "Grantees must provide a cash match of at least 50% of the total project cost." in text
    assert "From the notice you added" in text
    save_numbers(at, cash_reserves=30000, award=55000, committed_match=10000)
    text = page_text(at)
    assert af.LEVELS["burden"][0] in text
    assert repo.get_finance_settings(1)["cash_reserves"] == 30000
    inputs = repo.get_award_feasibility(1, PICK)["inputs"]
    assert inputs == {"award": 55000, "committed_match": 10000}  # untouched numbers stay "from the terms"
    assert any("Your numbers are saved" in s.value for s in at.success)


def test_what_if_reruns_the_arithmetic_without_saving(at):
    at.button(key=f"afford_demo_{PICK}").click().run()
    save_numbers(at, cash_reserves=30000, award=55000, committed_match=10000)
    before = repo.get_award_feasibility(1, PICK)["inputs"]
    at.slider(key=f"afford_wi_{PICK}_delay").set_value(0).run()
    at.slider(key=f"afford_wi_{PICK}_match").set_value(0).run()
    assert not at.exception
    target = pursuit.load_target(1, grant_id="sample-05", fetch=False)
    saved = af.analysis_for(1, target)
    scenario = af.analysis_for(1, target, af.clean_inputs({"payment_delay_days": 0, "match_percent": 0,
                                                           "award": 55000, "payment_type": "reimbursement"}))
    assert scenario["result"]["peak_need"] < saved["result"]["peak_need"]
    assert scenario["result"]["match_needed"] == 0 and scenario["verdict"]["level"] != "burden"
    shown = page_text(at).split("**This scenario:**")[1]
    assert af.LEVELS[scenario["verdict"]["level"]][0] in shown
    assert repo.get_award_feasibility(1, PICK)["inputs"] == before  # a scenario saves nothing


def test_the_explanation_in_practice_mode_is_written_by_code(at):
    at.button(key=f"afford_demo_{PICK}").click().run()
    at.button(key=f"afford_explain_{PICK}").click().run()
    assert not at.exception
    text = page_text(at)
    assert "Practice mode: written by code from the numbers" in text
    save_numbers(at, cash_reserves=90000)
    assert "written for earlier numbers" in page_text(at)


def test_the_pursuit_assessment_shows_the_finding(at):
    at.button(key=f"afford_demo_{PICK}").click().run()
    save_numbers(at, cash_reserves=30000, award=55000, committed_match=10000)
    at.button(key=f"pursue_run_{PICK}").click().run()
    assert not at.exception
    [latest] = repo.list_pursuit_assessments(1, PICK)
    assert "cash_flow_burden" in latest["payload"]["rules_fired"]
    assert "Can We Afford to Win? found that winning would tie up more cash" in page_text(at)


def test_a_pasted_notice_is_read_and_kept_private(at):
    at.text_area(key=f"afford_notice_{PICK}").input("No matching funds are required. Grants are paid in two "
                                                    "installments, and 50% is paid in advance.")
    at.button(key=f"afford_find_{PICK}").click().run()
    assert not at.exception
    row = repo.get_award_feasibility(1, PICK)
    assert row["terms"]["terms"]["match_percent"]["value"] == 0
    assert row["terms"]["terms"]["advance_percent"]["value"] == 50
    bob = auth.sign_up("bob@example.org", PASSWORD, "Bob Org")
    assert repo.get_award_feasibility(bob.id, PICK) is None


def test_the_budget_tab_opens_the_check_for_its_grant():
    user = auth.sign_up("carol@example.org", PASSWORD, "Carol Org")
    app_id = demo.load_demo_data(user.id)
    at = log_in(fresh_app(), "carol@example.org", PASSWORD)
    at.switch_page("app_pages/applications.py").run()
    at.button(key=f"afford_budget_{app_id}").click().run()
    assert not at.exception
    assert at.title[0].value == "Should We Pursue?"
    assert at.selectbox(key="pursue_pick").value == "grant:sample-01"
    assert any("No award terms found yet" in i.value for i in at.info)


def test_the_portfolio_shows_the_check_and_the_switch(at):
    at.button(key=f"afford_demo_{PICK}").click().run()
    save_numbers(at, cash_reserves=30000, award=55000, committed_match=10000)
    repo.save_grant(1, "sample-05")
    at.switch_page("app_pages/portfolio.py").run()
    assert not at.exception
    assert "Can we afford to win? " + af.LEVELS["burden"][0] in page_text(at)
    at.toggle(key="pf_defer_cash").set_value(True).run()
    assert not at.exception
    assert "You chose to defer grants that would strain your cash" in page_text(at)

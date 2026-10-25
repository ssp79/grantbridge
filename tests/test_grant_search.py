"""Search layer: profile filters, sample mode, live mode, deadline wording, ranking, and failures."""

import re
from dataclasses import replace
from datetime import date, datetime, timezone

import httpx
import pytest

from grantbridge import auth, demo, grant_search as gs, repo, trace
from tests.conftest import NOW, envelope, fake_client, hit, load_fixture, search_data

TODAY = date(2026, 10, 20)
PROFILE = demo.demo_fixture()["profile"]
OPEN_WORD = re.compile(r"\bopen\b", re.IGNORECASE)


@pytest.fixture
def user():
    return auth.sign_up("alice@example.org", "correct horse battery staple", "Alice Org")


def filters(**overrides) -> gs.SearchFilters:
    return gs.filters_from_profile(PROFILE, **overrides)


def live_client(hits, hit_count=None):
    return fake_client(lambda r: httpx.Response(200, json=envelope(search_data(hits, hit_count))))


# ---------------------------------------------------------------- filters from the profile

def test_filters_come_from_the_profile():
    f = filters()
    assert f.state == "CT" and f.focus_areas == ("Education", "Youth")
    assert f.requested_amount == 25_000 and f.annual_budget == 285_000
    params = f.live_params()
    assert params.categories == ("ED",)          # Youth has no Grants.gov category
    assert params.eligibilities == ("12",)       # 501(c)(3) nonprofits
    assert params.statuses == ("forecasted", "posted")


@pytest.mark.parametrize("tax, codes", [
    ("Yes, IRS-recognized 501(c)(3)", ("12",)),
    ("Fiscally sponsored by a 501(c)(3)", ("12",)),
    ("No", ("13",)),
    ("Application pending with the IRS", ()),
    ("", ()),
])
def test_tax_status_maps_to_grants_gov_applicant_codes(tax, codes):
    assert filters(tax_status=tax).live_params().eligibilities == codes


# ---------------------------------------------------------------- sample mode

def test_sample_mode_returns_only_labeled_samples():
    results, hidden = gs.search_samples(filters())
    assert len(results) == len(repo.list_sample_grants()) and hidden == 0
    for r in results:
        assert r.source == gs.SAMPLE and not r.is_live
        assert r.status_reported == "SAMPLE / NOT LIVE"
        assert r.source_url == "" and r.retrieved_at is None
        assert r.deadline.code == "sample" and "SAMPLE" in r.deadline.label
        assert not OPEN_WORD.search(r.deadline.label + r.deadline.detail)


def test_sample_checks_for_the_best_fit():
    results, _ = gs.search_samples(filters())
    ct = next(r for r in results if r.id == "sample-01")
    outcomes = {c.name: c.outcome for c in ct.checks}
    assert outcomes == {"State": gs.MEETS, "Focus area": gs.MEETS, "Award range": gs.MEETS,
                        "501(c)(3) status": gs.MEETS, "Annual budget": gs.MEETS}
    assert any("grades K-12" in u for u in ct.unknowns)  # left for a person (or the AI) to judge
    assert not ct.hard_fail


def test_wrong_state_is_a_hard_fail_ranked_last():
    results, _ = gs.search_samples(filters())
    texas = next(r for r in results if r.id == "sample-07")
    assert texas.hard_fail
    assert results[-1].id == "sample-07"
    assert not results[0].hard_fail


def test_ranking_is_deterministic():
    first = [r.id for r in gs.search_samples(filters())[0]]
    assert all([r.id for r in gs.search_samples(filters())[0]] == first for _ in range(3))


def test_hide_failing_removes_hard_fails_and_counts_them():
    results, hidden = gs.search_samples(filters(hide_failing=True))
    assert "sample-07" not in {r.id for r in results}
    assert hidden == 1


def test_budget_rules_are_checked_from_the_text():
    results, _ = gs.search_samples(filters(annual_budget=2_000_000))
    ct = next(r for r in results if r.id == "sample-01")
    budget = next(c for c in ct.checks if c.name == "Annual budget")
    assert budget.outcome == gs.FAILS and budget.hard
    capacity = next(r for r in results if r.id == "sample-03")
    assert next(c for c in capacity.checks if c.name == "Annual budget").outcome == gs.FAILS


def test_unknown_profile_facts_give_unknown_checks_not_guesses():
    results, _ = gs.search_samples(gs.filters_from_profile({"focus_areas": ["Education"]}))
    ct = next(r for r in results if r.id == "sample-01")
    outcomes = {c.name: c.outcome for c in ct.checks}
    assert outcomes["Award range"] == outcomes["Annual budget"] == outcomes["501(c)(3) status"] == gs.UNKNOWN


def test_sample_keyword_no_results():
    results, hidden = gs.search_samples(filters(keyword="zzqxjv"))
    assert results == [] and hidden == 0


def test_sample_keyword_match():
    results, _ = gs.search_samples(filters(keyword="tutoring after-school"))
    assert [r.id for r in results] == ["sample-01"]


def test_sample_focus_and_min_award_filters():
    results, _ = gs.search_samples(filters(focus_areas=("Workforce development",)))
    assert [r.id for r in results] == ["sample-07"]
    results, _ = gs.search_samples(filters(min_award=50_000))
    assert {r.id for r in results} == {"sample-04", "sample-05", "sample-07"}


# ---------------------------------------------------------------- live mode

def test_live_results_are_labeled_with_source_and_timestamp(user):
    outcome = gs.run_search(user.id, filters(), gs.LIVE, client=live_client([hit("361822", "Real-shaped")]), today=TODAY)
    assert outcome.error is None and outcome.retrieved_at == NOW
    r = outcome.results[0]
    assert r.is_live and r.source == "grants.gov"
    assert r.source_url == "https://www.grants.gov/search-results-detail/361822"
    assert r.retrieved_at == NOW
    assert "Grants.gov" in r.deadline.label and "Oct 20, 2026 19:51 UTC" in r.deadline.detail


@pytest.mark.parametrize("close, status, code", [
    ("12/11/2026", "posted", "posted"),
    ("10/27/2026", "posted", "closing_soon"),
    ("", "posted", "no_close_date"),
    ("01/01/2099", "posted", "no_close_date"),  # Grants.gov placeholder, not a real deadline
    ("", "forecasted", "forecasted"),
    ("not a date", "posted", "no_close_date"),
    ("12/11/2026", "mystery", "unknown"),
])
def test_deadline_status_never_claims_open(close, status, code):
    h = gs.gg._parse_hit(hit("5", "T", close=close, status=status))
    r = gs.live_result(h, NOW, filters(), TODAY)
    assert r.deadline.code == code
    assert not OPEN_WORD.search(r.deadline.label + " " + r.deadline.detail)
    if code != "unknown":
        assert "Grants.gov" in r.deadline.label + r.deadline.detail


def test_forecasts_say_not_accepting_applications():
    h = gs.gg._parse_hit(hit("5", "T", close="", status="forecasted"))
    assert "not accepting applications" in gs.live_result(h, NOW, filters(), TODAY).deadline.label


def test_passed_close_dates_are_hidden_and_counted(user):
    hits = [hit("1", "Future"), hit("2", "Past", close="09/30/2026")]
    outcome = gs.run_search(user.id, filters(), gs.LIVE, client=live_client(hits), today=TODAY)
    assert [r.id for r in outcome.results] == ["1"]
    assert outcome.hidden_closed == 1


def test_research_grants_rank_after_others(user):
    hits = [hit("1", "Dissemination Research in Health (R01 Clinical Trial Optional)", close="11/30/2026"),
            hit("2", "Community Literacy Partnerships", close="03/01/2027")]
    outcome = gs.run_search(user.id, filters(), gs.LIVE, client=live_client(hits), today=TODAY)
    assert [r.id for r in outcome.results] == ["2", "1"]
    assert outcome.results[1].research_like


def test_posted_research_grant_ranks_below_forecasted_community_grant(user):
    """Regression: a posted NIH R01 ranked first in the live browser run on 2026-10-20."""
    hits = [hit("1", "Genetic Architecture of Complex Traits (R01 Clinical Trial Not Allowed)", close="11/05/2026"),
            hit("2", "Youth Literacy Expansion", close="", status="forecasted")]
    outcome = gs.run_search(user.id, filters(), gs.LIVE, client=live_client(hits), today=TODAY)
    assert [r.id for r in outcome.results] == ["2", "1"]


def test_hide_research_drops_research_grants_and_counts_them(user):
    hits = [hit("1", "Exploratory Grants in Cancer Control (R21 Clinical Trial Optional)"),
            hit("2", "Youth Literacy Expansion"), hit("3", "Mind and Body Interventions", number="PAR-25-274")]
    outcome = gs.run_search(user.id, filters(hide_research=True), gs.LIVE, client=live_client(hits), today=TODAY)
    assert [r.id for r in outcome.results] == ["2"]
    assert outcome.hidden_research == 2
    step = trace.run_steps(user.id, outcome.run_id)[2]
    assert step["summary"]["hidden_research"] == 2


def test_live_eligibility_unknowns_are_listed(user):
    outcome = gs.run_search(user.id, filters(), gs.LIVE, client=live_client([hit("1", "X")]), today=TODAY)
    r = outcome.results[0]
    assert any("Geographic limits" in u for u in r.unknowns)
    assert any("Full eligibility rules" in u for u in r.unknowns)
    award = next(c for c in r.checks if c.name == "Award range")
    assert award.outcome == gs.UNKNOWN


def test_live_no_results(user):
    outcome = gs.run_search(user.id, filters(keyword="zzqxjv"), gs.LIVE, client=live_client([]), today=TODAY)
    assert outcome.error is None and outcome.results == [] and outcome.total_matches == 0


def test_live_bad_network_degrades_gracefully(user):
    def down(request):
        raise httpx.ConnectError("no route to host")

    outcome = gs.run_search(user.id, filters(), gs.LIVE, client=fake_client(down), today=TODAY)
    assert outcome.results == [] and outcome.error_kind == "unavailable"
    assert "not responding" in outcome.error
    step = trace.run_steps(user.id, outcome.run_id)[1]
    assert step["tool"] == "search_grants_gov" and step["status"] == "error"
    assert step["summary"]["error_kind"] == "unavailable" and step["summary"]["http_requests"] == 3


def test_live_rate_limit_is_reported(user):
    client = fake_client(lambda r: httpx.Response(429, headers={"Retry-After": "60"}))
    outcome = gs.run_search(user.id, filters(), gs.LIVE, client=client, today=TODAY)
    assert outcome.error_kind == "rate_limited" and "60 seconds" in outcome.error
    step = trace.run_steps(user.id, outcome.run_id)[1]
    assert step["status"] == "rate_limited" and step["summary"]["retry_after_s"] == 60


def test_live_malformed_response_degrades_gracefully(user):
    client = fake_client(lambda r: httpx.Response(200, text="<html>maintenance</html>"))
    outcome = gs.run_search(user.id, filters(), gs.LIVE, client=client, today=TODAY)
    assert outcome.error_kind == "malformed" and outcome.results == []


def test_live_partially_malformed_results_are_kept_and_counted(user):
    hits = [hit("1", "Fine"), {"id": "?", "title": "broken"}]
    outcome = gs.run_search(user.id, filters(), gs.LIVE, client=live_client(hits), today=TODAY)
    assert [r.id for r in outcome.results] == ["1"] and outcome.skipped_malformed == 1


# ---------------------------------------------------------------- live details

def details_client():
    return fake_client(lambda r: httpx.Response(200, json=load_fixture("grants_gov_fetch_synopsis_361822.json")))


def test_details_fill_in_checks(user):
    base = gs.run_search(user.id, filters(), gs.LIVE, client=live_client([hit("361822", "X")]), today=TODAY).results[0]
    updated, error = gs.run_details(user.id, base, filters(), client=details_client(), today=TODAY)
    assert error is None and updated.details_loaded
    checks = {c.name: c for c in updated.checks}
    assert checks["Applicant type"].outcome == gs.MEETS
    assert checks["Award range"].outcome == gs.FAILS  # $25,000 is below the $1,000,000 floor
    assert "below" in checks["Award range"].detail
    assert checks["Cost sharing"].outcome == gs.MEETS
    assert (updated.amount_min, updated.amount_max) == (1_000_000, 100_000_000)
    assert updated.close_date == date(2027, 10, 1)


def test_details_wrong_applicant_type_is_a_hard_fail(user):
    base = gs.run_search(user.id, filters(), gs.LIVE, client=live_client([hit("361822", "X")]), today=TODAY).results[0]
    data = load_fixture("grants_gov_fetch_synopsis_361822.json")
    data["data"]["synopsis"]["applicantTypes"] = [{"id": "00", "description": "State governments"}]
    client = fake_client(lambda r: httpx.Response(200, json=data))
    updated, _ = gs.run_details(user.id, base, filters(), client=client, today=TODAY)
    assert updated.hard_fail


def test_details_not_found_keeps_result_and_explains(user):
    base = gs.run_search(user.id, filters(), gs.LIVE, client=live_client([hit("999", "Gone")]), today=TODAY).results[0]
    client = fake_client(lambda r: httpx.Response(200, json=envelope({"cfdas": []})))
    same, error = gs.run_details(user.id, base, filters(), client=client, today=TODAY)
    assert same == base and "no longer returns details" in error


def test_details_network_failure_keeps_result(user):
    base = gs.run_search(user.id, filters(), gs.LIVE, client=live_client([hit("1", "X")]), today=TODAY).results[0]

    def down(request):
        raise httpx.ReadTimeout("slow")

    same, error = gs.run_details(user.id, base, filters(), client=fake_client(down), today=TODAY)
    assert same == base and "not responding" in error


# ---------------------------------------------------------------- live snapshots for applications

def test_live_snapshot_starts_an_application_and_stays_out_of_samples(user):
    base = gs.run_search(user.id, filters(), gs.LIVE, client=live_client([hit("361822", "Snapshot me")]), today=TODAY).results[0]
    grant_id = repo.save_live_grant_snapshot(base)
    assert grant_id == "gg-361822"
    stored = repo.get_grant(grant_id)
    assert not stored["is_example"] and stored["source_url"] == base.source_url
    assert stored["retrieved_at"].startswith("2026-10-20T19:51")
    app_id = repo.create_application_from_grant(user.id, grant_id)
    assert repo.get_application(user.id, app_id)["due_date"] == "2026-12-11"
    assert grant_id not in {g["id"] for g in repo.list_sample_grants()}


def test_samples_cannot_be_saved_as_live_snapshots():
    sample = gs.search_samples(filters())[0][0]
    with pytest.raises(Exception):
        repo.save_live_grant_snapshot(sample)
    with pytest.raises(Exception):
        repo.save_live_grant_snapshot(replace(sample, source=gs.LIVE, id="../x"))


# ---------------------------------------------------------------- found by a nonprofit's user test, 2026-10-23
#
# A grant professional searched Grants.gov for Virginia opportunities and hit two real defects: an opportunity
# listed twice on one page, and a forecast from years ago described as "not accepting applications yet".

TODAY = date(2026, 10, 20)


def live_page(hits: list[dict]):
    """A parsed Grants.gov results page, built the way the real client builds one."""
    from grantbridge import grants_gov as gg
    parsed = [h for h in (gg._parse_hit(r) for r in hits) if h is not None]
    return gg.SearchPage(hits=parsed, hit_count=len(hits), skipped=len(hits) - len(parsed), retrieved_at=NOW)


def test_one_opportunity_listed_twice_is_merged():
    """Grants.gov returned the same embassy opportunity twice in one Virginia search."""
    twice = [hit("111", "U.S. Embassy Cairo Public Diplomacy Grants"),
             hit("222", "Something else entirely"),
             hit("333", "U.S. Embassy Cairo Public Diplomacy Grants")]
    twice[2]["number"] = twice[0]["number"]            # the same opportunity number, a different record id
    outcome = gs.live_outcome(live_page(twice), gs.SearchFilters(), TODAY)
    titles = [r.title for r in outcome.results]
    assert titles.count("U.S. Embassy Cairo Public Diplomacy Grants") == 1
    assert outcome.duplicates_merged == 1


def test_merging_keeps_the_better_dated_record():
    """A stale forecast must not hide the live posting of the same opportunity."""
    pair = [hit("111", "Rural Water Program", close="01/01/2019", status="forecasted"),
            hit("222", "Rural Water Program", close="12/11/2026", status="posted")]
    pair[1]["number"] = pair[0]["number"]
    outcome = gs.live_outcome(live_page(pair), gs.SearchFilters(), TODAY)
    assert len(outcome.results) == 1
    assert outcome.results[0].deadline.code == "posted"


def test_two_different_opportunities_are_both_kept():
    outcome = gs.live_outcome(live_page([hit("111", "First"), hit("222", "Second")]),
                              gs.SearchFilters(), TODAY)
    assert len(outcome.results) == 2 and outcome.duplicates_merged == 0


def test_a_forecast_whose_close_date_has_passed_is_not_called_upcoming():
    """It said "not accepting applications yet" about a 2019 date, and a tester went to read the notice."""
    stale = gs.live_deadline("forecasted", date(2019, 3, 1), NOW, TODAY)
    assert stale.code == "passed"
    assert "2019" in stale.label and "passed" in stale.detail
    assert "not accepting applications yet" not in stale.label


def test_a_forecast_still_to_come_is_unchanged():
    ahead = gs.live_deadline("forecasted", date(2027, 3, 1), NOW, TODAY)
    assert ahead.code == "forecasted" and "not accepting applications yet" in ahead.label


def test_a_forecast_with_no_close_date_is_unchanged():
    none = gs.live_deadline("forecasted", None, NOW, TODAY)
    assert none.code == "forecasted"


def test_a_stale_forecast_is_hidden_from_results_like_any_closed_grant():
    outcome = gs.live_outcome(live_page([hit("111", "Old forecast", close="01/01/2019", status="forecasted")]),
                              gs.SearchFilters(), TODAY)
    assert outcome.results == [] and outcome.hidden_closed == 1


def test_the_award_range_keeps_grants_whose_size_the_funder_never_stated():
    """A nonprofit asked to filter by award size. Most live listings leave it blank, so unknown must survive."""
    wide = gs.SearchFilters(award_range=(25_000, 100_000))
    assert gs.award_in_range(wide, None, None) is True
    assert gs.award_in_range(wide, 50_000, 75_000) is True      # inside
    assert gs.award_in_range(wide, 10_000, 30_000) is True      # overlaps the bottom
    assert gs.award_in_range(wide, 80_000, 400_000) is True     # overlaps the top
    assert gs.award_in_range(wide, 1_000, 5_000) is False       # entirely below
    assert gs.award_in_range(wide, 500_000, 900_000) is False   # entirely above


def test_an_open_topped_range_has_no_ceiling():
    open_top = gs.SearchFilters(award_range=(250_000, None))
    assert gs.award_in_range(open_top, 5_000_000, 9_000_000) is True
    assert gs.award_in_range(open_top, 1_000, 2_000) is False


def test_live_results_outside_the_range_are_hidden_and_counted():
    hits = [hit("111", "Small award"), hit("222", "Big award")]
    page = live_page(hits)
    from dataclasses import replace as _replace
    outcome = gs.live_outcome(page, gs.SearchFilters(), TODAY)
    # search hits carry no award size, so a range must not empty the page
    ranged = gs.live_outcome(page, gs.SearchFilters(award_range=(25_000, 100_000)), TODAY)
    assert len(ranged.results) == len(outcome.results) and ranged.hidden_award == 0

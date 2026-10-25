"""Grants.gov client: request shape, parsing real responses, failures, rate limits, and caching."""

import json
from datetime import date

import httpx
import pytest

from grantbridge import grants_gov as gg
from tests.conftest import NOW, envelope, fake_client, hit, load_fixture, search_data


def json_reply(payload, status=200, headers=None):
    return lambda request: httpx.Response(status, json=payload, headers=headers)


class Recorder:
    """Transport handler that replays responses in order and records each request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        nxt = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


# ---------------------------------------------------------------- request shape

def test_search_body_matches_documented_parameters():
    rec = Recorder(httpx.Response(200, json=envelope(search_data([]))))
    client = fake_client(rec)
    client.search(gg.SearchParams(keyword=" after\x00school ", categories=("ED", "ISS"),
                                  eligibilities=("12",), rows=500))
    sent = rec.requests[0]
    assert sent.method == "POST"
    assert str(sent.url) == "https://api.grants.gov/v1/api/search2"
    body = json.loads(sent.content)
    assert body == {"keyword": "afterschool", "oppStatuses": "forecasted|posted", "rows": gg.MAX_ROWS,
                    "startRecordNum": 0, "fundingCategories": "ED|ISS", "eligibilities": "12"}


def test_fetch_rejects_non_numeric_ids_without_a_request():
    rec = Recorder(httpx.Response(200, json=envelope({})))
    with pytest.raises(ValueError):
        fake_client(rec).fetch("../admin")
    assert rec.requests == []


# ---------------------------------------------------------------- parsing real captured responses

def test_parses_real_search2_response():
    page = fake_client(json_reply(load_fixture("grants_gov_search2_tutoring.json"))).search(gg.SearchParams("tutoring"))
    assert page.hit_count == 1 and page.skipped == 0 and not page.from_cache
    h = page.hits[0]
    assert h.id == "361822"
    assert h.title == "Home Study and Post-Release Services for Unaccompanied Alien Children"  # &#8203; removed
    assert h.agency == "Administration for Children and Families - ORR"
    assert h.close_date == date(2027, 10, 1) and h.status == "posted"
    assert page.retrieved_at == NOW


def test_accepts_documented_field_names_too():
    raw = hit("100", "Documented Shape")
    raw["agencyName"] = raw.pop("agency")
    page = fake_client(json_reply(envelope(search_data([raw])))).search(gg.SearchParams())
    assert page.hits[0].agency == "Test Agency"


def test_parses_real_fetch_opportunity_synopsis():
    d = fake_client(json_reply(load_fixture("grants_gov_fetch_synopsis_361822.json"))).fetch("361822")
    assert d.id == "361822" and d.doc_type == "synopsis"
    assert d.award_floor == 1_000_000 and d.award_ceiling == 100_000_000
    assert d.close_date == date(2027, 10, 1)
    assert ("12", "Nonprofits having a 501(c)(3) status with the IRS, other than institutions of higher education") in d.applicant_types
    assert d.cost_sharing is False
    assert "&quot;" not in d.eligibility_text and "<" not in d.description


def test_parses_real_fetch_opportunity_forecast():
    d = fake_client(json_reply(load_fixture("grants_gov_fetch_forecast_355824.json"))).fetch("355824")
    assert d.doc_type == "forecast"
    assert d.award_floor == 450_000 and d.award_ceiling == 600_000


def test_unknown_opportunity_returns_none():
    # Grants.gov answers 200 with an empty data object for ids it does not know.
    empty = envelope({"revision": 0, "cfdas": [], "errorMessages": []})
    assert fake_client(json_reply(empty)).fetch("1") is None


def test_details_never_carry_contact_information():
    fields = gg.Details.__dataclass_fields__
    assert not any("contact" in name.lower() or "email" in name.lower() or "phone" in name.lower() for name in fields)


# ---------------------------------------------------------------- no results

def test_no_results_is_an_empty_page_not_an_error():
    page = fake_client(json_reply(envelope(search_data([])))).search(gg.SearchParams("zzzz"))
    assert page.hits == [] and page.hit_count == 0


# ---------------------------------------------------------------- bad network and server errors

@pytest.mark.parametrize("error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("bad")])
def test_network_failures_retry_then_raise_unavailable(error):
    rec = Recorder(error)
    with pytest.raises(gg.GrantsGovUnavailable) as caught:
        fake_client(rec).search(gg.SearchParams())
    assert len(rec.requests) == gg.MAX_ATTEMPTS
    assert "No live results are shown" in caught.value.user_message


def test_server_error_then_success_recovers():
    rec = Recorder(httpx.Response(503), httpx.Response(200, json=envelope(search_data([hit("1", "Recovered")]))))
    page = fake_client(rec).search(gg.SearchParams())
    assert page.hits[0].title == "Recovered" and len(rec.requests) == 2


def test_backoff_is_exponential():
    waits = []
    client = gg.GrantsGovClient(transport=httpx.MockTransport(Recorder(httpx.Response(500))),
                                min_interval=0, sleep=waits.append)
    with pytest.raises(gg.GrantsGovUnavailable):
        client.search(gg.SearchParams())
    assert waits == [gg.BASE_BACKOFF, gg.BASE_BACKOFF * 2]


def test_client_errors_are_not_retried():
    rec = Recorder(httpx.Response(400, text="Bad Request"))
    with pytest.raises(gg.GrantsGovBadResponse):
        fake_client(rec).search(gg.SearchParams())
    assert len(rec.requests) == 1


# ---------------------------------------------------------------- rate limits

class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_429_honors_retry_after_and_blocks_further_requests():
    clock = FakeClock()
    rec = Recorder(httpx.Response(429, headers={"Retry-After": "45"}))
    client = fake_client(rec, clock=clock)
    with pytest.raises(gg.GrantsGovRateLimited) as first:
        client.search(gg.SearchParams())
    assert first.value.retry_after == 45
    clock.t += 10
    with pytest.raises(gg.GrantsGovRateLimited) as second:
        client.search(gg.SearchParams("other"))  # different query, still blocked
    assert second.value.retry_after == 35
    assert len(rec.requests) == 1  # the cooldown sent nothing


def test_repeated_429s_double_the_cooldown():
    clock = FakeClock()
    client = fake_client(Recorder(httpx.Response(429)), clock=clock)
    with pytest.raises(gg.GrantsGovRateLimited) as a:
        client.search(gg.SearchParams())
    clock.t += a.value.retry_after + 1
    with pytest.raises(gg.GrantsGovRateLimited) as b:
        client.search(gg.SearchParams())
    assert (a.value.retry_after, b.value.retry_after) == (gg.COOLDOWN_START, gg.COOLDOWN_START * 2)


def test_requests_are_spaced_by_the_minimum_interval():
    clock, waits = FakeClock(), []
    rec = Recorder(httpx.Response(200, json=envelope(search_data([]))))
    client = gg.GrantsGovClient(transport=httpx.MockTransport(rec), min_interval=1.0,
                                sleep=waits.append, clock=clock)
    client.search(gg.SearchParams("a"))
    client.search(gg.SearchParams("b"))
    assert waits == [pytest.approx(1.0)]


# ---------------------------------------------------------------- malformed responses

@pytest.mark.parametrize("response", [
    httpx.Response(200, text="<html>Service Unavailable</html>"),
    httpx.Response(200, json=["not", "an", "object"]),
    httpx.Response(200, json={"errorcode": 1, "msg": "failed", "data": {}}),
    httpx.Response(200, json={"errorcode": 0, "msg": "ok"}),
    httpx.Response(200, json=envelope({"hitCount": 3, "oppHits": "three"})),
    httpx.Response(200, json=envelope(search_data([{"id": None}, {"title": "no id"}, "junk"]))),
], ids=["html", "json-list", "errorcode", "no-data", "hits-not-list", "all-hits-bad"])
def test_malformed_search_responses_raise_bad_response(response):
    with pytest.raises(gg.GrantsGovBadResponse):
        fake_client(lambda r: response).search(gg.SearchParams())


def test_partially_malformed_hits_are_skipped_and_counted():
    hits = [hit("1", "Good one"), {"id": "x", "title": "bad id"}, hit("2", ""), hit("3", "Bad date", close="13/45/2026")]
    page = fake_client(json_reply(envelope(search_data(hits)))).search(gg.SearchParams())
    assert [h.id for h in page.hits] == ["1", "3"]
    assert page.skipped == 2
    assert page.hits[1].close_date is None  # unparseable date becomes unknown, never guessed


# ---------------------------------------------------------------- caching

def test_identical_searches_are_cached_with_original_timestamp():
    rec = Recorder(httpx.Response(200, json=envelope(search_data([hit("1", "Cached")]))))
    client = fake_client(rec)
    first = client.search(gg.SearchParams("literacy"))
    second = client.search(gg.SearchParams("literacy"))
    assert len(rec.requests) == 1
    assert second.from_cache and not first.from_cache
    assert second.retrieved_at == first.retrieved_at


def test_cache_expires():
    clock = FakeClock()
    rec = Recorder(httpx.Response(200, json=envelope(search_data([]))))
    client = fake_client(rec, clock=clock)
    client.search(gg.SearchParams("x"))
    clock.t += gg.SEARCH_CACHE_TTL + 1
    client.search(gg.SearchParams("x"))
    assert len(rec.requests) == 2


def test_clean_text_handles_entities_tags_and_zero_width():
    assert gg.clean_text("A&amp;B <b>bold</b>&#8203; &quot;q&quot;​  end") == 'A&B bold "q" end'
    assert gg.clean_text(None) == ""
    assert len(gg.clean_text("x" * 5000, 100)) == 100

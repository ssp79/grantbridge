"""Client for the public Grants.gov API (search2 and fetchOpportunity).

Verified on 2026-10-20 against the official documentation and live responses:
  - API guide (base URL, no authentication for these two endpoints):
      https://grants.gov/api/api-guide
  - search2 reference:          https://grants.gov/api/common/search2
  - fetchOpportunity reference: https://grants.gov/api/common/fetchopportunity
  - Status codes (429 = too many requests, use exponential backoff):
      https://www.grants.gov/api/status-codes
  - Terms: https://grants.gov/api/terms-conditions
      Permitted: "search, display, analyze, retrieve, view and otherwise 'get'
      information from grants data". Apps must show ATTRIBUTION (below), must not
      modify or falsely represent content, and may be limited or blocked if they
      exceed usage limits. No numeric limit is published.

Live responses differ slightly from the documented examples (hits use `agency`
and `cfdaList`, the docs show `agencyName` and `alnist`), so parsing accepts
both. An unknown opportunity id returns HTTP 200 with empty data, and a bad
search body returns HTTP 200 with zero hits; both are handled below.

Politeness rules: one request per MIN_INTERVAL seconds from this process,
identical requests are served from a short cache, and after a 429 no request is
sent until a cooldown ends (doubling on repeated 429s).
"""

from __future__ import annotations

import html
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone

import httpx

API_BASE = "https://api.grants.gov/v1/api"
DETAIL_URL = "https://www.grants.gov/search-results-detail/{id}"
ATTRIBUTION = (
    "This product uses the Grants.gov API but is not endorsed or certified by the "
    "U.S. Department of Health and Human Services."
)

TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_ROWS = 200  # rows=200 verified live on 2026-10-20 (returned all 115 Education matches)
MIN_INTERVAL = 1.0  # seconds between requests from this process
SEARCH_CACHE_TTL = 15 * 60
DETAIL_CACHE_TTL = 60 * 60
MAX_ATTEMPTS = 3  # first try plus two retries, for timeouts, network errors, and 5xx
BASE_BACKOFF = 0.5
COOLDOWN_START = 30
COOLDOWN_MAX = 300
MAX_TEXT_CHARS = 2000

_ZERO_WIDTH = re.compile(r"[​-‏ - ⁠﻿]")
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


# ---------------------------------------------------------------- errors

class GrantsGovError(Exception):
    """Base class. `user_message` is safe to show; `kind` is safe to log."""

    kind = "error"
    user_message = "Grants.gov could not be reached. No live results are shown."


class GrantsGovUnavailable(GrantsGovError):
    kind = "unavailable"
    user_message = (
        "Grants.gov is not responding right now (network error, timeout, or server error). "
        "No live results are shown. Try again later, or switch to Sample grants."
    )


class GrantsGovRateLimited(GrantsGovError):
    kind = "rate_limited"

    def __init__(self, retry_after: int):
        super().__init__(f"rate limited for {retry_after}s")
        self.retry_after = retry_after
        self.user_message = (
            f"Grants.gov asked us to slow down. Live search is paused for about {retry_after} "
            "seconds. No live results are shown; switch to Sample grants meanwhile."
        )


class GrantsGovBadResponse(GrantsGovError):
    kind = "malformed"
    user_message = (
        "Grants.gov sent a response GrantBridge could not read, so no live results are shown. "
        "Try again later, or switch to Sample grants."
    )


# ---------------------------------------------------------------- data

@dataclass(frozen=True)
class SearchParams:
    keyword: str = ""
    categories: tuple[str, ...] = ()
    eligibilities: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ("forecasted", "posted")
    rows: int = MAX_ROWS

    def body(self) -> dict:
        body = {
            "keyword": clean_keyword(self.keyword),
            "oppStatuses": "|".join(self.statuses),
            "rows": max(1, min(int(self.rows), MAX_ROWS)),
            "startRecordNum": 0,
        }
        if self.categories:
            body["fundingCategories"] = "|".join(self.categories)
        if self.eligibilities:
            body["eligibilities"] = "|".join(self.eligibilities)
        return body


@dataclass(frozen=True)
class Hit:
    id: str
    number: str
    title: str
    agency: str
    open_date: date | None
    close_date: date | None
    status: str  # as reported: posted, forecasted, closed, archived
    doc_type: str


@dataclass(frozen=True)
class SearchPage:
    hits: list[Hit]
    hit_count: int
    skipped: int  # hits dropped because they were malformed
    retrieved_at: datetime
    from_cache: bool = False


@dataclass(frozen=True)
class Details:
    id: str
    number: str
    title: str
    agency: str
    doc_type: str  # synopsis or forecast
    description: str
    eligibility_text: str
    applicant_types: tuple[tuple[str, str], ...]  # (code, label)
    categories: tuple[str, ...]
    award_floor: int | None
    award_ceiling: int | None
    cost_sharing: bool | None
    close_date: date | None
    retrieved_at: datetime
    from_cache: bool = False


# ---------------------------------------------------------------- helpers

def clean_text(value, limit: int = MAX_TEXT_CHARS) -> str:
    """Unescape HTML entities, drop tags and zero-width characters, collapse spaces."""
    if not isinstance(value, str):
        return ""
    text = html.unescape(html.unescape(value))
    text = _TAGS.sub(" ", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _SPACES.sub(" ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def clean_keyword(value: str) -> str:
    text = "".join(ch for ch in (value or "") if ch.isprintable())
    return _SPACES.sub(" ", text).strip()[:100]


def detail_url(opportunity_id: str) -> str:
    return DETAIL_URL.format(id=opportunity_id)


def _parse_mdy(value) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def _parse_str_date(value) -> date | None:
    """fetchOpportunity '...Str' dates look like 2027-10-01-00-00-00."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_long_date(value) -> date | None:
    """fetchOpportunity dates also appear as 'Oct 01, 2027 12:00:00 AM EDT'."""
    if not isinstance(value, str) or len(value) < 12:
        return None
    try:
        return datetime.strptime(value[:12], "%b %d, %Y").date()
    except ValueError:
        return None


def _to_int(value) -> int | None:
    if value in (None, "", "none", "None"):
        return None
    try:
        number = int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _code_list(items) -> tuple[tuple[str, str], ...]:
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("id"):
            out.append((str(item["id"]), clean_text(item.get("description", ""), 200)))
    return tuple(out)


def _parse_hit(raw) -> Hit | None:
    if not isinstance(raw, dict):
        return None
    opp_id = str(raw.get("id") or "").strip()
    title = clean_text(raw.get("title"), 300)
    if not opp_id.isdigit() or not title:
        return None
    return Hit(
        id=opp_id,
        number=clean_text(raw.get("number"), 80),
        title=title,
        agency=clean_text(raw.get("agency") or raw.get("agencyName"), 200),
        open_date=_parse_mdy(raw.get("openDate")),
        close_date=_parse_mdy(raw.get("closeDate")),
        status=clean_text(raw.get("oppStatus"), 20).lower(),
        doc_type=clean_text(raw.get("docType"), 20).lower(),
    )


def _envelope(response: httpx.Response) -> dict:
    """Validate the common {errorcode, msg, data} wrapper and return `data`."""
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise GrantsGovBadResponse("response was not JSON") from None
    if not isinstance(body, dict):
        raise GrantsGovBadResponse("response was not a JSON object")
    if body.get("errorcode") not in (0, "0"):
        raise GrantsGovBadResponse(f"errorcode {body.get('errorcode')!r}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise GrantsGovBadResponse("missing data object")
    return data


def parse_search(response: httpx.Response, retrieved_at: datetime) -> SearchPage:
    data = _envelope(response)
    raw_hits = data.get("oppHits", [])
    if not isinstance(raw_hits, list):
        raise GrantsGovBadResponse("oppHits was not a list")
    hits = [h for h in (_parse_hit(r) for r in raw_hits) if h is not None]
    skipped = len(raw_hits) - len(hits)
    if raw_hits and not hits:
        raise GrantsGovBadResponse("every hit was malformed")
    hit_count = _to_int(data.get("hitCount"))
    if hit_count is None:
        hit_count = len(hits)
    return SearchPage(hits=hits, hit_count=max(hit_count, len(hits)), skipped=skipped, retrieved_at=retrieved_at)


def parse_details(response: httpx.Response, retrieved_at: datetime) -> Details | None:
    """Return None when Grants.gov has no such opportunity (it answers 200 with empty data)."""
    data = _envelope(response)
    opp_id = str(data.get("id") or "").strip()
    title = clean_text(data.get("opportunityTitle"), 300)
    if not opp_id or not title:
        return None
    doc_type = clean_text(data.get("docType"), 20).lower()
    block = data.get("synopsis") if isinstance(data.get("synopsis"), dict) else None
    if block is None and isinstance(data.get("forecast"), dict):
        block = data["forecast"]
    block = block or {}
    if doc_type == "forecast":
        close = _parse_str_date(block.get("estApplicationResponseDateStr")) or _parse_long_date(
            block.get("estApplicationResponseDate")
        )
        description = block.get("forecastDesc")
    else:
        close = _parse_str_date(block.get("responseDateStr")) or _parse_long_date(block.get("responseDate"))
        description = block.get("synopsisDesc")
    agency = block.get("agencyName") or (data.get("agencyDetails") or {}).get("agencyName", "")
    cost_sharing = block.get("costSharing")
    return Details(
        id=opp_id,
        number=clean_text(data.get("opportunityNumber"), 80),
        title=title,
        agency=clean_text(agency, 200),
        doc_type=doc_type or "synopsis",
        description=clean_text(description),
        eligibility_text=clean_text(block.get("applicantEligibilityDesc")),
        applicant_types=_code_list(block.get("applicantTypes")),
        categories=tuple(code for code, _ in _code_list(block.get("fundingActivityCategories"))),
        award_floor=_to_int(block.get("awardFloor")),
        award_ceiling=_to_int(block.get("awardCeiling")),
        cost_sharing=cost_sharing if isinstance(cost_sharing, bool) else None,
        close_date=close,
        retrieved_at=retrieved_at,
    )


# ---------------------------------------------------------------- client

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@dataclass
class GrantsGovClient:
    """Thread-safe client. Inject `transport` (e.g. httpx.MockTransport) in tests."""

    transport: httpx.BaseTransport | None = None
    min_interval: float = MIN_INTERVAL
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    now: Callable[[], datetime] = _utcnow
    requests_sent: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_request: float = field(default=-1e9, repr=False)
    _cooldown_until: float = field(default=-1e9, repr=False)
    _cooldown: int = field(default=COOLDOWN_START, repr=False)
    _cache: dict = field(default_factory=dict, repr=False)

    def search(self, params: SearchParams) -> SearchPage:
        body = params.body()
        key = ("search", json.dumps(body, sort_keys=True))
        cached = self._cached(key, SEARCH_CACHE_TTL)
        if cached is not None:
            return replace(cached, from_cache=True)
        response = self._post("/search2", body)
        page = parse_search(response, self.now())
        self._store(key, page)
        return page

    def fetch(self, opportunity_id: str) -> Details | None:
        if not str(opportunity_id).isdigit():
            raise ValueError("opportunity id must be numeric")
        key = ("fetch", str(opportunity_id))
        cached = self._cached(key, DETAIL_CACHE_TTL)
        if cached is not None:
            return replace(cached, from_cache=True)
        response = self._post("/fetchOpportunity", {"opportunityId": int(opportunity_id)})
        details = parse_details(response, self.now())
        if details is not None:
            self._store(key, details)
        return details

    def cooldown_remaining(self) -> int:
        return max(0, int(self._cooldown_until - self.clock() + 0.999))

    # -- internals

    def _cached(self, key, ttl: int):
        entry = self._cache.get(key)
        if entry and self.clock() - entry[0] < ttl:
            return entry[1]
        return None

    def _store(self, key, value) -> None:
        if len(self._cache) > 500:
            self._cache.clear()
        self._cache[key] = (self.clock(), value)

    def _post(self, path: str, body: dict) -> httpx.Response:
        remaining = self.cooldown_remaining()
        if remaining:
            raise GrantsGovRateLimited(remaining)
        last_error: GrantsGovError = GrantsGovUnavailable("no attempt made")
        with httpx.Client(base_url=API_BASE, timeout=TIMEOUT, transport=self.transport) as http:
            for attempt in range(MAX_ATTEMPTS):
                if attempt:
                    self.sleep(BASE_BACKOFF * 2 ** (attempt - 1))
                self._wait_turn()
                try:
                    response = http.post(path, json=body, headers={"Accept": "application/json"})
                except (httpx.TimeoutException, httpx.TransportError):
                    last_error = GrantsGovUnavailable("network error or timeout")
                    continue
                if response.status_code == 429:
                    raise self._start_cooldown(response)
                if response.status_code >= 500:
                    last_error = GrantsGovUnavailable(f"HTTP {response.status_code}")
                    continue
                if response.status_code != 200:
                    raise GrantsGovBadResponse(f"HTTP {response.status_code}")
                self._cooldown = COOLDOWN_START
                return response
        raise last_error

    def _wait_turn(self) -> None:
        with self._lock:
            wait = self._last_request + self.min_interval - self.clock()
            if wait > 0:
                self.sleep(wait)
            self._last_request = self.clock()
            self.requests_sent += 1

    def _start_cooldown(self, response: httpx.Response) -> GrantsGovRateLimited:
        retry_after = _to_int(response.headers.get("Retry-After"))
        seconds = min(COOLDOWN_MAX, max(retry_after or 0, self._cooldown))
        self._cooldown = min(COOLDOWN_MAX, self._cooldown * 2)
        self._cooldown_until = self.clock() + seconds
        return GrantsGovRateLimited(seconds)


_default_client: GrantsGovClient | None = None
_default_lock = threading.Lock()


def default_client() -> GrantsGovClient:
    """One shared client per process, so throttling and cooldowns apply to all users."""
    global _default_client
    with _default_lock:
        if _default_client is None:
            _default_client = GrantsGovClient()
        return _default_client

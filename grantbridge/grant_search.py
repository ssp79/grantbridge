"""Grant search over the offline sample fixtures or live Grants.gov.

Everything in this module is deterministic code: building the query from the
profile, filtering, the fit checks, deadline status, and sorting. AI is used
only afterwards (fit_explainer.py) to explain a result in plain words.

Wording rule: nothing here ever calls a grant "open". A live result reports
Grants.gov's own status as of the retrieval time and links to the source page.
A sample result is always labeled SAMPLE / NOT LIVE and has no real deadline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone

from grantbridge import grants_gov as gg
from grantbridge import repo, trace
from grantbridge.db import SAMPLE_LABEL

SAMPLE = "sample"
LIVE = "grants.gov"

MEETS, FAILS, UNKNOWN = "meets", "fails", "unknown"

# Grants.gov funding-category codes, as listed in live search2 responses on 2026-10-20.
FOCUS_TO_CATEGORIES = {
    "Arts & culture": ("AR", "HU"),
    "Education": ("ED",),
    "Environment": ("ENV", "NR"),
    "Food security": ("FN",),
    "Health": ("HL",),
    "Housing": ("HO",),
    "Workforce development": ("ELT",),
    "Youth": (),  # Grants.gov has no youth category
    "Seniors": ("ISS",),
    "Immigrant services": ("ISS",),
    "Disability services": ("ISS",),
    "Community development": ("CD",),
}
# Grants.gov applicant-type codes: 12 = "Nonprofits having a 501(c)(3) status with the IRS,
# other than institutions of higher education"; 13 = nonprofits without 501(c)(3); 25 = Others.
TAX_TO_ELIGIBILITY = {
    "Yes, IRS-recognized 501(c)(3)": "12",
    "Fiscally sponsored by a 501(c)(3)": "12",
    "No": "13",
}
CLOSING_SOON_DAYS = 14
PLACEHOLDER_YEAR = 2090  # Grants.gov shows dates like 01/01/2099 when there is no real close date

_RESEARCH = re.compile(
    r"\((?:R|K|U|P|F|T)\d{2}\b|\bclinical trials?\b|\bresearch (?:project|program|center)s?\b", re.IGNORECASE
)
_RESEARCH_NUMBER = re.compile(r"^(?:PAR|RFA|PA|NOT|OTA)-", re.IGNORECASE)
_BUDGET_UNDER = re.compile(r"budget (?:under|below|less than) \$([\d,]+)", re.IGNORECASE)
_BUDGET_BETWEEN = re.compile(r"budget between \$([\d,]+) and \$([\d,]+)", re.IGNORECASE)
_BUDGET_SHARE = re.compile(r"may not exceed (\d+)% of the organization's annual budget", re.IGNORECASE)
_STAFF_UNDER = re.compile(r"fewer than (\d+) full-time staff", re.IGNORECASE)


# ---------------------------------------------------------------- data

@dataclass(frozen=True)
class SearchFilters:
    keyword: str = ""
    focus_areas: tuple[str, ...] = ()
    min_award: int | None = None
    award_range: tuple[int, int | None] | None = None  # (low, high); high None means "and above"
    hide_failing: bool = False
    hide_research: bool = False  # live only: drop NIH-style research grants
    # Taken from the profile and used by the checks:
    state: str = ""
    tax_status: str = ""
    requested_amount: int | None = None
    annual_budget: int | None = None
    staff_size: int | None = None

    def live_params(self) -> gg.SearchParams:
        eligibility = TAX_TO_ELIGIBILITY.get(self.tax_status)
        return gg.SearchParams(
            keyword=self.keyword,
            categories=tuple(categories_for(self.focus_areas)),
            eligibilities=(eligibility,) if eligibility else (),
        )

    def safe_summary(self, source: str) -> dict:
        summary = {
            "source": source,
            "state": self.state,
            "focus_areas": list(self.focus_areas),
            "has_keyword": bool(self.keyword.strip()),
            "keyword_chars": len(self.keyword.strip()),
            "min_award": self.min_award,
            "hide_failing": self.hide_failing,
            "hide_research": self.hide_research,
        }
        if source == LIVE:
            params = self.live_params()
            summary.update(
                categories=list(params.categories),
                eligibility_codes=list(params.eligibilities),
                statuses=list(params.statuses),
                rows=params.rows,
            )
        return summary


def categories_for(focus_areas) -> list[str]:
    """Grants.gov funding-category codes for the given focus areas, sorted."""
    return sorted({c for f in focus_areas for c in FOCUS_TO_CATEGORIES.get(f, ())})


def filters_from_profile(org: dict | None, **overrides) -> SearchFilters:
    org = org or {}
    base = SearchFilters(
        focus_areas=tuple(org.get("focus_areas") or ()),
        state=org.get("state") or "",
        tax_status=org.get("tax_status") or "",
        requested_amount=org.get("requested_amount"),
        annual_budget=org.get("annual_budget"),
        staff_size=org.get("staff_size"),
    )
    return replace(base, **overrides)


@dataclass(frozen=True)
class Check:
    name: str
    outcome: str  # MEETS, FAILS, or UNKNOWN
    detail: str
    hard: bool = False  # a hard failure means the organization is very likely ineligible


@dataclass(frozen=True)
class DeadlineStatus:
    code: str  # sample, posted, closing_soon, no_close_date, forecasted, passed, unknown
    label: str  # short badge text
    detail: str  # full sentence naming the source and time
    tone: str  # badge style: example, ok, warn, no, info


@dataclass(frozen=True)
class GrantResult:
    source: str
    id: str
    number: str
    title: str
    funder: str
    summary: str
    amount_min: int | None
    amount_max: int | None
    close_date: date | None
    deadline: DeadlineStatus
    status_reported: str
    source_url: str
    retrieved_at: datetime | None
    eligibility: tuple[str, ...]
    checks: tuple[Check, ...]
    unknowns: tuple[str, ...]
    eligibility_text: str = ""
    details_loaded: bool = False
    research_like: bool = False
    deadline_raw: str = ""

    @property
    def is_live(self) -> bool:
        return self.source == LIVE

    @property
    def hard_fail(self) -> bool:
        return any(c.outcome == FAILS and c.hard for c in self.checks)

    def count(self, outcome: str) -> int:
        return sum(c.outcome == outcome for c in self.checks)


@dataclass
class SearchOutcome:
    source: str
    results: list[GrantResult]
    total_matches: int
    retrieved_at: datetime | None = None
    from_cache: bool = False
    skipped_malformed: int = 0
    hidden_closed: int = 0
    hidden_failing: int = 0
    hidden_research: int = 0
    duplicates_merged: int = 0
    hidden_award: int = 0
    error: str | None = None
    error_kind: str | None = None
    run_id: int | None = None


# ---------------------------------------------------------------- formatting

def fmt_date(d: date) -> str:
    return d.strftime("%b %d, %Y")


def fmt_time(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M UTC")


def _money(n: int) -> str:
    return f"${n:,}"


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------- checks shared by both sources

def _award_check(ask: int | None, lo: int | None, hi: int | None, live: bool) -> Check:
    if not ask:
        return Check("Award range", UNKNOWN, "Add your requested funding to your profile to compare it with the award range.")
    if lo is None and hi is None:
        where = "Grants.gov did not list award amounts." if live else "No award range listed."
        return Check("Award range", UNKNOWN, where)
    if lo is not None and ask < lo:
        return Check("Award range", FAILS, f"Your {_money(ask)} request is below the {_money(lo)} minimum award.")
    if hi is not None and ask > hi:
        return Check("Award range", FAILS, f"Your {_money(ask)} request is above the {_money(hi)} maximum award.")
    return Check("Award range", MEETS, f"Your {_money(ask)} request is within the award range.")


def _tax_check(criterion: str, tax_status: str) -> Check:
    text = criterion.lower()
    if tax_status == "Yes, IRS-recognized 501(c)(3)":
        return Check("501(c)(3) status", MEETS, "You reported IRS-recognized 501(c)(3) status (self-reported, not verified).")
    if tax_status == "Fiscally sponsored by a 501(c)(3)":
        if "fiscally sponsored" in text:
            return Check("501(c)(3) status", MEETS, "Fiscally sponsored projects are allowed (your status is self-reported).")
        return Check("501(c)(3) status", UNKNOWN, "Requires 501(c)(3) status. Ask whether your fiscal sponsor can apply for you.")
    if tax_status == "No":
        if " or " in text:
            return Check("501(c)(3) status", UNKNOWN, "Requires 501(c)(3) status unless you are another listed type.")
        return Check("501(c)(3) status", FAILS, "Requires 501(c)(3) status, and you reported you are not a 501(c)(3).", hard=True)
    if tax_status == "Application pending with the IRS":
        return Check("501(c)(3) status", UNKNOWN, "Requires 501(c)(3) status; your application is pending.")
    return Check("501(c)(3) status", UNKNOWN, "Requires 501(c)(3) status; your profile does not say yours.")


def _amount(text: str) -> int:
    return int(text.replace(",", ""))


def _budget_checks(criteria: list[str], f: SearchFilters) -> tuple[list[Check], set[int]]:
    checks, covered = [], set()
    for i, criterion in enumerate(criteria):
        if m := _BUDGET_BETWEEN.search(criterion):
            lo, hi = _amount(m.group(1)), _amount(m.group(2))
            covered.add(i)
            if f.annual_budget is None:
                checks.append(Check("Annual budget", UNKNOWN, f"Requires a budget between {_money(lo)} and {_money(hi)}; yours is not in your profile."))
            elif lo <= f.annual_budget <= hi:
                checks.append(Check("Annual budget", MEETS, f"Your {_money(f.annual_budget)} budget is between {_money(lo)} and {_money(hi)}."))
            else:
                checks.append(Check("Annual budget", FAILS, f"Requires a budget between {_money(lo)} and {_money(hi)}; yours is {_money(f.annual_budget)}.", hard=True))
        elif m := _BUDGET_UNDER.search(criterion):
            cap = _amount(m.group(1))
            covered.add(i)
            if f.annual_budget is None:
                checks.append(Check("Annual budget", UNKNOWN, f"Requires a budget under {_money(cap)}; yours is not in your profile."))
            elif f.annual_budget < cap:
                checks.append(Check("Annual budget", MEETS, f"Your {_money(f.annual_budget)} budget is under {_money(cap)}."))
            else:
                checks.append(Check("Annual budget", FAILS, f"Requires a budget under {_money(cap)}; yours is {_money(f.annual_budget)}.", hard=True))
        elif m := _BUDGET_SHARE.search(criterion):
            share = int(m.group(1))
            covered.add(i)
            if not f.annual_budget or not f.requested_amount:
                checks.append(Check("Request vs. budget", UNKNOWN, f"The request may not exceed {share}% of your budget; add both amounts to your profile."))
            else:
                limit = f.annual_budget * share // 100
                outcome = MEETS if f.requested_amount <= limit else FAILS
                verb = "is within" if outcome == MEETS else "exceeds"
                checks.append(Check("Request vs. budget", outcome, f"Your request {verb} {share}% of your budget ({_money(limit)})."))
        elif m := _STAFF_UNDER.search(criterion):
            cap = int(m.group(1))
            covered.add(i)
            if f.staff_size is None:
                checks.append(Check("Staff size", UNKNOWN, f"Requires fewer than {cap} full-time staff; yours is not in your profile."))
            elif f.staff_size < cap:
                checks.append(Check("Staff size", MEETS, f"Your {f.staff_size} staff is fewer than {cap}."))
            else:
                checks.append(Check("Staff size", FAILS, f"Requires fewer than {cap} full-time staff; you have {f.staff_size}.", hard=True))
    return checks, covered


# ---------------------------------------------------------------- sample fixtures

SAMPLE_DEADLINE_LABEL = "SAMPLE: no real deadline"


def sample_result(g: dict, f: SearchFilters) -> GrantResult:
    criteria = list(g["eligibility"])
    checks: list[Check] = []
    covered = {i for i, c in enumerate(criteria) if "located in" in c.lower()}

    if "ALL" in g["eligible_states"]:
        checks.append(Check("State", MEETS, "Open to organizations in every state."))
    elif not f.state:
        checks.append(Check("State", UNKNOWN, "Add your state to your profile to check location rules."))
    elif f.state in g["eligible_states"]:
        checks.append(Check("State", MEETS, f"Your state ({f.state}) is eligible."))
    else:
        allowed = ", ".join(g["eligible_states"])
        checks.append(Check("State", FAILS, f"Only organizations in {allowed} are eligible; yours is {f.state}.", hard=True))

    overlap = [a for a in g["focus_areas"] if a in f.focus_areas]
    if overlap:
        checks.append(Check("Focus area", MEETS, "Matches your focus: " + ", ".join(overlap) + "."))
    elif f.focus_areas:
        checks.append(Check("Focus area", FAILS, "None of your focus areas match this grant's."))
    else:
        checks.append(Check("Focus area", UNKNOWN, "Add focus areas to your profile to compare."))

    checks.append(_award_check(f.requested_amount, g.get("amount_min"), g.get("amount_max"), live=False))

    for i, criterion in enumerate(criteria):
        if "501(c)(3)" in criterion:
            checks.append(_tax_check(criterion, f.tax_status))
            covered.add(i)
            break

    budget_checks, budget_covered = _budget_checks(criteria, f)
    checks += budget_checks
    covered |= budget_covered

    unknowns = tuple(f"Not checked automatically: {c}" for i, c in enumerate(criteria) if i not in covered)
    example_date = "rolling" if g["deadline"] == "rolling" else g["deadline"]
    return GrantResult(
        source=SAMPLE,
        id=g["id"],
        number=g["id"],
        title=g["title"],
        funder=g["funder"],
        summary=g["summary"],
        amount_min=g.get("amount_min"),
        amount_max=g.get("amount_max"),
        close_date=None,
        deadline=DeadlineStatus(
            "sample", SAMPLE_DEADLINE_LABEL,
            f"{SAMPLE_LABEL}: this grant is invented for the demo and is not accepting applications. "
            f"Its example deadline ({example_date}) is not real.",
            "example",
        ),
        status_reported=SAMPLE_LABEL,
        source_url="",
        retrieved_at=None,
        eligibility=tuple(criteria),
        checks=tuple(checks),
        unknowns=unknowns,
        deadline_raw=g["deadline"],
    )


def filter_samples(f: SearchFilters, grants: list[dict] | None = None) -> tuple[list[GrantResult], int]:
    """Return (matching results, unranked; number hidden because they failed a hard check)."""
    grants = repo.list_sample_grants() if grants is None else grants
    tokens = f.keyword.lower().split()
    results, hidden = [], 0
    for g in grants:
        haystack = " ".join([g["title"], g["funder"], g["summary"], *g["eligibility"], *g["focus_areas"]]).lower()
        if tokens and not all(t in haystack for t in tokens):
            continue
        if f.focus_areas and not set(f.focus_areas) & set(g["focus_areas"]):
            continue
        if f.min_award and (g.get("amount_max") or 0) < f.min_award:
            continue
        if not award_in_range(f, g.get("amount_min"), g.get("amount_max")):
            continue
        result = sample_result(g, f)
        if f.hide_failing and result.hard_fail:
            hidden += 1
            continue
        results.append(result)
    return results, hidden


def search_samples(f: SearchFilters, grants: list[dict] | None = None) -> tuple[list[GrantResult], int]:
    """Filter and rank the sample fixtures."""
    results, hidden = filter_samples(f, grants)
    return rank(results), hidden


# ---------------------------------------------------------------- live Grants.gov

def award_in_range(f: SearchFilters, amount_min, amount_max) -> bool:
    """Whether a grant's award range overlaps the range the user asked for.

    A grant whose award size is unknown is kept. GrantBridge never turns "nobody told us" into "no", and
    Grants.gov leaves the award floor and ceiling empty on plenty of real listings — filtering them out would
    hide most of a live search.
    """
    if not f.award_range:
        return True
    low, high = f.award_range
    if amount_min is None and amount_max is None:
        return True
    ceiling = amount_max if amount_max is not None else amount_min
    floor = amount_min if amount_min is not None else amount_max
    if ceiling is not None and ceiling < low:
        return False
    if high is not None and floor is not None and floor > high:
        return False
    return True


def live_deadline(status: str, close: date | None, retrieved_at: datetime, today: date) -> DeadlineStatus:
    as_of = f"as reported by Grants.gov on {fmt_time(retrieved_at)}"
    confirm = "Confirm on the Grants.gov page before applying."
    if close and close.year >= PLACEHOLDER_YEAR:
        close = None  # placeholder date, not a real deadline
    if status == "forecasted":
        if close and close < today:
            # Grants.gov keeps old forecast records. Saying "not accepting applications yet" about a date
            # years in the past sent a real tester off to read a 2019 notice.
            return DeadlineStatus("passed", f"Forecast, estimated close date passed ({fmt_date(close)})",
                                  f"Listed as a forecast {as_of}, but its estimated close date "
                                  f"({fmt_date(close)}) has already passed, so this forecast is out of date. "
                                  f"{confirm}", "no")
        when = f" Estimated close date: {fmt_date(close)}." if close else ""
        return DeadlineStatus("forecasted", "Forecasted: not accepting applications yet",
                              f"Listed as a forecast {as_of}, so it is not accepting applications yet.{when} {confirm}", "info")
    if status == "posted":
        if close is None:
            return DeadlineStatus("no_close_date", "Posted on Grants.gov: no close date listed",
                                  f"Listed as posted {as_of}, with no close date. Read the notice for timing. {confirm}", "warn")
        if close < today:
            return DeadlineStatus("passed", f"Close date passed ({fmt_date(close)})",
                                  f"Its close date ({fmt_date(close)}) has passed, although it was listed as posted {as_of}.", "no")
        days = (close - today).days
        if days <= CLOSING_SOON_DAYS:
            when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
            return DeadlineStatus("closing_soon", f"Posted on Grants.gov: closes {fmt_date(close)} ({when})",
                                  f"Listed as posted {as_of}, closing {fmt_date(close)}. {confirm}", "warn")
        return DeadlineStatus("posted", f"Posted on Grants.gov: closes {fmt_date(close)}",
                              f"Listed as posted {as_of}, closing {fmt_date(close)}. {confirm}", "ok")
    if status == "listed":  # built from a notice alone; the search status was not checked
        if close is None:
            return DeadlineStatus("unknown", "Grants.gov notice: no close date listed",
                                  f"The Grants.gov notice listed no close date {as_of}. {confirm}", "warn")
        if close < today:
            return DeadlineStatus("passed", f"Close date passed ({fmt_date(close)})",
                                  f"The Grants.gov notice's close date ({fmt_date(close)}) has passed.", "no")
        return DeadlineStatus("listed", f"Grants.gov notice: closes {fmt_date(close)}",
                              f"The Grants.gov notice lists a close date of {fmt_date(close)} {as_of}; "
                              f"its posting status was not checked. {confirm}", "warn")
    if status in ("closed", "archived"):
        return DeadlineStatus("passed", f"{status.title()} on Grants.gov", f"Listed as {status} {as_of}.", "no")
    return DeadlineStatus("unknown", "Status unknown", f"Grants.gov did not report a usable status {as_of}. {confirm}", "warn")


def looks_like_research(title: str, number: str) -> bool:
    return bool(_RESEARCH.search(title) or _RESEARCH_NUMBER.match(number or ""))


def _live_checks(f: SearchFilters, research: bool, details: gg.Details | None) -> tuple[list[Check], list[str]]:
    params = f.live_params()
    checks: list[Check] = []
    unknowns = ["Full eligibility rules: read the notice on Grants.gov.",
                "Geographic limits: search results do not show them."]

    if details is not None:
        codes = {code for code, _ in details.applicant_types}
        wanted = TAX_TO_ELIGIBILITY.get(f.tax_status)
        if not codes:
            checks.append(Check("Applicant type", UNKNOWN, "Grants.gov did not list eligible applicant types."))
        elif wanted and wanted in codes:
            checks.append(Check("Applicant type", MEETS, "Grants.gov lists your organization type as eligible (your 501(c)(3) status is self-reported)."))
        elif "25" in codes:
            checks.append(Check("Applicant type", UNKNOWN, "Grants.gov lists \"Others\" as eligible; the notice explains who that includes."))
        elif wanted:
            checks.append(Check("Applicant type", FAILS, "Grants.gov does not list your organization type as an eligible applicant.", hard=True))
        else:
            checks.append(Check("Applicant type", UNKNOWN, "Set your 501(c)(3) status in your profile to check applicant type."))
        checks.append(_award_check(f.requested_amount, details.award_floor, details.award_ceiling, live=True))
        if details.cost_sharing is True:
            checks.append(Check("Cost sharing", UNKNOWN, "Grants.gov says cost sharing or matching is required; check the notice for how much."))
        elif details.cost_sharing is False:
            checks.append(Check("Cost sharing", MEETS, "Grants.gov says no cost sharing is required."))
        if details.eligibility_text:
            unknowns.append("Additional eligibility text from the notice needs a human read (shown below).")
    else:
        if params.eligibilities:
            checks.append(Check("Applicant type", MEETS,
                                "Found with Grants.gov's eligibility filter for your organization type "
                                "(your 501(c)(3) status is self-reported)."))
        else:
            checks.append(Check("Applicant type", UNKNOWN, "Set your 501(c)(3) status in your profile to filter by applicant type."))
        checks.append(Check("Award range", UNKNOWN, "Award amounts are not in search results. Load details from Grants.gov."))
        unknowns.append("Award amount and cost sharing: load details from Grants.gov.")

    if params.categories:
        checks.append(Check("Focus area", MEETS, "Found with your focus-area categories (" + ", ".join(params.categories) + ") on Grants.gov."))
    else:
        checks.append(Check("Focus area", UNKNOWN, "Your focus areas have no matching Grants.gov category, so results were not filtered by topic."))
    if research:
        checks.append(Check("Research grant?", UNKNOWN, "Looks like a research grant (for example an NIH R01 or a clinical trial). These usually fund universities and research institutions."))
    return checks, unknowns


def live_result(hit: gg.Hit, retrieved_at: datetime, f: SearchFilters, today: date) -> GrantResult:
    research = looks_like_research(hit.title, hit.number)
    checks, unknowns = _live_checks(f, research, None)
    return GrantResult(
        source=LIVE,
        id=hit.id,
        number=hit.number,
        title=hit.title,
        funder=hit.agency,
        summary="",
        amount_min=None,
        amount_max=None,
        close_date=hit.close_date,
        deadline=live_deadline(hit.status, hit.close_date, retrieved_at, today),
        status_reported=hit.status or "unknown",
        source_url=gg.detail_url(hit.id),
        retrieved_at=retrieved_at,
        eligibility=(),
        checks=tuple(checks),
        unknowns=tuple(unknowns),
        research_like=research,
    )


def with_details(result: GrantResult, details: gg.Details, f: SearchFilters, today: date) -> GrantResult:
    checks, unknowns = _live_checks(f, result.research_like, details)
    status = "forecasted" if details.doc_type == "forecast" else result.status_reported
    close = details.close_date or result.close_date
    return replace(
        result,
        title=details.title or result.title,
        funder=details.agency or result.funder,
        summary=details.description,
        amount_min=details.award_floor,
        amount_max=details.award_ceiling,
        close_date=close,
        deadline=live_deadline(status, close, details.retrieved_at, today),
        retrieved_at=details.retrieved_at,
        eligibility=tuple(label for _, label in details.applicant_types),
        eligibility_text=details.eligibility_text,
        checks=tuple(checks),
        unknowns=tuple(unknowns),
        details_loaded=True,
    )


def result_from_details(details: gg.Details, f: SearchFilters, today: date) -> GrantResult:
    """A live result built from fetchOpportunity alone, for a grant id that did not come from a search."""
    status = "forecasted" if details.doc_type == "forecast" else "listed"
    base = GrantResult(
        source=LIVE, id=details.id, number=details.number, title=details.title, funder=details.agency,
        summary="", amount_min=None, amount_max=None, close_date=details.close_date,
        deadline=live_deadline(status, details.close_date, details.retrieved_at, today),
        status_reported=status, source_url=gg.detail_url(details.id), retrieved_at=details.retrieved_at,
        eligibility=(), checks=(), unknowns=(), research_like=looks_like_research(details.title, details.number),
    )
    return with_details(base, details, f, today)


# ---------------------------------------------------------------- ranking

_DEADLINE_ORDER = {"sample": 0, "posted": 0, "closing_soon": 0, "no_close_date": 1, "listed": 1,
                   "forecasted": 2, "unknown": 3, "passed": 4}


def rank(results: list[GrantResult]) -> list[GrantResult]:
    """Hard failures last; research-type grants next to last; then deadline status, checks, date, title."""
    return sorted(results, key=lambda r: (
        r.hard_fail,
        r.research_like,
        _DEADLINE_ORDER.get(r.deadline.code, 3),
        r.count(FAILS),
        -r.count(MEETS),
        r.close_date or date.max,
        r.title.lower(),
    ))


# ---------------------------------------------------------------- traced entry points

def run_search(user_id: int, f: SearchFilters, source: str, *,
               client: gg.GrantsGovClient | None = None, today: date | None = None) -> SearchOutcome:
    """Run one traced search: build the query, call the search tool, then filter and rank."""
    today = today or _utc_today()
    with trace.run(user_id, "grant_search") as run:
        with run.step("build_query_from_profile", kind="code", **f.safe_summary(source)) as step:
            step.ok()
        if source == SAMPLE:
            outcome = _sample_search(run, f)
        else:
            outcome = _live_search(run, f, client or gg.default_client(), today)
    outcome.run_id = run.run_id
    return outcome


def _sample_search(run: trace.Run, f: SearchFilters) -> SearchOutcome:
    with run.step("search_sample_grants", kind="tool", source=SAMPLE) as step:
        matches, hidden = filter_samples(f)
        step.ok(result_count=len(matches), hidden_failing=hidden)
    with run.step("rank_results", kind="code") as step:
        ranked = rank(matches)
        step.ok(result_count=len(ranked), top_ids=[r.id for r in ranked[:5]])
    return SearchOutcome(SAMPLE, ranked, total_matches=len(ranked) + hidden, hidden_failing=hidden)


def _live_search(run: trace.Run, f: SearchFilters, client: gg.GrantsGovClient, today: date) -> SearchOutcome:
    params = f.live_params()
    with run.step("search_grants_gov", kind="tool", source=LIVE, categories=list(params.categories),
                  eligibility_codes=list(params.eligibilities), rows=params.rows) as step:
        sent_before = client.requests_sent
        try:
            page = client.search(params)
        except gg.GrantsGovRateLimited as err:
            step.set_status("rate_limited", retry_after_s=err.retry_after,
                            http_requests=client.requests_sent - sent_before)
            return SearchOutcome(LIVE, [], 0, error=err.user_message, error_kind=err.kind)
        except gg.GrantsGovError as err:
            step.fail(err.kind, http_requests=client.requests_sent - sent_before)
            return SearchOutcome(LIVE, [], 0, error=err.user_message, error_kind=err.kind)
        step.ok(result_count=len(page.hits), total_matches=page.hit_count, from_cache=page.from_cache,
                skipped_malformed=page.skipped, http_requests=client.requests_sent - sent_before)

    with run.step("filter_and_rank", kind="code") as step:
        outcome = live_outcome(page, f, today)
        step.ok(result_count=len(outcome.results), hidden_closed=outcome.hidden_closed,
                hidden_failing=outcome.hidden_failing, hidden_research=outcome.hidden_research,
                top_ids=[r.id for r in outcome.results[:5]])
    return outcome


def dedupe(results: list[GrantResult]) -> tuple[list[GrantResult], int]:
    """One row per opportunity. Returns (kept, merged).

    Grants.gov can return the same opportunity more than once on a single page — a forecast record and a
    synopsis record, or the same notice listed by more than one office. A real tester searching Virginia got
    the same U.S. embassy opportunity twice. Opportunities are identified by their opportunity number, and
    where two records share one, the better-dated record wins so a stale forecast cannot hide a live posting.
    """
    best: dict[str, GrantResult] = {}
    order: list[str] = []
    for result in results:
        key = (result.number or "").strip().upper() or f"id:{result.id}"
        current = best.get(key)
        if current is None:
            best[key] = result
            order.append(key)
        elif (_DEADLINE_ORDER.get(result.deadline.code, 9)
              < _DEADLINE_ORDER.get(current.deadline.code, 9)):
            best[key] = result
    return [best[k] for k in order], len(results) - len(order)


def live_outcome(page: gg.SearchPage, f: SearchFilters, today: date) -> SearchOutcome:
    """Turn one Grants.gov results page into checked, filtered, ranked results (pure code)."""
    built = [live_result(h, page.retrieved_at, f, today) for h in page.hits]
    built, duplicates_merged = dedupe(built)
    kept = [r for r in built if r.deadline.code != "passed"]
    hidden_closed = len(built) - len(kept)
    hidden_failing = hidden_research = 0
    if f.hide_failing:
        hidden_failing = sum(r.hard_fail for r in kept)
        kept = [r for r in kept if not r.hard_fail]
    if f.hide_research:
        hidden_research = sum(r.research_like for r in kept)
        kept = [r for r in kept if not r.research_like]
    hidden_award = 0
    if f.award_range:
        wanted = [r for r in kept if award_in_range(f, r.amount_min, r.amount_max)]
        hidden_award = len(kept) - len(wanted)
        kept = wanted
    return SearchOutcome(LIVE, rank(kept), total_matches=page.hit_count, retrieved_at=page.retrieved_at,
                         from_cache=page.from_cache, skipped_malformed=page.skipped,
                         duplicates_merged=duplicates_merged, hidden_award=hidden_award,
                         hidden_closed=hidden_closed, hidden_failing=hidden_failing,
                         hidden_research=hidden_research)


def run_details(user_id: int, result: GrantResult, f: SearchFilters, *,
                client: gg.GrantsGovClient | None = None, today: date | None = None
                ) -> tuple[GrantResult, str | None]:
    """Load Grants.gov details for one live result. Returns (result, error message or None)."""
    if not result.is_live:
        return result, None
    today = today or _utc_today()
    client = client or gg.default_client()
    with trace.run(user_id, "grant_details") as run:
        with run.step("fetch_grants_gov_details", kind="tool", opportunity_id=result.id) as step:
            sent_before = client.requests_sent
            try:
                details = client.fetch(result.id)
            except gg.GrantsGovRateLimited as err:
                step.set_status("rate_limited", retry_after_s=err.retry_after)
                return result, err.user_message
            except gg.GrantsGovError as err:
                step.fail(err.kind, http_requests=client.requests_sent - sent_before)
                return result, err.user_message
            if details is None:
                step.set_status("not_found", found=False, http_requests=client.requests_sent - sent_before)
                return result, "Grants.gov no longer returns details for this opportunity. Check the source page."
            updated = with_details(result, details, f, today)
            step.ok(found=True, from_cache=details.from_cache, http_requests=client.requests_sent - sent_before,
                    checks_meets=updated.count(MEETS), checks_fails=updated.count(FAILS),
                    checks_unknown=updated.count(UNKNOWN))
    return updated, None

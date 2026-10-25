"""Privacy-safe trace of agent runs and their tool calls.

A run (for example one grant search) is a list of steps. Each step records the
tool name, whether it was code, a tool, or the AI model, its status, timing,
token counts, and a small set of allowlisted arguments and result counts.

Recorded: tool names, timings, statuses, error categories, result counts,
filter categories (state code, focus areas, Grants.gov category codes), public
grant ids, and token counts. Each model call also records the model, its input,
cached (cache read), cache-write, output, and reasoning tokens as the provider
reported them, whether usage was reported at all, the gateway's cache result,
and an estimated cost with the rates it used (pricing.py).

Never recorded: search keyword text (only its length), profile text, email
addresses, passwords, API keys, model prompts, or model replies. Anything not
on the allowlist is dropped before it reaches the database or the log.

Traces belong to one user and are read back only with that user's id. Each user
keeps their most recent MAX_RUNS_PER_USER runs, plus every AI run from the last
24 hours, because the budgets and rate limits count those.
"""

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from grantbridge import pricing
from grantbridge.db import connect, now_iso
from grantbridge.repo import KEY_PROFILE_FIELDS
from grantbridge.validation import FOCUS_AREAS, US_STATES

log = logging.getLogger("grantbridge.trace")

MAX_RUNS_PER_USER = 50
BUDGET_WINDOW = timedelta(hours=24)  # AI runs this recent are never pruned (see llm.py's budgets)
TOKEN_FIELDS = ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens")
_USAGE_ORDER = {"": 0, "reported": 1, "no cache detail": 2, "not reported": 3}

_TOKEN = re.compile(r"^[a-z][a-z0-9 _./\-]{0,39}$")   # e.g. "grants.gov", "possible fit"
_CODE = re.compile(r"^[A-Z0-9]{1,4}$")                # Grants.gov category / eligibility codes
_ID = re.compile(r"^[a-z0-9\-]{1,40}$")               # public grant ids: "sample-01", "361822"


def _in(vocabulary) -> callable:
    return lambda v: v in vocabulary


# String-valued keys and the only values they may hold. Every other allowlisted
# key must be a number, a boolean, or None; strings under those keys are dropped.
_STRING_RULES = {
    "source": _TOKEN.match,
    "state": _in(set(US_STATES) | {""}),
    "focus_areas": _in(set(FOCUS_AREAS)),
    "categories": _CODE.match,
    "eligibility_codes": _CODE.match,
    "statuses": _TOKEN.match,
    "top_ids": _ID.match,
    "grant_id": _ID.match,
    "opportunity_id": _ID.match,
    "model": _TOKEN.match,
    "verdict": _TOKEN.match,
    "confidence": _TOKEN.match,
    "error_kind": re.compile(r"^[A-Za-z_]{1,40}$").match,
    "missing_fields": _in(set(KEY_PROFILE_FIELDS.values())),
    "mode": _in({"live", "mock"}),
    "intent": _TOKEN.match,
    "stop_reason": _TOKEN.match,
    "refusal_reason": _TOKEN.match,
    "reasoning_effort": _in({"default", "minimal", "low", "medium", "high"}),
    "deadline_source": _in({"grants.gov", "sample", "user"}),
}
_NUMERIC_KEYS = frozenset({
    "rows", "min_award", "hide_failing", "hide_research", "has_keyword", "keyword_chars",
    "result_count", "total_matches", "skipped_malformed", "hidden_closed", "hidden_failing", "hidden_research",
    "from_cache", "found", "details_loaded", "checks_meets", "checks_fails", "checks_unknown",
    "http_requests", "retry_after_s", "guard_removed_sentences", "guard_verdict_changed",
    "guard_confidence_capped",
    # advisor
    "tool_round", "tool_calls", "model_calls", "history_messages", "message_chars",
    "fields_known", "fields_missing", "saved", "already_saved", "refused",
    "application_count", "sections_total", "sections_answered",
    "known_facts", "assumptions", "clarifying", "guard_unverified_figures", "guard_uncited_grants",
    "guard_eligibility_claims", "budget_remaining",
    # drafting
    "section_id", "word_count", "word_limit", "unsupported_figures", "unrecognized_names", "placeholders",
    "injection_signals", "requirements_total", "requirements_met", "quotes_unverified", "checklist_items",
    "facts_known", "facts_added",
    # proposal review and revisions
    "application_id", "dimensions_assessed", "caps_applied", "recs_relabeled", "quotes_dropped",
    "predictions_removed", "figures_replaced", "recommendations", "claims_kept", "missing_items", "changes",
    # budget and narrative
    "budget_items", "budget_checks", "target_words", "commitments_removed", "lines_not_mentioned",
    # application timeline
    "days_left", "plan_days", "default_days", "steps_total", "steps_done", "overdue_steps", "plan_flags",
    "kept_done",
    # pursuit assessment
    "rules_fired", "fit_reused", "eligibility_removed",
    # portfolio and mission drift
    "ai_overridden", "candidates", "recommended", "deferred", "excluded", "hours_per_week",
    # Can We Afford to Win? (counts only: no money figures, no notice text)
    "notice_chars", "conditions_found", "conditions_kept", "numbers_dropped", "injected_dropped",
    # output sanitization
    "output_secrets_redacted", "output_images_removed", "output_links_removed", "output_html_removed",
    "output_instruction_leaks",
})
SAFE_KEYS = frozenset(_STRING_RULES) | _NUMERIC_KEYS

_DROP = object()


def safe_fields(values: dict) -> dict:
    """Keep only allowlisted keys whose values pass that key's rule; drop everything else."""
    out = {}
    for key, value in values.items():
        if key in _STRING_RULES:
            cleaned = _safe_strings(value, _STRING_RULES[key])
        elif key in _NUMERIC_KEYS:
            cleaned = value if value is None or isinstance(value, (bool, int, float)) else _DROP
        else:
            continue
        if cleaned is not _DROP:
            out[key] = cleaned
    return out


def _token(value) -> str:
    """A short lower-case label (model name, cache status) or '' when the value does not look like one."""
    value = str(value or "").strip().lower()
    return value if _TOKEN.match(value) else ""


def _safe_strings(value, rule):
    if isinstance(value, str):
        return value if rule(value) else _DROP
    if isinstance(value, (list, tuple, set)):
        items = sorted(value) if isinstance(value, set) else list(value)
        if len(items) > 20 or not all(isinstance(i, str) and rule(i) for i in items):
            return _DROP
        return items
    return _DROP


@dataclass
class Step:
    tool: str
    kind: str  # "code", "tool", or "llm"
    args: dict
    status: str = "ok"
    summary: dict = field(default_factory=dict)
    duration_ms: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    model: str = ""
    served_model: str = ""
    gateway_cache: str = ""
    usage_status: str = ""  # model calls: reported / no cache detail / not reported
    cost_usd: float | None = None
    price_ref: str = ""
    _calls: int = 0

    def __post_init__(self) -> None:
        if self.kind == "llm" and not self.usage_status:
            self.usage_status = "not reported"  # until a call's usage arrives (a call that raised has none)

    def ok(self, **summary) -> None:
        self.status = "ok"
        self.summary.update(safe_fields(summary))

    def fail(self, error_kind: str, **summary) -> None:
        self.status = "error"
        self.summary.update(safe_fields({"error_kind": error_kind, **summary}))

    def set_status(self, status: str, **summary) -> None:
        self.status = status
        self.summary.update(safe_fields(summary))

    def add_usage(self, usage: dict, model: str = "") -> None:
        """Add one model call's token counts and estimated cost (llm.usage_of / llm.respond output).

        A call whose usage was not reported adds no tokens and leaves the cost unknown, never a made-up zero.
        """
        status = usage.get("usage_status") or ("reported" if usage else "not reported")
        for key in TOKEN_FIELDS:
            setattr(self, key, getattr(self, key) + int(usage.get(key, 0) or 0))
        self.model = self.model or _token(model)
        self.served_model = self.served_model or _token(usage.get("served_model"))
        self.gateway_cache = _token(usage.get("gateway_cache")) or self.gateway_cache
        first = self._calls == 0
        self.usage_status = status if first else max(self.usage_status, status, key=_USAGE_ORDER.get)
        cost, ref = pricing.estimate(model, {**usage, "usage_status": status})
        if first:
            self.cost_usd, self.price_ref = cost, ref
        else:
            self.cost_usd = None if cost is None or self.cost_usd is None else self.cost_usd + cost
            self.price_ref = self.price_ref if ref == self.price_ref else "several price sources"
        self._calls += 1


@dataclass
class Run:
    user_id: int
    kind: str
    steps: list[Step] = field(default_factory=list)
    status: str = "ok"
    run_id: int | None = None
    duration_ms: int | None = None  # set when the run is saved
    _started: float = field(default_factory=time.perf_counter)
    _started_at: str = field(default_factory=now_iso)

    @contextmanager
    def step(self, tool: str, kind: str = "tool", **args):
        step = Step(tool=tool, kind=kind, args=safe_fields(args))
        self.steps.append(step)
        started = time.perf_counter()
        try:
            yield step
        except Exception as exc:
            step.fail(type(exc).__name__)
            raise
        finally:
            step.duration_ms = int((time.perf_counter() - started) * 1000)
            if step.status != "ok" and self.status == "ok":
                self.status = step.status

    def totals(self) -> dict:
        return {key: sum(getattr(s, key) for s in self.steps) for key in TOKEN_FIELDS}

    def elapsed_ms(self) -> int:
        """Time since the run started, or its final duration once saved."""
        if self.duration_ms is not None:
            return self.duration_ms
        return int((time.perf_counter() - self._started) * 1000)

    def usage_summary(self) -> dict:
        """The model calls so far in this run: tokens, estimated cost, and time. Saved with drafts and reviews."""
        return summarize_calls([s.__dict__ for s in self.steps], elapsed_ms=self.elapsed_ms())

    def save(self) -> int:
        duration = self.duration_ms = self.elapsed_ms()
        window_start = (datetime.now(timezone.utc) - BUDGET_WINDOW).isoformat(timespec="seconds")
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO agent_runs (user_id, kind, status, started_at, duration_ms) VALUES (?, ?, ?, ?, ?)",
                (self.user_id, self.kind, self.status, self._started_at, duration),
            )
            self.run_id = cur.lastrowid
            conn.executemany(
                """INSERT INTO agent_steps (run_id, position, tool, kind, status, args, summary, duration_ms,
                                            input_tokens, cached_tokens, cache_write_tokens, output_tokens,
                                            reasoning_tokens, model, served_model, gateway_cache, usage_status,
                                            cost_usd, price_ref)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (self.run_id, i, s.tool, s.kind, s.status, json.dumps(s.args), json.dumps(s.summary),
                     s.duration_ms, s.input_tokens, s.cached_tokens, s.cache_write_tokens, s.output_tokens,
                     s.reasoning_tokens, s.model, s.served_model, s.gateway_cache, s.usage_status,
                     None if s.cost_usd is None else round(s.cost_usd, 10), s.price_ref)
                    for i, s in enumerate(self.steps)
                ],
            )
            # Keep the newest runs, and every AI run inside the budget window: otherwise a burst of cheap runs
            # (plain searches) would push recent AI runs out and reset the daily budget and rate limits.
            conn.execute(
                """DELETE FROM agent_runs WHERE user_id = ? AND id NOT IN
                       (SELECT id FROM agent_runs WHERE user_id = ? ORDER BY id DESC LIMIT ?)
                     AND NOT (started_at >= ? AND id IN (SELECT run_id FROM agent_steps WHERE kind = 'llm'))""",
                (self.user_id, self.user_id, MAX_RUNS_PER_USER, window_start),
            )
        for s in self.steps:
            log.info(
                "trace run=%s kind=%s tool=%s type=%s status=%s ms=%d tokens_in=%d tokens_out=%d cost_usd=%s",
                self.run_id, self.kind, s.tool, s.kind, s.status, s.duration_ms, s.input_tokens, s.output_tokens,
                "-" if s.cost_usd is None else f"{s.cost_usd:.6f}",
            )
        return self.run_id


@contextmanager
def run(user_id: int, kind: str):
    """Record a run. It is saved even if a step raises, with the run marked as an error."""
    current = Run(user_id=user_id, kind=kind)
    try:
        yield current
    except Exception:
        current.status = "error"
        raise
    finally:
        current.save()


# ---------------------------------------------------------------- reading (owner only)

def tokens_used_since(user_id: int, since_iso: str) -> int:
    """Input plus output tokens this user's runs spent since `since_iso` (for the daily AI budget).

    Portkey cache hits are left out: they reached no model, and their counts are copies of an earlier call's.
    """
    with connect() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(s.input_tokens + s.output_tokens), 0)
                 FROM agent_steps s JOIN agent_runs r ON r.id = s.run_id
                WHERE r.user_id = ? AND r.started_at >= ? AND s.gateway_cache != 'hit'""",
            (user_id, since_iso),
        ).fetchone()
    return int(row[0])


def tokens_used_since_all(since_iso: str) -> int:
    """Input plus output tokens spent by every account since `since_iso` (for the server-wide budget)."""
    with connect() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(s.input_tokens + s.output_tokens), 0)
                 FROM agent_steps s JOIN agent_runs r ON r.id = s.run_id
                WHERE r.started_at >= ? AND s.gateway_cache != 'hit'""",
            (since_iso,),
        ).fetchone()
    return int(row[0])


def ai_run_starts_since(user_id: int, since_iso: str) -> list[str]:
    """Start times of this user's runs that called the AI model since `since_iso`, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT DISTINCT r.id, r.started_at FROM agent_runs r JOIN agent_steps s ON s.run_id = r.id
                WHERE r.user_id = ? AND r.started_at >= ? AND s.kind = 'llm' ORDER BY r.started_at""",
            (user_id, since_iso),
        ).fetchall()
    return [r["started_at"] for r in rows]


def summarize_calls(steps: list[dict], elapsed_ms: int | None = None) -> dict:
    """Totals over a run's model calls: tokens, estimated cost, and time.

    cost_usd is None when any model call could not be priced (usage not reported, or no rate for the model);
    priced_cost_usd then holds the part that could. A run with no model calls costs 0.
    """
    calls = [s for s in steps if s["kind"] == "llm"]
    costs = [s["cost_usd"] for s in calls]
    priced = [c for c in costs if c is not None]
    return {
        "model": next((s["model"] for s in calls if s["model"]), ""),
        "served_model": next((s["served_model"] for s in calls if s["served_model"]), ""),
        "gateway_cache": sorted({s["gateway_cache"] for s in calls if s["gateway_cache"]}),
        "model_calls": len(calls),
        "tool_calls": sum(s["kind"] == "tool" for s in steps),
        **{key: sum(int(s[key]) for s in calls) for key in TOKEN_FIELDS},
        "cost_usd": None if len(priced) < len(costs) else round(sum(priced), 10),
        "priced_cost_usd": round(sum(priced), 10),
        "unpriced_calls": len(costs) - len(priced),
        "unreported_calls": sum(s["usage_status"] == "not reported" for s in calls),
        "gateway_hits": sum(s["gateway_cache"] == "hit" for s in calls),
        "model_ms": sum(int(s["duration_ms"]) for s in calls),
        "elapsed_ms": elapsed_ms,
        "price_ref": next((s["price_ref"] for s in calls if s["cost_usd"] is not None and s["price_ref"]), ""),
    }


def list_runs(user_id: int, limit: int = 10) -> list[dict]:
    """This user's newest runs, each with its totals (see summarize_calls) and kind, status, start, duration."""
    with connect() as conn:
        runs = conn.execute(
            "SELECT id, kind, status, started_at, duration_ms FROM agent_runs WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        steps = conn.execute(
            f"""SELECT s.run_id, {_STEP_COLUMNS} FROM agent_steps s JOIN agent_runs r ON r.id = s.run_id
                 WHERE r.user_id = ? AND s.run_id IN ({','.join('?' * len(runs)) or 'NULL'})""",
            (user_id, *[r["id"] for r in runs]),
        ).fetchall()
    by_run: dict[int, list[dict]] = {}
    for s in steps:
        by_run.setdefault(s["run_id"], []).append(dict(s))
    return [{**dict(r), **summarize_calls(by_run.get(r["id"], []), elapsed_ms=r["duration_ms"])} for r in runs]


def run_summary(user_id: int, run_id: int) -> dict | None:
    """One run's totals (see summarize_calls), or None if the run is not this user's."""
    with connect() as conn:
        run = conn.execute("SELECT duration_ms FROM agent_runs WHERE id = ? AND user_id = ?",
                           (run_id, user_id)).fetchone()
    if run is None:
        return None
    return summarize_calls(run_steps(user_id, run_id), elapsed_ms=run["duration_ms"])


def usage_since(user_id: int, since_iso: str) -> dict:
    """This user's model calls since `since_iso`: runs, calls, tokens, and estimated cost (for Settings)."""
    with connect() as conn:
        row = conn.execute(
            """SELECT COUNT(DISTINCT r.id) AS ai_runs, COUNT(s.id) AS model_calls,
                      COALESCE(SUM(s.input_tokens), 0) AS input_tokens,
                      COALESCE(SUM(s.cached_tokens), 0) AS cached_tokens,
                      COALESCE(SUM(s.cache_write_tokens), 0) AS cache_write_tokens,
                      COALESCE(SUM(s.output_tokens), 0) AS output_tokens,
                      COALESCE(SUM(s.reasoning_tokens), 0) AS reasoning_tokens,
                      COALESCE(SUM(s.cost_usd), 0) AS priced_cost_usd,
                      COALESCE(SUM(s.cost_usd IS NULL), 0) AS unpriced_calls,
                      COALESCE(SUM(s.gateway_cache = 'hit'), 0) AS gateway_hits
                 FROM agent_steps s JOIN agent_runs r ON r.id = s.run_id
                WHERE r.user_id = ? AND r.started_at >= ? AND s.kind = 'llm'""",
            (user_id, since_iso),
        ).fetchone()
    return dict(row)


_STEP_COLUMNS = """s.position, s.tool, s.kind, s.status, s.args, s.summary, s.duration_ms,
                   s.input_tokens, s.cached_tokens, s.cache_write_tokens, s.output_tokens, s.reasoning_tokens,
                   s.model, s.served_model, s.gateway_cache, s.usage_status, s.cost_usd, s.price_ref"""


def run_steps(user_id: int, run_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT {_STEP_COLUMNS}
                 FROM agent_steps s JOIN agent_runs r ON r.id = s.run_id
                WHERE s.run_id = ? AND r.user_id = ?
                ORDER BY s.position""",
            (run_id, user_id),
        ).fetchall()
    steps = []
    for r in rows:
        step = dict(r)
        step["args"] = json.loads(step["args"])
        step["summary"] = json.loads(step["summary"])
        steps.append(step)
    return steps

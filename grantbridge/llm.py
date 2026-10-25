"""Shared model client: one place that builds the OpenAI-compatible client from config."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from openai import OpenAI

from grantbridge import trace
from grantbridge.config import resolve_settings
from grantbridge.db import connect, install_id

REQUEST_TIMEOUT = 60.0
# Response headers read after each call (never request headers, which carry the API key).
GATEWAY_CACHE_HEADER = "x-portkey-cache-status"  # Portkey's response cache: miss, hit, refresh, ...
SERVED_MODEL_HEADER = "x-ms-served-model"  # the model snapshot Azure OpenAI ran
# Documented by Portkey ("Cache (Simple & Semantic)"): skip the saved copy and make a new model call.
FRESH_ANSWER_HEADER = {"x-portkey-cache-force-refresh": "true"}
_HEADER_TOKEN = re.compile(r"^[a-z0-9][a-z0-9 ._\-]{0,39}$")


def get_client(*, fresh_answers: bool = False) -> tuple[OpenAI, str]:
    """Return (client, model name). Raises config.ConfigError when no key is set.

    fresh_answers asks Portkey never to answer from its response cache. Only the cost measurement uses it, so
    that every measured call is a real model call rather than a replay of an earlier one.
    """
    settings = resolve_settings()
    client = OpenAI(**client_options(settings, fresh_answers=fresh_answers), timeout=REQUEST_TIMEOUT, max_retries=1)
    return client, settings.model


def client_options(settings, *, fresh_answers: bool = False) -> dict:
    """Keyword arguments for OpenAI(...): the provider's own, plus Portkey's fresh-answer header when asked."""
    kwargs = settings.client_kwargs()
    if fresh_answers and settings.provider == "portkey":
        kwargs["default_headers"] = {**kwargs.get("default_headers", {}), **FRESH_ANSWER_HEADER}
    return kwargs


def cache_key(feature: str, user_id: int) -> str:
    """prompt_cache_key for one feature and one account of this installation.

    OpenAI uses the key for separate cache accounting (GPT-5.6 and later), so one account's prompts never share
    a prompt cache with another's: nobody can probe for another account's prompts through cache hits, and each
    account's cached-token counts are its own. The installation's random id is mixed in because account ids
    repeat across installations, and the hash keeps both out of what the provider sees.
    """
    digest = hashlib.sha256(f"{install_id()}:{int(user_id)}".encode()).hexdigest()[:20]
    return f"grantbridge-{feature}-{digest}"


REASONING_EFFORTS = ("minimal", "low", "medium", "high")


def reasoning_effort() -> str | None:
    """Reasoning effort sent with every model call: GRANTBRIDGE_REASONING_EFFORT, default "low".

    "default" sends no setting, so the provider's default applies (medium for gpt-6-luna). Reasoning tokens are
    billed as output tokens, the most expensive kind; docs/TOKENOMICS.md measures what "low" saves and whether
    answers got worse.
    """
    value = os.getenv("GRANTBRIDGE_REASONING_EFFORT", "low").strip().lower()
    if value == "default":
        return None
    return value if value in REASONING_EFFORTS else "low"


def reasoning_options() -> dict:
    """Extra request fields for the reasoning effort (none when the provider's default applies)."""
    effort = reasoning_effort()
    return {"reasoning": {"effort": effort}} if effort else {}


ZERO_USAGE = {"input_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0,
              "reasoning_tokens": 0}


def usage_of(response) -> dict:
    """Token counts from a Responses API result, with usage_status saying whether the provider reported them.

    "reported": every count came from the provider. "no cache detail": totals only, so cache reads and writes
    are unknown (recorded as 0). "not reported": no usage at all; the zeros are not real counts and the call gets
    no cost estimate.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {**ZERO_USAGE, "usage_status": "not reported"}
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "cached_tokens": int(getattr(input_details, "cached_tokens", 0) or 0),
        "cache_write_tokens": int(getattr(input_details, "cache_write_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "reasoning_tokens": int(getattr(output_details, "reasoning_tokens", 0) or 0),
        "usage_status": "reported" if input_details is not None else "no cache detail",
    }


def _header_token(value) -> str:
    value = str(value or "").strip().lower()
    return value if _HEADER_TOKEN.match(value) else ""


def respond(client, *, parse: bool = False, **request):
    """Make one Responses API call. Returns (response, usage).

    usage is usage_of(response) plus two facts from the response headers: gateway_cache (Portkey's cache result;
    "hit" means a saved copy of an earlier identical answer, whose token counts are that earlier call's) and
    served_model (the model snapshot that answered). Wrappers and test fakes without with_raw_response are called
    directly, without headers.
    """
    method = "parse" if parse else "create"
    raw_api = getattr(client.responses, "with_raw_response", None)
    if raw_api is None:
        response, headers = getattr(client.responses, method)(**request), {}
    else:
        raw = getattr(raw_api, method)(**request)
        response, headers = raw.parse(), raw.headers
    usage = usage_of(response)
    usage["gateway_cache"] = _header_token(headers.get(GATEWAY_CACHE_HEADER))
    usage["served_model"] = _header_token(headers.get(SERVED_MODEL_HEADER) or getattr(response, "model", None))
    return response, usage


# ---------------------------------------------------------------- daily budget (overspending guard)

def daily_budget() -> int:
    """Max input + output tokens per account per rolling 24 hours (GRANTBRIDGE_DAILY_TOKEN_BUDGET).

    Portkey cache hits do not count: they reach no model and cost nothing.
    """
    try:
        return max(0, int(os.getenv("GRANTBRIDGE_DAILY_TOKEN_BUDGET", "100000")))
    except ValueError:
        return 100_000


def tokens_used_today(user_id: int) -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    return trace.tokens_used_since(user_id, since)


def budget_left(user_id: int) -> int:
    return max(0, daily_budget() - tokens_used_today(user_id))


# ---------------------------------------------------------------- rate limits (overspending and abuse guards)

BUSY_NOTICE = ("Another AI request for your account is still running, so this ran in mock mode. "
               "Try again when it finishes.")
# A request that crashed or hung frees the slot after this many seconds. It is longer than the slowest
# legitimate request (5 model calls with a 60-second timeout each, plus tools).
SLOT_TIMEOUT_SECONDS = 360


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def requests_per_minute() -> int:
    """Max AI requests per account per rolling minute (GRANTBRIDGE_AI_REQUESTS_PER_MINUTE)."""
    return _env_int("GRANTBRIDGE_AI_REQUESTS_PER_MINUTE", 15)


def server_daily_budget() -> int:
    """Max tokens for all accounts together per rolling 24 hours (GRANTBRIDGE_SERVER_DAILY_TOKEN_BUDGET).

    The per-account budget alone could be dodged by signing up many accounts; this cap cannot.
    """
    return _env_int("GRANTBRIDGE_SERVER_DAILY_TOKEN_BUDGET", 1_000_000)


def _since(**delta) -> str:
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat(timespec="seconds")


def seconds_until_next_request(user_id: int) -> int:
    """0 if an AI request is allowed now, else how many seconds until the oldest one leaves the window."""
    starts = trace.ai_run_starts_since(user_id, _since(seconds=60))
    if len(starts) < requests_per_minute():
        return 0
    oldest = datetime.fromisoformat(starts[0])
    return max(1, int((oldest + timedelta(seconds=60) - datetime.now(timezone.utc)).total_seconds()) + 1)


@contextmanager
def ai_slot(user_id: int):
    """At most one AI request in flight per account, across every server process. Yields False when one is.

    The slot is a row in ai_inflight; SQLite's primary-key insert is atomic across processes, so two
    requests can never both get it. A slot older than SLOT_TIMEOUT_SECONDS is treated as abandoned.
    """
    token, now = secrets.token_hex(8), time.time()
    with connect() as conn:
        conn.execute("DELETE FROM ai_inflight WHERE user_id = ? AND started_at < ?",
                     (user_id, now - SLOT_TIMEOUT_SECONDS))
        granted = conn.execute("INSERT OR IGNORE INTO ai_inflight (user_id, token, started_at) VALUES (?, ?, ?)",
                               (user_id, token, now)).rowcount == 1
    try:
        yield granted
    finally:
        if granted:
            with connect() as conn:
                conn.execute("DELETE FROM ai_inflight WHERE user_id = ? AND token = ?", (user_id, token))


def choose_mode(user_id: int, want_mock: bool) -> tuple[str, str | None]:
    """("live" or "mock", reason). Mock when asked, when no key is configured, or when the budget is used up."""
    from grantbridge.config import ConfigError

    if want_mock:
        return "mock", None
    try:
        get_client()
    except ConfigError:
        return "mock", "No API key is configured, so this ran in mock mode (no AI call)."
    if budget_left(user_id) <= 0:
        return "mock", (f"You have used today's AI budget ({daily_budget():,} tokens), so this ran in mock mode. "
                        "The budget resets within 24 hours.")
    if trace.tokens_used_since_all(_since(hours=24)) >= server_daily_budget():
        return "mock", ("This GrantBridge server has used its daily AI budget for all accounts, so this ran in "
                        "mock mode. It resets within 24 hours.")
    wait = seconds_until_next_request(user_id)
    if wait:
        return "mock", (f"Too many AI requests in the last minute (limit {requests_per_minute()}), so this ran in "
                        f"mock mode. Try again in about {wait} seconds.")
    return "live", None

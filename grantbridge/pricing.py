"""Token prices and per-call cost estimates.

Rates come from data/pricing.json, or the file named by GRANTBRIDGE_PRICING_FILE. Each entry records the page
its rates came from and the date they were checked. A model without an entry gets no estimate: GrantBridge
never guesses a price, and a call whose usage was not reported gets no estimate either.

How one call is priced (OpenAI's prompt-caching guide): cache reads (cached_tokens) and cache writes
(cache_write_tokens) are both parts of input_tokens, so

    ordinary input = input_tokens - cached_tokens - cache_write_tokens
    cost = ordinary input x input rate + cache reads x cached rate
           + cache writes x cache-write rate + output_tokens x output rate

Reasoning tokens are part of output_tokens and are billed as output. A request with more input tokens than a
tier allows is billed entirely at the next tier's rates. A Portkey response-cache hit never reaches the model
provider, so it costs $0.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from grantbridge.config import REPO_ROOT

log = logging.getLogger("grantbridge.pricing")

DEFAULT_FILE = REPO_ROOT / "data" / "pricing.json"
GATEWAY_HIT_REF = "Portkey cache hit: a saved copy of an earlier identical answer, so no new tokens were billed"


class PricingError(ValueError):
    """The pricing file is missing or malformed."""


@dataclass(frozen=True)
class Tier:
    up_to_input_tokens: int | None  # None: no upper limit
    input: float  # USD per 1M ordinary input tokens
    cached_input: float  # USD per 1M input tokens read from the prompt cache
    cache_write: float  # USD per 1M input tokens written to the prompt cache (30-minute writes)
    output: float  # USD per 1M output tokens, reasoning included


@dataclass(frozen=True)
class ModelPrice:
    model: str
    aliases: tuple[str, ...]
    tiers: tuple[Tier, ...]
    source: str
    source_url: str
    checked: str  # the date the rates were read from source_url
    route: str = ""
    notes: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        """Short citation stored with every estimate, so an old estimate keeps the rates it used."""
        return f"{self.source}, checked {self.checked}"

    def tier_for(self, input_tokens: int) -> Tier:
        for tier in self.tiers:
            if tier.up_to_input_tokens is None or input_tokens <= tier.up_to_input_tokens:
                return tier
        return self.tiers[-1]

    def cost(self, input_tokens: int, cached_tokens: int, cache_write_tokens: int, output_tokens: int) -> float:
        tier = self.tier_for(input_tokens)
        ordinary = max(0, input_tokens - cached_tokens - cache_write_tokens)
        return (ordinary * tier.input + cached_tokens * tier.cached_input + cache_write_tokens * tier.cache_write
                + output_tokens * tier.output) / 1_000_000


def pricing_file() -> Path:
    """GRANTBRIDGE_PRICING_FILE (relative paths start at the repo folder), else data/pricing.json."""
    override = os.getenv("GRANTBRIDGE_PRICING_FILE", "").strip()
    if not override:
        return DEFAULT_FILE
    path = Path(override)
    return path if path.is_absolute() else REPO_ROOT / path


def load(path: Path | str | None = None) -> dict[str, ModelPrice]:
    """Every priced model, keyed by lower-case name and alias. Raises PricingError for a missing or bad file."""
    path = Path(path or pricing_file())
    try:
        stamp = path.stat().st_mtime_ns
    except OSError as err:
        raise PricingError(f"Pricing file not found: {path}") from err
    return _load(str(path), stamp)


def _rate(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise PricingError(f"a rate must be a number of dollars per 1M tokens, not {value!r}")
    return float(value)


@lru_cache(maxsize=4)
def _load(path: str, _stamp: int) -> dict[str, ModelPrice]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        prices: dict[str, ModelPrice] = {}
        for entry in data["models"]:
            tiers = tuple(
                Tier(up_to_input_tokens=None if t["up_to_input_tokens"] is None else int(t["up_to_input_tokens"]),
                     input=_rate(t["input"]), cached_input=_rate(t["cached_input"]),
                     cache_write=_rate(t["cache_write"]), output=_rate(t["output"]))
                for t in entry["tiers"])
            if not tiers or tiers[-1].up_to_input_tokens is not None:
                raise PricingError("the last tier must have no input limit (up_to_input_tokens: null)")
            price = ModelPrice(model=entry["model"], aliases=tuple(entry.get("aliases", ())), tiers=tiers,
                               source=entry["source"], source_url=entry["source_url"], checked=entry["checked"],
                               route=entry.get("route", ""), notes=tuple(entry.get("notes", ())))
            for name in (price.model, *price.aliases):
                prices[name.strip().lower()] = price
        return prices
    except (KeyError, TypeError, ValueError) as err:  # PricingError is a ValueError
        raise PricingError(f"Pricing file {path} is malformed: {err}") from err


def price_for(model: str | None) -> ModelPrice | None:
    """The price entry for a model name or alias, or None (unknown model, or an unreadable pricing file)."""
    if not model:
        return None
    try:
        return load().get(model.strip().lower())
    except PricingError as err:
        log.warning("No cost estimates: %s", err)
        return None


def estimate(model: str | None, usage: dict) -> tuple[float | None, str]:
    """(estimated cost in USD, where the rates came from) for one call's usage (see llm.usage_of).

    The cost is None when it cannot be estimated honestly: usage not reported, or no price for the model.
    """
    if usage.get("gateway_cache") == "hit":
        return 0.0, GATEWAY_HIT_REF
    status = usage.get("usage_status") or ("reported" if usage else "not reported")
    if status == "not reported":
        return None, "no usage reported, so no cost estimate"
    price = price_for(model)
    if price is None:
        return None, f"no price for {model or 'this model'} in the pricing file"
    cost = price.cost(int(usage.get("input_tokens", 0)), int(usage.get("cached_tokens", 0)),
                      int(usage.get("cache_write_tokens", 0)), int(usage.get("output_tokens", 0)))
    if status == "no cache detail":
        return cost, f"{price.ref}; cache details not reported, so all input is priced as ordinary input"
    return cost, price.ref

"""Make one small live model call to confirm the API key and gateway work.

Usage (from the repo folder):
    python -m scripts.check_model

Prints which provider, model, and .env location were used, the model's reply,
and the token counts. The API key itself is never printed.
"""

from __future__ import annotations

import sys
import time

from openai import OpenAI, OpenAIError

from grantbridge.config import ConfigError, resolve_settings

PROMPT = "Reply with exactly: GrantBridge model check succeeded."


def main() -> int:
    try:
        settings = resolve_settings()
    except ConfigError as err:
        print(err, file=sys.stderr)
        return 1

    status = settings.status()
    print(f"Provider: {status['provider']}  Model: {status['model']}  API key: {status['key']}")

    client = OpenAI(**settings.client_kwargs())
    started = time.perf_counter()
    try:
        response = client.responses.create(model=settings.model, input=PROMPT)
    except OpenAIError as err:
        print(f"Model call failed: {type(err).__name__}: {err}", file=sys.stderr)
        return 1
    seconds = time.perf_counter() - started

    usage = response.usage
    cached = getattr(usage.input_tokens_details, "cached_tokens", 0) if usage else 0
    reasoning = getattr(usage.output_tokens_details, "reasoning_tokens", 0) if usage else 0
    print(f"Reply: {response.output_text!r}")
    print(f"Status: {response.status}  Latency: {seconds:.2f}s")
    if usage:
        print(
            f"Tokens: input={usage.input_tokens} (cached={cached}) "
            f"output={usage.output_tokens} (reasoning={reasoning}) total={usage.total_tokens}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

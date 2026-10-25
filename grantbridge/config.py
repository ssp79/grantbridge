"""Environment and model configuration.

The .env file is looked up in two places, in this order:
  1. the repo root (the folder that holds streamlit_app.py)
  2. the folder above the repo (where the teaching staff keep their .env)
A value from the repo's own .env wins over the parent's. Variables already set
in the shell win over both.

Provider choice:
  - PORTKEY_API_KEY  -> course Portkey gateway, model fixed to gpt-6-luna
  - OPENAI_API_KEY   -> the user's own OpenAI key (used only if no Portkey key,
                        or if GRANTBRIDGE_PROVIDER=openai)

The Portkey base URL and header follow the course examples in
Lectures 11 and 12 (backend/agents/config.py). Secrets are never printed:
Settings hides the key from repr(), and status() reports only where it came from.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[1]

COURSE_MODEL = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"


class ConfigError(RuntimeError):
    """Raised when no usable API key is configured."""


def env_file_candidates(repo_root: Path = REPO_ROOT) -> list[Path]:
    return [repo_root / ".env", repo_root.parent / ".env"]


def read_env_files(repo_root: Path = REPO_ROOT) -> tuple[dict[str, str], dict[str, Path]]:
    """Merge the candidate .env files, earlier files winning.

    Returns (values, sources) where sources maps each key to the file it came from.
    """
    values: dict[str, str] = {}
    sources: dict[str, Path] = {}
    for path in env_file_candidates(repo_root):
        if not path.is_file():
            continue
        for key, value in dotenv_values(path).items():
            if key in values or value is None:
                continue
            values[key] = value.strip().strip("'\"").strip()
            sources[key] = path
    return values, sources


@dataclass(frozen=True)
class Settings:
    provider: str  # "portkey" or "openai"
    model: str
    base_url: str | None
    key_source: str  # human-readable origin of the key, never the key itself
    api_key: str = field(repr=False)

    def client_kwargs(self) -> dict:
        """Keyword arguments for openai.OpenAI(...) or openai.AsyncOpenAI(...)."""
        if self.provider == "portkey":
            return {
                "api_key": self.api_key,
                "base_url": self.base_url,
                "default_headers": {"x-portkey-provider": "openai"},
            }
        kwargs: dict = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return kwargs

    def status(self) -> dict[str, str]:
        """Safe-to-display summary (no secret values)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "key": f"found ({self.key_source})",
        }


def _describe_source(name: str, sources: Mapping[str, Path], repo_root: Path) -> str:
    path = sources.get(name)
    if path is None:
        return "shell environment"
    return "repo .env" if path.parent == repo_root else "parent-folder .env"


def resolve_settings(
    environ: Mapping[str, str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> Settings:
    """Pick the provider and model from the shell environment plus .env files."""
    file_values, sources = read_env_files(repo_root)
    shell = os.environ if environ is None else environ

    def get(name: str) -> str:
        if (shell.get(name) or "").strip():
            return shell[name].strip()
        return file_values.get(name, "")

    def source(name: str) -> str:
        if (shell.get(name) or "").strip():
            return "shell environment"
        return _describe_source(name, sources, repo_root)

    portkey_key = get("PORTKEY_API_KEY")
    openai_key = get("OPENAI_API_KEY")
    preferred = get("GRANTBRIDGE_PROVIDER").lower()

    if preferred == "openai" and not openai_key:
        raise ConfigError("GRANTBRIDGE_PROVIDER=openai but OPENAI_API_KEY is not set.")

    if portkey_key and preferred != "openai":
        return Settings(
            provider="portkey",
            model=COURSE_MODEL,  # the course key may only be used with gpt-6-luna
            base_url=PORTKEY_BASE_URL,
            key_source=source("PORTKEY_API_KEY"),
            api_key=portkey_key,
        )
    if openai_key:
        return Settings(
            provider="openai",
            model=get("OPENAI_MODEL") or COURSE_MODEL,
            base_url=get("OPENAI_BASE_URL") or None,
            key_source=source("OPENAI_API_KEY"),
            api_key=openai_key,
        )

    looked_in = ", ".join(str(p) for p in env_file_candidates(repo_root))
    raise ConfigError(
        "No API key found. Put PORTKEY_API_KEY (or OPENAI_API_KEY) in a .env file "
        f"in the repo folder or the folder above it. Looked in: {looked_in}"
    )


_SECRET_NAME = re.compile(r"(?:KEY|TOKEN|SECRET|PASSWORD)$", re.IGNORECASE)


@lru_cache(maxsize=1)
def known_secrets() -> tuple[str, ...]:
    """Values of every secret-looking setting (…KEY, …TOKEN, …SECRET, …PASSWORD) from the shell and .env files.

    Used only to redact: outputs and logs are scrubbed of these exact strings. Longest first, so a
    secret that contains another is replaced whole. Call known_secrets.cache_clear() after changing them.
    """
    file_values, _ = read_env_files()
    values = set()
    for source in (os.environ, file_values):
        for name, value in source.items():
            value = (value or "").strip().strip("'\"")
            if _SECRET_NAME.search(name) and len(value) >= 8:
                values.add(value)
    return tuple(sorted(values, key=len, reverse=True))

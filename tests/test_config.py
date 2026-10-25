"""Tests for .env resolution and provider selection. No network calls."""

from pathlib import Path

import pytest

from grantbridge.config import COURSE_MODEL, PORTKEY_BASE_URL, ConfigError, resolve_settings

FAKE_KEY = "pk-test-not-a-real-key-123"


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    """submissions/ (parent) containing grantbridge/ (repo), like the grading setup."""
    parent = tmp_path / "submissions"
    repo = parent / "grantbridge"
    repo.mkdir(parents=True)
    return parent, repo


def test_parent_env_is_used_when_repo_has_none(layout):
    parent, repo = layout
    (parent / ".env").write_text(f"PORTKEY_API_KEY={FAKE_KEY}\n")
    s = resolve_settings(environ={}, repo_root=repo)
    assert s.provider == "portkey"
    assert s.api_key == FAKE_KEY
    assert s.key_source == "parent-folder .env"


def test_repo_env_wins_over_parent(layout):
    parent, repo = layout
    (parent / ".env").write_text("PORTKEY_API_KEY=parent-key\n")
    (repo / ".env").write_text("PORTKEY_API_KEY=repo-key\n")
    s = resolve_settings(environ={}, repo_root=repo)
    assert s.api_key == "repo-key"
    assert s.key_source == "repo .env"


def test_shell_environment_wins_over_files(layout):
    parent, repo = layout
    (parent / ".env").write_text("PORTKEY_API_KEY=file-key\n")
    s = resolve_settings(environ={"PORTKEY_API_KEY": "shell-key"}, repo_root=repo)
    assert s.api_key == "shell-key"


def test_quotes_and_whitespace_are_trimmed(layout):
    parent, repo = layout
    (parent / ".env").write_text(f'PORTKEY_API_KEY=  "{FAKE_KEY}"  \n')
    assert resolve_settings(environ={}, repo_root=repo).api_key == FAKE_KEY


def test_portkey_is_locked_to_course_model(layout):
    parent, repo = layout
    (parent / ".env").write_text(f"PORTKEY_API_KEY={FAKE_KEY}\nOPENAI_MODEL=gpt-other\n")
    s = resolve_settings(environ={}, repo_root=repo)
    assert s.model == COURSE_MODEL
    kwargs = s.client_kwargs()
    assert kwargs["base_url"] == PORTKEY_BASE_URL
    assert kwargs["default_headers"] == {"x-portkey-provider": "openai"}


def test_portkey_preferred_when_both_keys_present(layout):
    parent, repo = layout
    (parent / ".env").write_text("PORTKEY_API_KEY=pk\nOPENAI_API_KEY=sk\n")
    assert resolve_settings(environ={}, repo_root=repo).provider == "portkey"


def test_openai_key_used_when_no_portkey(layout):
    parent, repo = layout
    (parent / ".env").write_text("OPENAI_API_KEY=sk-test\nOPENAI_MODEL=my-model\n")
    s = resolve_settings(environ={}, repo_root=repo)
    assert s.provider == "openai"
    assert s.model == "my-model"
    assert "base_url" not in s.client_kwargs()


def test_openai_can_be_forced(layout):
    parent, repo = layout
    (parent / ".env").write_text("PORTKEY_API_KEY=pk\nOPENAI_API_KEY=sk\nGRANTBRIDGE_PROVIDER=openai\n")
    assert resolve_settings(environ={}, repo_root=repo).provider == "openai"


def test_missing_keys_raise_helpful_error(layout):
    _, repo = layout
    with pytest.raises(ConfigError, match="No API key found"):
        resolve_settings(environ={}, repo_root=repo)


def test_secret_never_appears_in_repr_or_status(layout):
    parent, repo = layout
    (parent / ".env").write_text(f"PORTKEY_API_KEY={FAKE_KEY}\n")
    s = resolve_settings(environ={}, repo_root=repo)
    assert FAKE_KEY not in repr(s)
    assert FAKE_KEY not in str(s.status())

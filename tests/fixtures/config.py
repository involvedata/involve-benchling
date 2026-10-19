"""Environment isolation and ``BenchlingConfig`` fixtures."""

from __future__ import annotations

import pytest

from involve_benchling import BenchlingConfig

BASE_URL = "https://example.benchling.com"

ENV_VARS = (
    "BENCHLING_BASE_URL",
    "BENCHLING_API_KEY",
    "BENCHLING_OAUTH_CLIENT_ID",
    "BENCHLING_OAUTH_CLIENT_SECRET",
    "BENCHLING_EARLY_ACCESS",
    "BENCHLING_REGISTRY_NAME",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Removes every ``BENCHLING_*`` variable so a developer's shell cannot leak in."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def api_key_env(clean_env: pytest.MonkeyPatch) -> dict[str, str]:
    """Sets a complete API-key environment and returns it."""
    env = {"BENCHLING_BASE_URL": BASE_URL, "BENCHLING_API_KEY": "sk_env"}
    for name, value in env.items():
        clean_env.setenv(name, value)
    return env


@pytest.fixture
def api_key_config() -> BenchlingConfig:
    return BenchlingConfig(base_url=BASE_URL, api_key="sk_test")


@pytest.fixture
def oauth_config() -> BenchlingConfig:
    return BenchlingConfig(
        base_url=BASE_URL, oauth_client_id="client_id", oauth_client_secret="client_secret"
    )

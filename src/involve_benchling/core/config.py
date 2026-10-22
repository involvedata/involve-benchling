"""Immutable configuration for connecting to Benchling."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any

from ..cache.policy import CachePolicy
from ..errors import ConfigError

_ENV_PREFIX = "BENCHLING_"


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(f"{_ENV_PREFIX}{name}", "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(f"{_ENV_PREFIX}{name}", "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ConfigError(f"{_ENV_PREFIX}{name} must be an integer, got {value!r}") from None


@dataclass(frozen=True)
class BenchlingConfig:
    """Connection settings for a Benchling tenant.

    Authenticate with either an API key or OAuth client credentials.
    All fields are immutable; use :meth:`with_options` to derive variants.
    """

    base_url: str
    api_key: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    early_access: bool = False
    registry_name: str | None = None
    #: Clients built from this config send only reads (see :mod:`~involve_benchling.core.readonly`).
    read_only: bool = False
    #: Clients pause together after a ``429`` (see :mod:`~involve_benchling.core.pacing`).
    pacing: bool = True
    #: Most requests a paced client sends at once.
    max_concurrency: int = 4
    #: How many times a paced client resends a request that got ``429``.
    max_retries: int = 8
    cache: CachePolicy = field(default_factory=CachePolicy)

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ConfigError("base_url is required (e.g. https://yourtenant.benchling.com)")
        has_key = bool(self.api_key)
        has_oauth = bool(self.oauth_client_id and self.oauth_client_secret)
        if not has_key and not has_oauth:
            raise ConfigError(
                "Provide api_key or oauth_client_id + oauth_client_secret "
                f"(or set {_ENV_PREFIX}API_KEY / {_ENV_PREFIX}OAUTH_CLIENT_ID "
                f"and {_ENV_PREFIX}OAUTH_CLIENT_SECRET)."
            )
        if has_key and has_oauth:
            raise ConfigError("Provide api_key or OAuth credentials, not both.")
        if self.max_concurrency < 1:
            raise ConfigError(f"max_concurrency must be at least 1, got {self.max_concurrency}")
        if self.max_retries < 0:
            raise ConfigError(f"max_retries must not be negative, got {self.max_retries}")

    @property
    def auth_method(self) -> str:
        """``"api_key"`` or ``"oauth"``."""
        return "api_key" if self.api_key else "oauth"

    @classmethod
    def from_env(cls, **overrides: Any) -> BenchlingConfig:
        """Build a config from ``BENCHLING_*`` environment variables.

        Recognised variables: ``BENCHLING_BASE_URL``, ``BENCHLING_API_KEY``,
        ``BENCHLING_OAUTH_CLIENT_ID``, ``BENCHLING_OAUTH_CLIENT_SECRET``,
        ``BENCHLING_EARLY_ACCESS``, ``BENCHLING_REGISTRY_NAME``,
        ``BENCHLING_READ_ONLY``, ``BENCHLING_PACING`` (on unless set to a false
        value), ``BENCHLING_MAX_CONCURRENCY``, ``BENCHLING_MAX_RETRIES``.
        Keyword arguments override environment values.
        """
        env: dict[str, Any] = {
            "base_url": os.getenv(f"{_ENV_PREFIX}BASE_URL", ""),
            "api_key": os.getenv(f"{_ENV_PREFIX}API_KEY") or None,
            "oauth_client_id": os.getenv(f"{_ENV_PREFIX}OAUTH_CLIENT_ID") or None,
            "oauth_client_secret": os.getenv(f"{_ENV_PREFIX}OAUTH_CLIENT_SECRET") or None,
            "early_access": _env_flag("EARLY_ACCESS"),
            "registry_name": os.getenv(f"{_ENV_PREFIX}REGISTRY_NAME") or None,
            "read_only": _env_flag("READ_ONLY"),
            "pacing": _env_flag("PACING", default=True),
            "max_concurrency": _env_int("MAX_CONCURRENCY", 4),
            "max_retries": _env_int("MAX_RETRIES", 8),
        }
        env.update(overrides)
        return cls(**env)

    def with_options(self, **changes: Any) -> BenchlingConfig:
        """Return a copy of this config with the given fields replaced."""
        return replace(self, **changes)

"""Construction helpers for ``benchling_v3_sdk`` clients.

:func:`connect` returns a plain ``benchling_v3_sdk.Benchling`` client, and
every helper in this library accepts SDK clients and resources directly.

When ``config.read_only`` is set, the client is built on an ``httpx``
transport that blocks every request that could change tenant data (see
:mod:`~involve_benchling.core.readonly`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import ConfigError
from .config import BenchlingConfig
from .readonly import read_only_async_http_client, read_only_http_client

if TYPE_CHECKING:
    from benchling_v3_sdk import AsyncBenchling, Benchling

#: Request timeout (seconds) for read-only clients, matching the SDK default.
_DEFAULT_TIMEOUT = 60.0


def _client_kwargs(config: BenchlingConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"base_url": config.base_url}
    if config.early_access:
        kwargs["early_access"] = "true"
    if config.api_key:
        kwargs["api_key"] = config.api_key
    else:
        kwargs["client_id"] = config.oauth_client_id
        kwargs["client_secret"] = config.oauth_client_secret
    return kwargs


def _read_only_http_kwargs(extra: dict[str, Any]) -> dict[str, Any]:
    if "httpx_client" in extra:
        raise ConfigError(
            "A read-only config builds its own httpx client; do not pass httpx_client."
        )
    return {
        "timeout": extra.get("timeout") or _DEFAULT_TIMEOUT,
        "follow_redirects": extra.get("follow_redirects", True),
    }


def connect(config: BenchlingConfig, **extra: Any) -> Benchling:
    """Create a synchronous ``benchling_v3_sdk.Benchling`` client.

    Extra keyword arguments (``timeout``, ``max_retries``, ``httpx_client``,
    ...) are forwarded to the SDK constructor.

    Raises:
        ConfigError: ``config.read_only`` is set and ``httpx_client`` was passed.
    """
    from benchling_v3_sdk import Benchling

    if config.read_only:
        http = _read_only_http_kwargs(extra)
        extra["httpx_client"] = read_only_http_client(config.base_url, **http)
    return Benchling(**_client_kwargs(config), **extra)


def connect_async(config: BenchlingConfig, **extra: Any) -> AsyncBenchling:
    """Create an asynchronous ``benchling_v3_sdk.AsyncBenchling`` client.

    Raises:
        ConfigError: ``config.read_only`` is set and ``httpx_client`` was passed.
    """
    from benchling_v3_sdk import AsyncBenchling

    if config.read_only:
        http = _read_only_http_kwargs(extra)
        extra["httpx_client"] = read_only_async_http_client(config.base_url, **http)
    return AsyncBenchling(**_client_kwargs(config), **extra)

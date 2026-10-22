"""Construction helpers for ``benchling_v3_sdk`` clients.

:func:`connect` returns a plain ``benchling_v3_sdk.Benchling`` client, and
every helper in this library accepts SDK clients and resources directly.

The client is built on this library's own ``httpx`` client when either
option below is set:

- ``config.read_only`` blocks every request that could change tenant data
  (see :mod:`~involve_benchling.core.readonly`).
- ``config.pacing`` caps concurrent requests and pauses them together after
  a ``429`` (see :mod:`~involve_benchling.core.pacing`).

The read-only check runs first, so a blocked write never waits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from ..errors import ConfigError
from .config import BenchlingConfig
from .pacing import AsyncPacedTransport, PacedTransport, Pacer, _register
from .readonly import AsyncReadOnlyTransport, ReadOnlyTransport

if TYPE_CHECKING:
    from benchling_v3_sdk import AsyncBenchling, Benchling

#: Request timeout (seconds) for clients built here, matching the SDK default.
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


def _owns_http_client(config: BenchlingConfig) -> bool:
    return config.read_only or config.pacing


def _http_kwargs(extra: dict[str, Any]) -> dict[str, Any]:
    if "httpx_client" in extra:
        raise ConfigError(
            "This config builds its own httpx client for read-only access or pacing; "
            "do not pass httpx_client (set pacing=False to supply your own)."
        )
    return {
        "timeout": extra.get("timeout") or _DEFAULT_TIMEOUT,
        "follow_redirects": extra.get("follow_redirects", True),
    }


def _sync_transport(config: BenchlingConfig) -> tuple[httpx.BaseTransport, Pacer | None]:
    transport: httpx.BaseTransport = httpx.HTTPTransport()
    pacer = Pacer(config.max_concurrency) if config.pacing else None
    if pacer:
        transport = PacedTransport(pacer, transport)
    if config.read_only:
        transport = ReadOnlyTransport(config.base_url, transport)
    return transport, pacer


def _async_transport(
    config: BenchlingConfig,
) -> tuple[httpx.AsyncBaseTransport, Pacer | None]:
    transport: httpx.AsyncBaseTransport = httpx.AsyncHTTPTransport()
    pacer = Pacer(config.max_concurrency) if config.pacing else None
    if pacer:
        transport = AsyncPacedTransport(pacer, transport)
    if config.read_only:
        transport = AsyncReadOnlyTransport(config.base_url, transport)
    return transport, pacer


def connect(config: BenchlingConfig, **extra: Any) -> Benchling:
    """Create a synchronous ``benchling_v3_sdk.Benchling`` client.

    Extra keyword arguments (``timeout``, ``max_retries``, ``httpx_client``,
    ...) are forwarded to the SDK constructor.

    Raises:
        ConfigError: ``httpx_client`` was passed while ``config.read_only`` or
            ``config.pacing`` is set.
    """
    from benchling_v3_sdk import Benchling

    pacer = None
    if _owns_http_client(config):
        http = _http_kwargs(extra)
        transport, pacer = _sync_transport(config)
        extra["httpx_client"] = httpx.Client(transport=transport, **http)
    client = Benchling(**_client_kwargs(config), **extra)
    if pacer:
        _register(client, pacer)
    return client


def connect_async(config: BenchlingConfig, **extra: Any) -> AsyncBenchling:
    """Create an asynchronous ``benchling_v3_sdk.AsyncBenchling`` client.

    Raises:
        ConfigError: ``httpx_client`` was passed while ``config.read_only`` or
            ``config.pacing`` is set.
    """
    from benchling_v3_sdk import AsyncBenchling

    pacer = None
    if _owns_http_client(config):
        http = _http_kwargs(extra)
        transport, pacer = _async_transport(config)
        extra["httpx_client"] = httpx.AsyncClient(transport=transport, **http)
    client = AsyncBenchling(**_client_kwargs(config), **extra)
    if pacer:
        _register(client, pacer)
    return client

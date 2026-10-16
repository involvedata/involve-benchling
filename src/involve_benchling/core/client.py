"""Thin construction helpers over the official ``benchling_v3_sdk``.

involve-benchling never hides the SDK: :func:`connect` returns the plain
``benchling_v3_sdk.Benchling`` client, and every helper in this library
accepts SDK clients and resources directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .config import BenchlingConfig

if TYPE_CHECKING:
    from benchling_v3_sdk import AsyncBenchling, Benchling


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


def connect(config: BenchlingConfig, **extra: Any) -> Benchling:
    """Create a synchronous ``benchling_v3_sdk.Benchling`` client.

    Extra keyword arguments (``timeout``, ``max_retries``, ``httpx_client``,
    ...) are forwarded to the SDK constructor.
    """
    from benchling_v3_sdk import Benchling

    return Benchling(**_client_kwargs(config), **extra)


def connect_async(config: BenchlingConfig, **extra: Any) -> AsyncBenchling:
    """Create an asynchronous ``benchling_v3_sdk.AsyncBenchling`` client."""
    from benchling_v3_sdk import AsyncBenchling

    return AsyncBenchling(**_client_kwargs(config), **extra)

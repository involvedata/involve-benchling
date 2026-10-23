"""Read-only enforcement at the HTTP transport.

A read-only client sends only ``GET``, ``HEAD`` and ``OPTIONS`` requests,
plus ``POST`` to a short list of endpoints that read without changing
tenant data (:data:`READ_POSTS`):

- ``/oauth/token`` issues a credential.
- ``/api/v3/search`` runs a search query.

Any other request raises :class:`~involve_benchling.errors.ReadOnlyViolationError`
before it leaves the process.

The check sits below every SDK method, so it covers raw-response calls and
methods added in future SDK releases without a list of write verbs to
maintain. Build read-only clients with ``BenchlingConfig(read_only=True)``
and :func:`~involve_benchling.connect`; use these helpers directly only when
constructing an ``httpx`` client yourself.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..errors import ReadOnlyViolationError
from .proxy import async_http_transport, http_transport

__all__ = [
    "READ_POSTS",
    "SAFE_METHODS",
    "AsyncReadOnlyTransport",
    "ReadOnlyTransport",
    "read_only_async_http_client",
    "read_only_http_client",
    "token_url",
]

#: HTTP methods a read-only client may send to any URL.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Paths, relative to the tenant base URL, that accept a read-only ``POST``.
READ_POSTS: tuple[str, ...] = ("oauth/token", "api/v3/search")


def _url(base_url: str, path: str) -> httpx.URL:
    return httpx.URL(f"{base_url.rstrip('/')}/{path}")


def token_url(base_url: str) -> httpx.URL:
    """The OAuth token endpoint the SDK posts to for ``base_url``."""
    return _url(base_url, "oauth/token")


def _check(request: httpx.Request, read_posts: frozenset[httpx.URL]) -> None:
    if request.method in SAFE_METHODS:
        return
    url = request.url.copy_with(query=None, fragment=None)
    if request.method == "POST" and url in read_posts:
        return
    raise ReadOnlyViolationError(request.method, str(url))


def _read_posts(base_url: str) -> frozenset[httpx.URL]:
    return frozenset(_url(base_url, path) for path in READ_POSTS)


class ReadOnlyTransport(httpx.BaseTransport):
    """Sync transport that rejects every request a read-only client must not send."""

    def __init__(self, base_url: str, inner: httpx.BaseTransport | None = None) -> None:
        self._read_posts = _read_posts(base_url)
        self._inner = inner or http_transport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        _check(request, self._read_posts)
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


class AsyncReadOnlyTransport(httpx.AsyncBaseTransport):
    """Async counterpart of :class:`ReadOnlyTransport`."""

    def __init__(self, base_url: str, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._read_posts = _read_posts(base_url)
        self._inner = inner or async_http_transport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        _check(request, self._read_posts)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def read_only_http_client(base_url: str, **kwargs: Any) -> httpx.Client:
    """An ``httpx.Client`` whose transport enforces read-only access."""
    kwargs.setdefault("follow_redirects", True)
    return httpx.Client(transport=ReadOnlyTransport(base_url), **kwargs)


def read_only_async_http_client(base_url: str, **kwargs: Any) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` whose transport enforces read-only access."""
    kwargs.setdefault("follow_redirects", True)
    return httpx.AsyncClient(transport=AsyncReadOnlyTransport(base_url), **kwargs)

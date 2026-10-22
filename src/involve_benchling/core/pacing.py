"""Request pacing at the HTTP transport.

Benchling's V3 API rejects requests with ``429`` once a caller's budget is
spent, and asks callers to pause every request on that budget rather than
retry each one on its own. The SDK retries per request, so concurrent calls
keep spending the budget and fail together.

A paced transport fixes this for one client. It does three things:

- It caps how many requests are in flight at once.
- After a ``429`` it holds every request until the pause ends. The pause
  lasts until ``Retry-After`` has passed. Without that header it grows
  exponentially with consecutive ``429`` responses, with jitter, up to
  :data:`MAX_PAUSE` seconds.
- After a ``429`` it halves the cap, down to one request. Each time a full
  cap's worth of requests succeeds, the cap grows by one, back up to
  ``max_concurrency``. A burst of ``429`` responses to requests sent before
  the last cut halves the cap only once.

The SDK still retries, and its retries pass through the same transport, so
they wait out the shared pause too. Clients built by
:func:`~involve_benchling.connect` are paced unless ``config.pacing`` is off;
read a client's :class:`Pacer` with :func:`pacer_for`.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import random
import threading
import time
import weakref
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

__all__ = [
    "MAX_PAUSE",
    "AsyncPacedTransport",
    "PacedTransport",
    "Pacer",
    "pacer_for",
]

logger = logging.getLogger(__name__)

#: Longest pause, in seconds, after a ``429`` without ``Retry-After``.
MAX_PAUSE = 60.0

_pacers: weakref.WeakKeyDictionary[Any, Pacer] = weakref.WeakKeyDictionary()


def pacer_for(client: Any) -> Pacer | None:
    """The :class:`Pacer` of a client built by ``connect()``, or ``None`` if it is unpaced."""
    return _pacers.get(client)


def _register(client: Any, pacer: Pacer) -> None:
    _pacers[client] = pacer


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())


class Pacer:
    """Cap and pause state shared by every request one client sends.

    The pacer is thread-safe. ``clock`` returns monotonic seconds and
    defaults to :func:`time.monotonic`.
    """

    def __init__(
        self,
        max_concurrency: int,
        *,
        clock: Callable[[], float] | None = None,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.max_concurrency = max_concurrency
        self.clock = clock or time.monotonic
        self._jitter = jitter
        self._lock = threading.Lock()
        self._limit = max_concurrency
        self._in_flight = 0
        self._successes = 0
        self._cut_at = float("-inf")
        self._paused_until = 0.0
        self._streak = 0
        self._throttled = 0

    @property
    def limit(self) -> int:
        """How many requests may be in flight now."""
        return self._limit

    @property
    def throttled(self) -> int:
        """How many ``429`` responses this client has received."""
        return self._throttled

    def try_acquire(self) -> bool:
        """Take a request slot if one is free under the current cap."""
        with self._lock:
            if self._in_flight >= self._limit:
                return False
            self._in_flight += 1
            return True

    def release(self) -> None:
        """Return a slot taken by :meth:`try_acquire`."""
        with self._lock:
            self._in_flight -= 1

    def wait_time(self) -> float:
        """Seconds until the current pause ends, or ``0.0`` if there is none."""
        with self._lock:
            return max(0.0, self._paused_until - self.clock())

    def record(
        self, request: httpx.Request, response: httpx.Response, sent_at: float | None = None
    ) -> None:
        """Update the cap and pause from the network's response to ``request``.

        ``sent_at`` is the :attr:`clock` time the request was sent. A ``429``
        to a request sent before the last cut leaves the cap alone.
        """
        with self._lock:
            now = self.clock()
            if response.status_code != 429:
                self._streak = 0
                self._successes += 1
                if self._successes >= self._limit:
                    self._successes = 0
                    self._limit = min(self.max_concurrency, self._limit + 1)
                return
            self._throttled += 1
            self._streak += 1
            self._successes = 0
            if sent_at is None or sent_at >= self._cut_at:
                self._limit = max(1, self._limit // 2)
                self._cut_at = now
            pause = _retry_after(response)
            if pause is None:
                base = min(MAX_PAUSE, 2.0 ** (self._streak - 1))
                pause = base * (0.5 + 0.5 * self._jitter())
            self._paused_until = max(self._paused_until, now + pause)
            limit = self._limit
        logger.warning(
            "Benchling returned 429 for %s %s; pausing requests for %.1fs, cap now %d",
            request.method,
            request.url.path,
            pause,
            limit,
        )


class PacedTransport(httpx.BaseTransport):
    """Sync transport that sends requests through a :class:`Pacer`."""

    def __init__(
        self,
        pacer: Pacer,
        inner: httpx.BaseTransport | None = None,
        *,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.pacer = pacer
        self._inner = inner or httpx.HTTPTransport()
        self._ready = threading.Condition()
        self._sleep = sleep or time.sleep

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        with self._ready:
            while not self.pacer.try_acquire():
                self._ready.wait()
        try:
            while (wait := self.pacer.wait_time()) > 0:
                self._sleep(wait)
            sent_at = self.pacer.clock()
            response = self._inner.handle_request(request)
            self.pacer.record(request, response, sent_at)
            return response
        finally:
            self.pacer.release()
            with self._ready:
                self._ready.notify_all()

    def close(self) -> None:
        self._inner.close()


class AsyncPacedTransport(httpx.AsyncBaseTransport):
    """Async counterpart of :class:`PacedTransport`."""

    def __init__(
        self,
        pacer: Pacer,
        inner: httpx.AsyncBaseTransport | None = None,
        *,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.pacer = pacer
        self._inner = inner or httpx.AsyncHTTPTransport()
        self._ready = asyncio.Condition()
        self._sleep = sleep or asyncio.sleep

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        async with self._ready:
            await self._ready.wait_for(self.pacer.try_acquire)
        try:
            while (wait := self.pacer.wait_time()) > 0:
                await self._sleep(wait)
            sent_at = self.pacer.clock()
            response = await self._inner.handle_async_request(request)
            self.pacer.record(request, response, sent_at)
            return response
        finally:
            self.pacer.release()
            async with self._ready:
                self._ready.notify_all()

    async def aclose(self) -> None:
        await self._inner.aclose()

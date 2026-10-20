"""Typed exception hierarchy for involve-benchling.

Errors raised by this library are always subclasses of
:class:`InvolveBenchlingError`. Errors raised by the underlying
``benchling_v3_sdk`` are passed through untouched.
"""

from __future__ import annotations


class InvolveBenchlingError(Exception):
    """Base class for all involve-benchling errors."""


class ConfigError(InvolveBenchlingError):
    """Raised when configuration is missing or inconsistent."""


class NotFoundError(InvolveBenchlingError):
    """Raised when a lookup matched no items."""

    def __init__(self, resource: str, criteria: dict[str, object]) -> None:
        self.resource = resource
        self.criteria = criteria
        super().__init__(f"No {resource} found matching {criteria!r}")


class AmbiguousError(InvolveBenchlingError):
    """Raised when a lookup expected exactly one item but matched several."""

    def __init__(self, resource: str, criteria: dict[str, object], count: int) -> None:
        self.resource = resource
        self.criteria = criteria
        self.count = count
        super().__init__(f"Expected exactly one {resource} matching {criteria!r}, found {count}")


class CacheError(InvolveBenchlingError):
    """Raised when a cache backend fails irrecoverably."""


class ReadOnlyViolationError(InvolveBenchlingError):
    """Raised when a read-only client attempts a request that could change data."""

    def __init__(self, method: str, url: str) -> None:
        self.method = method
        self.url = url
        super().__init__(f"Read-only client blocked {method} {url}")

"""Cache policy: what to cache, where, and for how long."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: Default TTLs (seconds) per category. Categories are free-form strings;
#: these defaults reflect how often each kind of Benchling data changes.
DEFAULT_TTLS: dict[str, float] = {
    "schema": 24 * 3600,
    "registry": 12 * 3600,
    "dropdown": 12 * 3600,
    "folder": 12 * 3600,
    "project": 12 * 3600,
    "user": 12 * 3600,
    "entity": 3600,
}


@dataclass(frozen=True)
class CachePolicy:
    """Configuration for :class:`~involve_benchling.cache.BenchlingCache`."""

    enabled: bool = True
    #: Directory for the persistent tier. ``None`` disables the disk tier.
    directory: Path | None = Path(".benchling-cache")
    #: Maximum entries held in the in-memory LRU tier.
    max_memory_entries: int = 1024
    #: TTL (seconds) used when a category has no specific TTL.
    default_ttl: float = 3600
    #: Per-category TTL overrides, merged over :data:`DEFAULT_TTLS`.
    ttls: dict[str, float] = field(default_factory=dict)

    def ttl_for(self, category: str) -> float:
        """Resolve the TTL for a category."""
        if category in self.ttls:
            return self.ttls[category]
        return DEFAULT_TTLS.get(category, self.default_ttl)

"""Track resources created during a test and clean them up afterwards."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CleanupError(Exception):
    """Raised when one or more cleanup callbacks failed."""

    def __init__(self, failures: list[tuple[str, Exception]]) -> None:
        self.failures = failures
        lines = "; ".join(f"{desc}: {exc!r}" for desc, exc in failures)
        super().__init__(f"{len(failures)} cleanup step(s) failed: {lines}")


@dataclass
class ResourceTracker:
    """Registers cleanup callbacks and runs them LIFO.

    Tests register whatever they create::

        entity = benchling.custom_entity.create(...)
        benchling_tracker.track(
            f"custom_entity {entity.id}",
            lambda: benchling.custom_entity.update(entity.id, archived=True,
                                                   archive_reason="Made in error"),
        )

    All callbacks run even if earlier ones fail; failures are aggregated
    into a single :class:`CleanupError`.
    """

    _cleanups: list[tuple[str, Callable[[], object]]] = field(default_factory=list)

    def track(self, description: str, cleanup: Callable[[], object]) -> None:
        """Register a cleanup callback for a created resource."""
        self._cleanups.append((description, cleanup))

    def __len__(self) -> int:
        return len(self._cleanups)

    def cleanup(self) -> None:
        """Run all cleanups in reverse order of registration."""
        failures: list[tuple[str, Exception]] = []
        while self._cleanups:
            description, callback = self._cleanups.pop()
            try:
                callback()
                logger.info("cleaned up %s", description)
            except Exception as exc:
                logger.warning("cleanup failed for %s: %r", description, exc)
                failures.append((description, exc))
        if failures:
            raise CleanupError(failures)

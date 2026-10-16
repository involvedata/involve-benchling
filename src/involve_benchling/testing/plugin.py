"""pytest plugin (auto-registered via the ``pytest11`` entry point)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pytest

from ..core.config import BenchlingConfig
from ..errors import ConfigError
from .tracker import ResourceTracker

if TYPE_CHECKING:
    from benchling_v3_sdk import Benchling


def pytest_configure(config: Any) -> None:
    config.addinivalue_line(
        "markers", "integration: tests that hit a real Benchling tenant (require credentials)"
    )


@pytest.fixture(scope="session")
def benchling_config() -> BenchlingConfig:
    """Config from ``BENCHLING_*`` env vars; skips when not configured."""
    if not os.getenv("BENCHLING_BASE_URL"):
        pytest.skip("BENCHLING_BASE_URL not set; skipping Benchling integration test")
    try:
        return BenchlingConfig.from_env()
    except ConfigError as exc:
        pytest.skip(f"Benchling credentials incomplete: {exc}")


@pytest.fixture(scope="session")
def benchling(benchling_config: BenchlingConfig) -> Benchling:
    """A connected synchronous SDK client."""
    from ..core.client import connect

    return connect(benchling_config)


@pytest.fixture
def benchling_tracker() -> Iterator[ResourceTracker]:
    """Tracks created resources and cleans them up after the test."""
    tracker = ResourceTracker()
    yield tracker
    tracker.cleanup()

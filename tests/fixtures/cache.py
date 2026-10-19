"""Clock, cache backend and cache fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from involve_benchling.cache import (
    BenchlingCache,
    CachePolicy,
    DiskBackend,
    MemoryBackend,
    TieredBackend,
    backends,
)

from .fakes import FakeClock


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Freezes cache time. Call ``clock.advance(seconds)`` to expire entries."""
    fake = FakeClock()
    monkeypatch.setattr(backends, "time", fake)
    return fake


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def memory_backend() -> MemoryBackend:
    return MemoryBackend()


@pytest.fixture
def disk_backend(cache_dir: Path) -> DiskBackend:
    return DiskBackend(cache_dir)


@pytest.fixture
def tiered_backend(memory_backend: MemoryBackend, disk_backend: DiskBackend) -> TieredBackend:
    return TieredBackend(memory_backend, disk_backend)


@pytest.fixture
def cache_policy(cache_dir: Path) -> CachePolicy:
    """The default policy, with its disk tier inside the test's temp directory."""
    return CachePolicy(directory=cache_dir)


@pytest.fixture
def memory_cache(memory_backend: MemoryBackend) -> BenchlingCache:
    return BenchlingCache(memory_backend)


@pytest.fixture
def disk_cache(disk_backend: DiskBackend) -> BenchlingCache:
    """A cache backed only by disk, so every value round-trips through JSON."""
    return BenchlingCache(disk_backend)

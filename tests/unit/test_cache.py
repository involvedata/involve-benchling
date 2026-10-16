import time

import pytest
from pydantic import BaseModel

from involve_benchling.cache import (
    MISSING,
    BenchlingCache,
    CachePolicy,
    DiskBackend,
    MemoryBackend,
    TieredBackend,
)


class FakeEntity(BaseModel):
    id: str
    name: str


class TestMemoryBackend:
    def test_roundtrip(self):
        backend = MemoryBackend()
        backend.set("k", {"a": 1}, ttl=60)
        assert backend.get("k") == {"a": 1}

    def test_miss(self):
        assert MemoryBackend().get("nope") is MISSING

    def test_ttl_expiry(self):
        backend = MemoryBackend()
        backend.set("k", 1, ttl=0.01)
        time.sleep(0.02)
        assert backend.get("k") is MISSING

    def test_lru_eviction(self):
        backend = MemoryBackend(max_entries=2)
        backend.set("a", 1, ttl=60)
        backend.set("b", 2, ttl=60)
        backend.get("a")  # refresh a
        backend.set("c", 3, ttl=60)  # evicts b
        assert backend.get("a") == 1
        assert backend.get("b") is MISSING
        assert backend.get("c") == 3

    def test_invalidate_prefix(self):
        backend = MemoryBackend()
        backend.set("schema:1", 1, ttl=60)
        backend.set("schema:2", 2, ttl=60)
        backend.set("entity:1", 3, ttl=60)
        assert backend.invalidate("schema:") == 2
        assert backend.get("entity:1") == 3


class TestDiskBackend:
    def test_roundtrip(self, tmp_path):
        backend = DiskBackend(tmp_path)
        backend.set("k", {"a": 1}, ttl=60)
        assert backend.get("k") == {"a": 1}

    def test_persists_across_instances(self, tmp_path):
        DiskBackend(tmp_path).set("k", "v", ttl=60)
        assert DiskBackend(tmp_path).get("k") == "v"

    def test_expiry(self, tmp_path):
        backend = DiskBackend(tmp_path)
        backend.set("k", "v", ttl=-1)
        assert backend.get("k") is MISSING

    def test_corrupt_entry_is_miss(self, tmp_path):
        backend = DiskBackend(tmp_path)
        backend.set("k", "v", ttl=60)
        for path in (tmp_path / "entries").glob("*.json"):
            path.write_text("{corrupt")
        assert backend.get("k") is MISSING

    def test_invalidate_prefix(self, tmp_path):
        backend = DiskBackend(tmp_path)
        backend.set("schema:1", 1, ttl=60)
        backend.set("entity:1", 2, ttl=60)
        assert backend.invalidate("schema:") == 1
        assert backend.get("entity:1") == 2


class TestTieredBackend:
    def test_disk_hit_warms_memory(self, tmp_path):
        memory = MemoryBackend()
        disk = DiskBackend(tmp_path)
        tiered = TieredBackend(memory, disk)
        disk.set("k", "v", ttl=60)
        assert tiered.get("k") == "v"
        assert memory.get("k") == "v"


class TestBenchlingCache:
    def test_fetch_once_then_hit(self):
        cache = BenchlingCache(MemoryBackend())
        calls = []

        def fetch():
            calls.append(1)
            return {"x": 1}

        assert cache.get_or_fetch("k", fetch=fetch) == {"x": 1}
        assert cache.get_or_fetch("k", fetch=fetch) == {"x": 1}
        assert len(calls) == 1
        assert cache.hits == 1 and cache.misses == 1
        assert cache.hit_rate == 0.5

    def test_pydantic_model_roundtrip(self, tmp_path):
        # Through the DISK tier: proves JSON serialisation, no pickle.
        cache = BenchlingCache(DiskBackend(tmp_path))
        entity = FakeEntity(id="ent_1", name="pIVD-001")
        cache.get_or_fetch("e", fetch=lambda: entity)

        restored = BenchlingCache(DiskBackend(tmp_path)).get_or_fetch(
            "e", fetch=lambda: pytest.fail("should have been cached")
        )
        assert isinstance(restored, FakeEntity)
        assert restored == entity

    def test_model_list_roundtrip(self, tmp_path):
        cache = BenchlingCache(DiskBackend(tmp_path))
        entities = [FakeEntity(id=f"ent_{i}", name=f"E{i}") for i in range(3)]
        cache.get_or_fetch("es", fetch=lambda: entities)
        restored = BenchlingCache(DiskBackend(tmp_path)).get_or_fetch(
            "es", fetch=lambda: pytest.fail("should have been cached")
        )
        assert restored == entities

    def test_disabled_policy_always_fetches(self):
        cache = BenchlingCache(MemoryBackend(), CachePolicy(enabled=False))
        calls = []
        cache.get_or_fetch("k", fetch=lambda: calls.append(1))
        cache.get_or_fetch("k", fetch=lambda: calls.append(1))
        assert len(calls) == 2

    def test_category_ttl_resolution(self):
        policy = CachePolicy(ttls={"schema": 123.0})
        assert policy.ttl_for("schema") == 123.0
        assert policy.ttl_for("registry") == 12 * 3600  # default table
        assert policy.ttl_for("unknown") == policy.default_ttl

    def test_from_policy_no_disk(self):
        cache = BenchlingCache.from_policy(CachePolicy(directory=None))
        cache.get_or_fetch("k", fetch=lambda: 1)
        assert cache.get_or_fetch("k", fetch=lambda: 2) == 1

    def test_namespace_isolation(self, tmp_path):
        policy = CachePolicy(directory=tmp_path)
        a = BenchlingCache.from_policy(policy, namespace="https://a.benchling.com")
        b = BenchlingCache.from_policy(policy, namespace="https://b.benchling.com")
        a.get_or_fetch("k", fetch=lambda: "from-a")
        assert b.get_or_fetch("k", fetch=lambda: "from-b") == "from-b"

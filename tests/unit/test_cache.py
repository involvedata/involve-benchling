import pytest
from benchling_v3_sdk.types.custom_entity import CustomEntity

from involve_benchling.cache import (
    MISSING,
    BenchlingCache,
    CachePolicy,
    DiskBackend,
    MemoryBackend,
)


def _never():
    pytest.fail("should have been served from the cache")


class TestMemoryBackend:
    def test_roundtrip(self, memory_backend):
        memory_backend.set("k", {"a": 1}, ttl=60)
        assert memory_backend.get("k") == {"a": 1}

    def test_miss(self, memory_backend):
        assert memory_backend.get("nope") is MISSING

    def test_ttl_expiry(self, memory_backend, clock):
        memory_backend.set("k", 1, ttl=60)
        clock.advance(59)
        assert memory_backend.get("k") == 1
        clock.advance(1)
        assert memory_backend.get("k") is MISSING

    def test_lru_eviction(self):
        backend = MemoryBackend(max_entries=2)
        backend.set("a", 1, ttl=60)
        backend.set("b", 2, ttl=60)
        backend.get("a")  # refresh a
        backend.set("c", 3, ttl=60)  # evicts b
        assert backend.get("a") == 1
        assert backend.get("b") is MISSING
        assert backend.get("c") == 3

    def test_invalidate_prefix(self, memory_backend):
        memory_backend.set("schema:1", 1, ttl=60)
        memory_backend.set("schema:2", 2, ttl=60)
        memory_backend.set("entity:1", 3, ttl=60)
        assert memory_backend.invalidate("schema:") == 2
        assert memory_backend.get("entity:1") == 3


class TestDiskBackend:
    def test_roundtrip(self, disk_backend):
        disk_backend.set("k", {"a": 1}, ttl=60)
        assert disk_backend.get("k") == {"a": 1}

    def test_persists_across_instances(self, disk_backend, cache_dir):
        disk_backend.set("k", "v", ttl=60)
        assert DiskBackend(cache_dir).get("k") == "v"

    def test_ttl_expiry(self, disk_backend, clock):
        disk_backend.set("k", "v", ttl=60)
        clock.advance(60)
        assert disk_backend.get("k") is MISSING

    def test_corrupt_entry_is_miss(self, disk_backend, cache_dir):
        disk_backend.set("k", "v", ttl=60)
        for path in (cache_dir / "entries").glob("*.json"):
            path.write_text("{corrupt")
        assert disk_backend.get("k") is MISSING

    def test_invalidate_prefix(self, disk_backend):
        disk_backend.set("schema:1", 1, ttl=60)
        disk_backend.set("entity:1", 2, ttl=60)
        assert disk_backend.invalidate("schema:") == 1
        assert disk_backend.get("entity:1") == 2


class TestTieredBackend:
    def test_disk_hit_warms_memory(self, tiered_backend, memory_backend, disk_backend):
        disk_backend.set("k", "v", ttl=60)
        assert tiered_backend.get("k") == "v"
        assert memory_backend.get("k") == "v"

    def test_invalidate_clears_both_tiers(self, tiered_backend, memory_backend, disk_backend):
        tiered_backend.set("k", "v", ttl=60)
        tiered_backend.invalidate("k")
        assert memory_backend.get("k") is MISSING
        assert disk_backend.get("k") is MISSING


class TestBenchlingCache:
    def test_fetch_once_then_hit(self, memory_cache):
        calls = []

        def fetch():
            calls.append(1)
            return {"x": 1}

        assert memory_cache.get_or_fetch("k", fetch=fetch) == {"x": 1}
        assert memory_cache.get_or_fetch("k", fetch=fetch) == {"x": 1}
        assert len(calls) == 1
        assert memory_cache.hits == 1 and memory_cache.misses == 1
        assert memory_cache.hit_rate == 0.5

    def test_sdk_model_roundtrip(self, disk_cache, disk_backend, plasmids):
        # Through the disk tier, so the model survives JSON serialisation.
        disk_cache.get_or_fetch("e", fetch=lambda: plasmids[0])
        restored = BenchlingCache(disk_backend).get_or_fetch("e", fetch=_never)
        assert isinstance(restored, CustomEntity)
        assert restored == plasmids[0]

    def test_sdk_model_list_roundtrip(self, disk_cache, disk_backend, plasmids):
        disk_cache.get_or_fetch("es", fetch=lambda: plasmids)
        assert BenchlingCache(disk_backend).get_or_fetch("es", fetch=_never) == plasmids

    def test_category_ttl_applies(self, memory_backend, clock):
        cache = BenchlingCache(memory_backend, CachePolicy(ttls={"schema": 10}))
        cache.get_or_fetch("k", category="schema", fetch=lambda: "old")
        clock.advance(10)
        assert cache.get_or_fetch("k", category="schema", fetch=lambda: "new") == "new"

    def test_disabled_policy_always_fetches(self, memory_backend):
        cache = BenchlingCache(memory_backend, CachePolicy(enabled=False))
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

    def test_namespace_isolation(self, cache_policy):
        a = BenchlingCache.from_policy(cache_policy, namespace="https://a.benchling.com")
        b = BenchlingCache.from_policy(cache_policy, namespace="https://b.benchling.com")
        a.get_or_fetch("k", fetch=lambda: "from-a")
        assert b.get_or_fetch("k", fetch=lambda: "from-b") == "from-b"

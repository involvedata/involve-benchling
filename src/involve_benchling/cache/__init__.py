"""Caching for Benchling API responses.

The official SDK does no caching; reference data (schemas, dropdowns,
registries, users) rarely changes but is fetched constantly. A
:class:`BenchlingCache` turns those ~500ms calls into sub-millisecond
lookups.

Values round-trip through JSON (never pickle). Benchling SDK models are
Pydantic models and are serialised losslessly::

    from involve_benchling.cache import BenchlingCache
    from benchling_v3_sdk.types.custom_entity import CustomEntity

    cache = BenchlingCache.from_policy(policy, namespace=config.base_url)

    entities = cache.get_or_fetch(
        "entities:by-schema:ts_abc123",
        category="entity",
        model=CustomEntity,
        fetch=lambda: list(benchling.custom_entity.list(schema_eq="ts_abc123")),
    )

    # after a write:
    cache.invalidate("entities:")
"""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from .backends import MISSING, CacheBackend, DiskBackend, MemoryBackend, TieredBackend
from .policy import DEFAULT_TTLS, CachePolicy

__all__ = [
    "DEFAULT_TTLS",
    "MISSING",
    "BenchlingCache",
    "CacheBackend",
    "CachePolicy",
    "DiskBackend",
    "MemoryBackend",
    "TieredBackend",
]

M = TypeVar("M", bound=BaseModel)


def _encode(value: Any) -> Any:
    """Encode a value (possibly a Pydantic model or list of them) to JSON-safe form."""
    if isinstance(value, BaseModel):
        return {"__model__": _model_ref(type(value)), "data": value.model_dump_json()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {"__list__": [_encode(item) for item in value]}
    return {"__json__": value}


def _decode(doc: Any) -> Any:
    if not isinstance(doc, dict):
        return doc
    if "__model__" in doc:
        model_cls = _import_model(doc["__model__"])
        return model_cls.model_validate_json(doc["data"])
    if "__list__" in doc:
        return [_decode(item) for item in doc["__list__"]]
    return doc.get("__json__")


def _model_ref(cls: type[BaseModel]) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def _import_model(ref: str) -> type[BaseModel]:
    module_name, _, qualname = ref.partition(":")
    obj: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
        raise TypeError(f"{ref} is not a Pydantic model")
    return obj


class BenchlingCache:
    """High-level cache facade with stats and model-aware serialisation."""

    def __init__(self, backend: CacheBackend, policy: CachePolicy | None = None) -> None:
        self._backend = backend
        self._policy = policy or CachePolicy()
        self.hits = 0
        self.misses = 0

    @classmethod
    def from_policy(cls, policy: CachePolicy, *, namespace: str = "") -> BenchlingCache:
        """Build the standard tiered cache described by ``policy``.

        ``namespace`` (typically the tenant base URL) isolates cache
        directories between tenants.
        """
        memory = MemoryBackend(policy.max_memory_entries)
        if policy.directory is None:
            return cls(memory, policy)
        subdir = hashlib.sha256(namespace.encode()).hexdigest()[:12] if namespace else "default"
        disk = DiskBackend(policy.directory / subdir)
        return cls(TieredBackend(memory, disk), policy)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def get_or_fetch(
        self,
        key: str,
        *,
        fetch: Callable[[], Any],
        category: str = "",
        ttl: float | None = None,
        model: type[BaseModel] | None = None,
    ) -> Any:
        """Return the cached value for ``key``, calling ``fetch`` on a miss.

        ``ttl`` overrides the policy TTL for ``category``. ``model`` is
        accepted for documentation/typing symmetry; rehydration is driven
        by metadata stored alongside the value.
        """
        if not self._policy.enabled:
            return fetch()
        doc = self._backend.get(key)
        if doc is not MISSING:
            self.hits += 1
            return _decode(doc)
        self.misses += 1
        value = fetch()
        resolved_ttl = ttl if ttl is not None else self._policy.ttl_for(category)
        self._backend.set(key, _encode(value), resolved_ttl)
        return value

    def invalidate(self, prefix: str = "") -> int:
        """Drop every entry whose key starts with ``prefix``. Returns the count."""
        return self._backend.invalidate(prefix)

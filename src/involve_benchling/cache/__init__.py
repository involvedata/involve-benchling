"""Caching for Benchling API responses.

Reference data (schemas, dropdowns, registries, users) changes rarely but
is often read many times. A :class:`BenchlingCache` keeps those responses
locally, so repeat lookups take under a millisecond.

Values round-trip through JSON (never pickle). Benchling SDK models are
Pydantic models and are serialised losslessly. A cached model is rebuilt
only from a ``benchling_v3_sdk`` class or the ``model`` passed to
:meth:`BenchlingCache.get_or_fetch`, so a tampered cache file cannot make
the cache import arbitrary modules::

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


def _decode(doc: Any, model: type[BaseModel] | None = None) -> Any:
    if not isinstance(doc, dict):
        return doc
    if "__model__" in doc:
        ref = doc["__model__"]
        model_cls = model if model and ref == _model_ref(model) else _import_model(ref)
        return model_cls.model_validate_json(doc["data"])
    if "__list__" in doc:
        return [_decode(item, model) for item in doc["__list__"]]
    return doc.get("__json__")


def _model_ref(cls: type[BaseModel]) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


#: Packages whose models the cache imports by name when rehydrating.
_TRUSTED_MODEL_PACKAGES = ("benchling_v3_sdk",)


def _import_model(ref: str) -> type[BaseModel]:
    module_name, _, qualname = ref.partition(":")
    if module_name.partition(".")[0] not in _TRUSTED_MODEL_PACKAGES:
        raise TypeError(f"{ref} is not a Benchling SDK model; pass it as model=")
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

        ``ttl`` overrides the policy TTL for ``category``. ``model`` names a
        Pydantic class outside ``benchling_v3_sdk`` that the cached value may
        hold; SDK models need no ``model``. An entry that cannot be decoded
        counts as a miss.
        """
        if not self._policy.enabled:
            return fetch()
        doc = self._backend.get(key)
        if doc is not MISSING:
            try:
                value = _decode(doc, model)
            except (ImportError, AttributeError, TypeError, ValueError):
                pass
            else:
                self.hits += 1
                return value
        self.misses += 1
        value = fetch()
        resolved_ttl = ttl if ttl is not None else self._policy.ttl_for(category)
        self._backend.set(key, _encode(value), resolved_ttl)
        return value

    def invalidate(self, prefix: str = "") -> int:
        """Drop every entry whose key starts with ``prefix``. Returns the count."""
        return self._backend.invalidate(prefix)

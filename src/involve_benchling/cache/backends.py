"""Cache backends.

Values are stored as JSON documents, never pickle. Pydantic models from
the Benchling SDK are serialised with ``model_dump_json`` and rehydrated
with ``model_validate_json``.

The disk tier creates its directory and files readable only by the current
user, because cached responses can hold sensitive tenant data.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover
        return "<MISSING>"


#: Sentinel returned by :meth:`CacheBackend.get` on a miss.
MISSING: Any = _Missing()


@runtime_checkable
class CacheBackend(Protocol):
    """Minimal interface a cache backend must implement.

    Values are JSON-serialisable documents (dict/list/str/num/bool/None).
    """

    def get(self, key: str) -> Any: ...

    def set(self, key: str, value: Any, ttl: float) -> None: ...

    def invalidate(self, prefix: str = "") -> int: ...


class MemoryBackend:
    """In-process LRU cache with per-entry TTL."""

    def __init__(self, max_entries: int = 1024) -> None:
        self._max = max_entries
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any:
        entry = self._data.get(key)
        if entry is None:
            return MISSING
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._data[key]
            return MISSING
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        self._data[key] = (time.monotonic() + ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def invalidate(self, prefix: str = "") -> int:
        keys = [k for k in self._data if k.startswith(prefix)]
        for k in keys:
            del self._data[k]
        return len(keys)


class DiskBackend:
    """Persistent cache: one JSON file per key, shared across processes.

    Writes are atomic (write to a unique temp file, then rename). Corrupt or
    unreadable entries are treated as misses, never as errors. The directory
    holds a ``.gitignore`` so a cache inside a repository is never committed.
    """

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._index_dir = directory / "entries"
        self._index_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        gitignore = directory / ".gitignore"
        if not gitignore.exists():
            with contextlib.suppress(OSError):
                gitignore.write_text("*\n")

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:40]
        return self._index_dir / f"{digest}.json"

    def get(self, key: str) -> Any:
        path = self._path(key)
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            return MISSING
        if doc.get("key") != key or time.time() >= doc.get("expires_at", 0):
            return MISSING
        return doc.get("value")

    def set(self, key: str, value: Any, ttl: float) -> None:
        path = self._path(key)
        doc = {"key": key, "expires_at": time.time() + ttl, "value": value}
        try:
            # mkstemp creates the file with mode 0600.
            fd, tmp_name = tempfile.mkstemp(dir=self._index_dir, suffix=".tmp")
        except OSError:
            return
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(doc))
            tmp.replace(path)
        except OSError:
            # Cache failures must never break the caller.
            tmp.unlink(missing_ok=True)

    def invalidate(self, prefix: str = "") -> int:
        count = 0
        for path in self._index_dir.glob("*.json"):
            try:
                doc = json.loads(path.read_text())
            except (OSError, ValueError):
                path.unlink(missing_ok=True)
                continue
            if doc.get("key", "").startswith(prefix):
                path.unlink(missing_ok=True)
                count += 1
        return count


class TieredBackend:
    """Memory tier in front of a persistent tier."""

    def __init__(self, memory: MemoryBackend, disk: DiskBackend) -> None:
        self._memory = memory
        self._disk = disk

    def get(self, key: str) -> Any:
        value = self._memory.get(key)
        if value is not MISSING:
            return value
        value = self._disk.get(key)
        if value is not MISSING:
            # Re-warm the memory tier; TTL is enforced by the disk doc,
            # so a short memory TTL keeps the tiers close.
            self._memory.set(key, value, ttl=60)
        return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        self._memory.set(key, value, ttl)
        self._disk.set(key, value, ttl)

    def invalidate(self, prefix: str = "") -> int:
        self._memory.invalidate(prefix)
        return self._disk.invalidate(prefix)

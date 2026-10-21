"""involve-benchling: an extension of Benchling's V3 Python SDK.

Helpers that work alongside ``benchling_v3_sdk`` and accept and return its
models:

- :mod:`involve_benchling.cache` -- tiered, pickle-free response caching.
- :mod:`involve_benchling.resolve` -- generic name->object resolution with
  typed errors, over any V3 resource.
- :mod:`involve_benchling.dataframes` -- pandas adapters (optional extra).
- :mod:`involve_benchling.testing` -- pytest fixtures and resource cleanup.
- :mod:`involve_benchling.tools` -- cross-resource workflows (roadmap).

Quick start::

    from involve_benchling import BenchlingConfig, connect, resolve

    config = BenchlingConfig.from_env()
    benchling = connect(config)
    plasmid = resolve.get_by_name(benchling.custom_entity, "pEX-001")
"""

from . import resolve
from .cache import BenchlingCache, CachePolicy
from .core import BenchlingConfig, connect, connect_async
from .errors import (
    AmbiguousError,
    CacheError,
    ConfigError,
    InvolveBenchlingError,
    NotFoundError,
    ReadOnlyViolationError,
)
from .version import __version__

__all__ = [
    "AmbiguousError",
    "BenchlingCache",
    "BenchlingConfig",
    "CacheError",
    "CachePolicy",
    "ConfigError",
    "InvolveBenchlingError",
    "NotFoundError",
    "ReadOnlyViolationError",
    "__version__",
    "connect",
    "connect_async",
    "resolve",
]

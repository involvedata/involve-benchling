"""Shared test fixtures for involve-benchling.

Helper modules (import directly in tests):

- ``builders``: V3 wire-format payloads and real SDK models.
- ``fakes``: in-memory stand-ins for SDK resource clients and the clock.

Fixture modules (registered by ``tests/conftest.py``):

- ``config``: environment isolation and ``BenchlingConfig`` instances.
- ``cache``: a controllable clock, cache backends and caches.
- ``tenant``: a small canned tenant (plasmid schema, entities, resources).
"""

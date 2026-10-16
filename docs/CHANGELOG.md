# Changelog

## 0.1.0 (unreleased)

Initial scaffold.

- `core`: `BenchlingConfig` (API key / OAuth, env loading) and
  `connect()` / `connect_async()` over `benchling-v3-sdk-python`.
- `cache`: tiered memory+disk cache, JSON-only serialisation of Pydantic
  SDK models, per-category TTL policy, prefix invalidation.
- `resolve`: generic `find_all` / `find_one` / `get_by_name` /
  `get_id_by_name` with `NotFoundError` / `AmbiguousError`.
- `dataframes` (extra): `to_dataframe()` with Benchling fields expansion.
- `testing`: pytest plugin (`benchling_config`, `benchling`,
  `benchling_tracker` fixtures) and `ResourceTracker`.

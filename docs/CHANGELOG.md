# Changelog

## 0.1.0 (unreleased)

Initial scaffold.

- `core`: `BenchlingConfig` (API key / OAuth, env loading) and
  `connect()` / `connect_async()` over `benchling-v3-sdk-python`.
- `cache`: tiered memory+disk cache, JSON-only serialisation of Pydantic
  SDK models, per-category TTL policy, prefix invalidation.
- `resolve`: generic `find_all` / `find_one` / `get_by_name` /
  `get_id_by_name` with `NotFoundError` / `AmbiguousError`.
- `dataframes` (extra): `to_dataframe()` expands V3 `schemaFields` into
  typed columns; `field_names()` maps field definition IDs to names.
- Tests: shared fixtures in `tests/fixtures/` (V3 payload builders, fake
  resources, a frozen cache clock, a canned plasmid tenant).
- `testing`: pytest plugin (`benchling_config`, `benchling`,
  `benchling_tracker` fixtures) and `ResourceTracker`.

# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## 0.1.0a1 (unreleased)

### Added

- `core`: `BenchlingConfig` (API key or OAuth, loaded from `BENCHLING_*`
  environment variables) and `connect()` / `connect_async()` over
  `benchling-v3-sdk-python`.
- `core`: read-only clients. `BenchlingConfig(read_only=True)` (or
  `BENCHLING_READ_ONLY=1`) builds the SDK on an `httpx` transport that sends
  only `GET` / `HEAD` / `OPTIONS`, plus `POST` to the OAuth token exchange and
  `/api/v3/search`. Anything else raises `ReadOnlyViolationError` before it
  leaves the process.
- `cache`: tiered memory and disk cache, JSON-only serialisation of Pydantic
  SDK models, per-category TTL policy, prefix invalidation. The disk tier
  writes owner-only files and a `.gitignore`, and rebuilds only
  `benchling_v3_sdk` models or the `model` passed to `get_or_fetch`.
- `resolve`: generic `find_all` / `find_one` / `get_by_name` /
  `get_id_by_name` with `NotFoundError` / `AmbiguousError`.
- `dataframes` (extra): `to_dataframe()` expands V3 `schemaFields` into typed
  columns; `field_names()` maps field definition IDs to names.
- `testing`: pytest plugin (`benchling_config`, `benchling`,
  `benchling_tracker` fixtures) and `ResourceTracker`.

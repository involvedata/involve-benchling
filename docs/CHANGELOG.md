# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## 0.1.2 (2026-10-23)

### Added

- `core.proxy`: `http_transport()` and `async_http_transport()` build network
  transports that honour `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and
  `NO_PROXY` the way httpx does. `ProxyTransport` and `AsyncProxyTransport`
  route each request direct or through its proxy.

### Fixed

- Clients built by `connect()` / `connect_async()` now use the proxy
  environment variables. In 0.1.1 read-only and paced clients sent every
  request direct, so they failed in proxied sandboxes with what looked like
  a DNS error. The read-only check still runs before any proxy is
  contacted, and proxied and direct requests share one pacer. The
  `read_only_http_client()` helpers and transports built without an
  `inner` transport get the same fix.

## 0.1.1 (2026-10-22)

### Added

- `core.pacing`: a shared rate limit alongside the concurrency cap. Requests
  are spaced to a rate that starts at 10 requests/s, halves on a `429`
  (down to 0.5) and rises by 0.1 requests/s per success (up to 20).
  `Pacer.rate` reports it.
- `BenchlingConfig.max_retries` (default 8, or `BENCHLING_MAX_RETRIES`): a
  paced client resends a request that got a `429` up to this many times,
  for every method. A negative value raises `ConfigError`.

### Fixed

- Large crawls no longer fail on `429 Budget rate limit hit`. In 0.1.0 a
  cap of one request in flight still allowed fast back-to-back requests,
  and the SDK gave up after 2 retries.

## 0.1.0 (2026-10-22)

### Added

- `core.pacing`: clients built by `connect()` / `connect_async()` cap
  concurrent requests (`BenchlingConfig.max_concurrency`, default 4, or
  `BENCHLING_MAX_CONCURRENCY`). After a `429` they pause every request until
  `Retry-After` has passed, or back off exponentially with jitter up to 60 s
  without it. Each `429` also halves the cap, which grows back by one after
  each full cap's worth of successes. SDK retries wait out the same pause.
  `pacer_for(client)` returns the client's `Pacer`, and each `429` is logged
  at `WARNING`.
- `BenchlingConfig.pacing` (default on, or `BENCHLING_PACING=0`) turns
  pacing off.

### Changed

- Clients are paced by default, so at most 4 requests are in flight per
  client unless `max_concurrency` is raised.
- `connect()` raises `ConfigError` when `httpx_client` is passed while
  pacing is on. Set `pacing=False` to supply your own client.

## 0.1.0a2 (2026-10-21)

### Changed

- Releases are published to PyPI from GitHub Actions through trusted
  publishing. The library itself is unchanged.

## 0.1.0a1 (2026-10-21)

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

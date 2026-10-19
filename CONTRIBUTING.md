# Contributing

(Private alpha — this document will be expanded before the public release.)

## Ground rules

- **Pass through SDK models** — never introduce wrapper dataclasses for
  Benchling resources.
- **Generic over bespoke** — prefer helpers that work on any resource to
  per-resource code.
- **Every public function is typed and documented.** CI runs mypy
  `--strict` and ruff.
- **Unit tests must run with zero credentials.** Anything touching a real
  tenant is `@pytest.mark.integration`.

## Workflow

```bash
make install     # editable install with dev extras
make lint type test
```

PRs need: passing CI, a test for every behaviour change, and a changelog
entry under `docs/CHANGELOG.md`.

## Test fixtures

Shared fixtures live in `tests/fixtures/` and are registered by
`tests/conftest.py`. Use them instead of defining fakes inside test files.

| Module | Provides |
|---|---|
| `builders` | V3 wire-format payloads (`text_value`, `link_value`, `custom_entity_payload`, ...) and real SDK models built from them (`custom_entity`, `field_definitions`) |
| `fakes` | `FakeResource` (applies `name_any_of`, `id_any_of`, `schema_eq` and records calls), `UnfilteredResource`, `FakeSchemaResource`, `FakeClock` |
| `config` | `clean_env`, `api_key_env`, `api_key_config`, `oauth_config` |
| `cache` | `clock` (freezes cache time; `clock.advance(s)` expires entries), `cache_dir`, `memory_backend`, `disk_backend`, `tiered_backend`, `cache_policy`, `memory_cache`, `disk_cache` |
| `tenant` | A canned plasmid tenant: `plasmid_field_definitions`, `plasmids`, `entity_resource`, `unfiltered_resource`, `schema_resource` |

Unit tests run with every `BENCHLING_*` variable removed
(`tests/unit/conftest.py`). Use `clock` rather than `time.sleep` for TTL
tests.

These fixtures are private to this repo. The shipped
`involve_benchling.testing` plugin provides the live-tenant fixtures
(`benchling_config`, `benchling`, `benchling_tracker`) for integration tests.

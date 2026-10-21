# Contributing

Thanks for helping. Bug reports, fixes and new helpers are all welcome. For a
larger change, open an issue first so we can agree on the shape before you
write it.

## Ground rules

- **Pass through SDK models.** Never introduce wrapper dataclasses for
  Benchling resources.
- **Generic over bespoke.** Prefer helpers that work on any resource to
  per-resource code.
- **Every public function is typed and documented.** CI runs mypy
  `--strict` and ruff.
- **Unit tests run with zero credentials.** Anything touching a real
  tenant is marked `@pytest.mark.integration`.
- **Optional dependencies stay optional.** Import them inside the function
  that needs them and declare them as an extra in `pyproject.toml`.

## Setup

```bash
python -m venv venv && source venv/bin/activate
make install          # pip install -e ".[dev]"
pre-commit install    # optional: ruff and file checks on every commit
```

## Checks

```bash
make lint             # ruff check and ruff format --check
make type             # mypy --strict
make test             # unit tests, no credentials needed
make test-all         # unit and integration tests
```

Integration tests need a tenant. Copy `.test.env.template` to `.test.env`
and fill it in. Use a sandbox tenant, because the tests create and archive
resources.

## Pull requests

A pull request needs:

- passing CI
- a test for every behaviour change
- an entry under `docs/CHANGELOG.md`
- docstrings for any new public function

Keep each pull request to one change.

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

## Security

Report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).

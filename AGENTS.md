# Agent guide

Instructions for AI coding agents working in this repository. Human
contributors should read [CONTRIBUTING.md](CONTRIBUTING.md), which this file
follows.

## Project

involve-benchling is a typed Python library over `benchling-v3-sdk-python`.
It adds caching, name resolution, dataframes, read-only clients and pytest
utilities, and it never hides the SDK. Functions accept and return SDK
objects.

| Path | Contents |
|---|---|
| `src/involve_benchling/core/` | `BenchlingConfig`, `connect()`, the read-only `httpx` transport |
| `src/involve_benchling/cache/` | Cache facade, policy, memory and disk backends |
| `src/involve_benchling/resolve/` | Generic lookups over any `list` resource |
| `src/involve_benchling/dataframes.py` | pandas adapters (optional extra) |
| `src/involve_benchling/testing/` | pytest plugin and `ResourceTracker` |
| `tests/fixtures/` | Shared fakes, builders and a canned tenant |
| `docs/design/` | Design documents for planned modules |

## Commands

```bash
make install   # editable install with dev extras
make lint      # ruff
make type      # mypy --strict
make test      # unit tests; no credentials
```

Run `make lint type test` before you finish. All three must pass.

## Rules

- Pass SDK models through. Don't add wrapper dataclasses for Benchling
  resources.
- Keep helpers generic over resources rather than writing one per resource.
- Type and document every public function. mypy runs in strict mode.
- Never use pickle. Cached values are JSON.
- Core depends only on the SDK, `httpx` and `pydantic`. Anything else is an
  optional extra imported inside the function that needs it.
- Unit tests must not touch the network or need credentials. Use the
  fixtures in `tests/fixtures/` instead of new fakes.
- Mark tests that need a tenant `@pytest.mark.integration`. Never run them
  unless asked, because they write to the tenant.
- Add a `docs/CHANGELOG.md` entry for every user-visible change.
- Never commit `.test.env`, credentials, tenant URLs or data from a real
  tenant. Examples use `example.benchling.com`.

## Style

- Line length is 100. Ruff formats the code.
- Write docstrings in plain present tense, saying what the function does.
- Keep comments short and about current behaviour.

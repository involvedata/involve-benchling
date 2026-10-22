# involve-benchling

An extension of Benchling's [`benchling-v3-sdk-python`](https://pypi.org/project/benchling-v3-sdk-python/)
for teams building integrations and analysis on Benchling.

involve-benchling works alongside the SDK. You keep using Benchling's typed
models, pagination and full API surface, and this library adds helpers that
work with them.

> **Status: alpha.** The API may change before 1.0. See the [changelog](https://github.com/involvedata/involve-benchling/blob/main/docs/CHANGELOG.md).

involve-benchling is built by [Involve Data](https://involvedata.com). We're big fans of
Benchling and use it every day. This is an independent project, not affiliated with or
endorsed by Benchling, Inc.

## What it adds

| Feature | Module | What it gives you |
|---|---|---|
| **Caching** | `involve_benchling.cache` | Tiered (memory + disk, shared across processes), pickle-free JSON serialisation of SDK models, per-category TTLs. Reference data (schemas, dropdowns, registries) goes from ~500ms to <1ms. |
| **Resolution** | `involve_benchling.resolve` | Generic `get_by_name` / `find_one` over *any* V3 resource, raising `NotFoundError` or `AmbiguousError` when a name matches nothing or several items. |
| **DataFrames** | `involve_benchling.dataframes` | Explicit `to_dataframe()` that expands V3 `schemaFields` into one typed, named column per field. Optional extra. |
| **Read-only clients** | `involve_benchling.core.readonly` | A client that cannot change tenant data, enforced in the HTTP transport below every SDK method. |
| **Rate-limit pacing** | `involve_benchling.core.pacing` | Caps concurrent requests and pauses every request on a client after a `429`, so concurrent calls stop failing together. On by default. |
| **Testing** | `involve_benchling.testing` | pytest plugin: env-based config/client fixtures and a `benchling_tracker` that cleans up every resource a test created — even on failure. |

## Install

```bash
pip install involve-benchling              # core (the SDK and its own dependencies)
pip install "involve-benchling[pandas]"    # + dataframe support
```

## Quick start

```python
from involve_benchling import BenchlingConfig, connect, resolve

config = BenchlingConfig.from_env()   # BENCHLING_BASE_URL, BENCHLING_API_KEY, ...
benchling = connect(config)           # a plain benchling_v3_sdk.Benchling

# The SDK is right there — use it directly:
for seq in benchling.dna_sequence.list(page_size=50):
    print(seq.id, seq.name)

# Resolution with typed errors, over any resource:
plasmid = resolve.get_by_name(benchling.custom_entity, "pEX-001")
schema_id = resolve.get_id_by_name(benchling.entity_schema, "Plasmid")

# Caching reference data:
from involve_benchling.cache import BenchlingCache

cache = BenchlingCache.from_policy(config.cache, namespace=config.base_url)
schemas = cache.get_or_fetch(
    "schemas:entity",
    category="schema",
    fetch=lambda: list(benchling.entity_schema.list()),
)

# Analysis-ready dataframes:
from involve_benchling.dataframes import field_names, to_dataframe

df = to_dataframe(
    benchling.custom_entity.list(schema_eq=schema_id),
    field_names=field_names(benchling.custom_entity_schema, schema_id),
)
```

### Read-only clients

```python
config = BenchlingConfig.from_env(read_only=True)   # or BENCHLING_READ_ONLY=1
benchling = connect(config)

benchling.folder.list()                     # fine
benchling.folder.create(name="x", parent_id="lib_1")
# ReadOnlyViolationError: Read-only client blocked POST .../api/v3/folder/items
```

The check sits in the `httpx` transport, below every SDK method. A
read-only client sends only `GET`, `HEAD` and `OPTIONS`, plus `POST` to the
OAuth token exchange and `/api/v3/search`, which read without changing data.
Raw-response calls and methods added in later SDK releases are covered without
a list of write verbs to maintain.

### Rate limits

Benchling's V3 API gives each user and each app a request budget, plus a
budget shared by the whole tenant. Once a budget is spent it returns `429`,
and it asks callers to pause every request on that budget rather than retry
each one separately. The SDK retries each request on its own, so concurrent
calls keep spending the budget and fail together.

Clients built by `connect()` and `connect_async()` are paced:

- At most `max_concurrency` requests (default 4) are in flight at once.
- After a `429`, every request on the client waits until `Retry-After` has
  passed. Without the header, the pause doubles with each `429` in a row
  (1, 2, 4… s, with jitter) up to 60 s.
- After a `429`, the cap also halves, down to one request. Each time a full
  cap's worth of requests succeeds, it grows by one, back up to
  `max_concurrency`. A pause alone isn't enough, because every request
  resumes at once when it ends and hits the limit again.
- The SDK still retries, and its retries wait out the same pause.

```python
from involve_benchling.core import pacer_for

config = BenchlingConfig.from_env(max_concurrency=2)   # or BENCHLING_MAX_CONCURRENCY=2
benchling = connect(config)
...
pacer_for(benchling).throttled                         # 429s received so far
pacer_for(benchling).limit                             # current cap
```

Each `429` is also logged at `WARNING` on `involve_benchling.core.pacing`.

The pause belongs to one client. Share one client between threads or tasks
that use the same credentials, because separate clients and processes can't
see each other's pauses. Benchling also caps how many objects a tenant can
create or update per hour. A pause can't wait that out, so the SDK raises
once its retries run out.

Turn pacing off with `pacing=False` (or `BENCHLING_PACING=0`). That is also
required to pass your own `httpx_client` to `connect()`.

### Cache storage

The disk tier defaults to `.benchling-cache/` in the working directory. It
creates the directory and its files readable only by the current user, and
writes a `.gitignore` into it so the cache is never committed. Cached
responses can hold sensitive data, so point `CachePolicy.directory` somewhere
protected.

The cache is keyed by `namespace` (usually the tenant URL), not by
credential. Don't share one cache directory between credentials with
different access, or a narrower credential can read what a broader one
cached.

### Testing your own Benchling integrations

```python
import pytest

@pytest.mark.integration
def test_my_workflow(benchling, benchling_tracker):
    entity = benchling.custom_entity.create(...)
    benchling_tracker.track(
        f"custom_entity {entity.id}",
        lambda: benchling.custom_entity.update(
            entity.id, archived=True, archive_reason="Made in error"
        ),
    )
    # ... test things; cleanup happens even if assertions fail
```

## Design principles

1. **Pass through SDK models.** No parallel dataclass universe; functions
   accept and return `benchling_v3_sdk` types.
2. **Generic over bespoke.** One `get_by_name` for 100+ resources, not
   one service class per resource.
3. **Explicit APIs.** No magic kwargs, no hidden state. Strictly typed
   (`py.typed`, mypy `--strict`).
4. **Everything optional is an extra.** Core depends on the SDK and
   nothing else.
5. **No pickle.** Cached values are JSON documents; a shared cache
   directory is never a code-execution vector.

## Roadmap

- `config` — configuration as code: export, plan and apply tenant configuration from
  YAML state files. Design: [`docs/design/config-as-code.md`](https://github.com/involvedata/involve-benchling/blob/main/docs/design/config-as-code.md).
- `tools.discovery` — tenant environment discovery: schemas, dropdowns,
  relationships; ERD and documentation generation.
- `tools.entry_search` — entry search with automatic user/project
  resolution.
- Cache invalidation hooks for write operations.
- Async parity helpers for `AsyncBenchling`.

## Development

```bash
python -m venv venv && source venv/bin/activate
make install   # pip install -e ".[dev]"
make lint type test
```

Integration tests need a tenant. Copy `.test.env.template` to `.test.env`,
fill it in, then run `pytest -m integration`. See [CONTRIBUTING.md](https://github.com/involvedata/involve-benchling/blob/main/CONTRIBUTING.md)
for the full workflow.

## License

Apache-2.0 © Involve Data

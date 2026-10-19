# involve-benchling

**The toolkit the official Benchling SDK doesn't give you.**

A thin, composable layer over [`benchling-v3-sdk-python`](https://pypi.org/project/benchling-v3-sdk-python/)
— it never hides the SDK. You keep Benchling's typed models, pagination,
and full API surface; this library adds what's missing around them.

> **Status: private alpha.** APIs will change before a public release.

## Why

The Benchling V3 SDK is excellent at being an API client. It is not a
toolkit. Teams integrating Benchling all end up rebuilding the same four
things:

| Pillar | Module | What it gives you |
|---|---|---|
| **Caching** | `involve_benchling.cache` | Tiered (memory + disk, shared across processes), pickle-free JSON serialisation of SDK models, per-category TTLs. Reference data (schemas, dropdowns, registries) goes from ~500ms to <1ms. |
| **Resolution** | `involve_benchling.resolve` | Generic `get_by_name` / `find_one` over *any* V3 resource, with typed `NotFoundError` / `AmbiguousError` instead of silent first-match. |
| **DataFrames** | `involve_benchling.dataframes` | Explicit `to_dataframe()` that expands V3 `schemaFields` into one typed, named column per field. Optional extra. |
| **Testing** | `involve_benchling.testing` | pytest plugin: env-based config/client fixtures and a `benchling_tracker` that cleans up every resource a test created — even on failure. |

## Install

```bash
pip install involve-benchling              # core (SDK + nothing else)
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
plasmid = resolve.get_by_name(benchling.custom_entity, "pIVD-001")
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

Integration tests need a tenant: copy `.test.env.template` to `.test.env`,
fill it in, then `pytest -m integration`.

## License

Apache-2.0 © Involve Data

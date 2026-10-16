"""Smoke test against a real tenant. Requires BENCHLING_* env vars.

Run with: pytest -m integration
"""

import pytest

from involve_benchling import resolve

pytestmark = pytest.mark.integration


def test_connects_and_lists_schemas(benchling):
    pager = benchling.entity_schema.list(page_size=5)
    schemas = []
    for schema in pager:
        schemas.append(schema)
        if len(schemas) >= 5:
            break
    assert schemas, "expected at least one entity schema"
    assert all(s.id for s in schemas)


def test_resolve_against_real_resource(benchling):
    first = next(iter(benchling.entity_schema.list(page_size=1)))
    found = resolve.get_by_name(benchling.entity_schema, first.name)
    assert found.id == first.id

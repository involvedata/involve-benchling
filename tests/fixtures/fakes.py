"""In-memory stand-ins for SDK resource clients and the clock."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

from benchling_v3_sdk.types.schema_field_definition_unpaginated_list import (
    SchemaFieldDefinitionUnpaginatedList,
)

Filter = str | Sequence[str] | None


def _as_list(value: Filter) -> list[str] | None:
    if value is None:
        return None
    return [value] if isinstance(value, str) else list(value)


def _schema_id(item: Any) -> str | None:
    schema = getattr(item, "typed_schema", None) or getattr(item, "schema_", None)
    return getattr(schema, "id", None)


class FakeResource:
    """A V3 resource client whose ``list`` applies the common server-side filters.

    The explicit keyword signature matters, because ``resolve`` inspects it
    to decide between server-side and client-side name matching. Each call
    is recorded in ``calls``.
    """

    def __init__(self, items: Iterable[Any]) -> None:
        self.items = list(items)
        self.calls: list[dict[str, Any]] = []

    def list(
        self,
        *,
        id_any_of: Filter = None,
        name_any_of: Filter = None,
        name_any_of_case_sensitive: Filter = None,
        schema_eq: str | None = None,
        page_size: int | None = None,
    ) -> Iterator[Any]:
        ids = _as_list(id_any_of)
        names = _as_list(name_any_of)
        exact_names = _as_list(name_any_of_case_sensitive)
        self.calls.append(
            {
                "id_any_of": ids,
                "name_any_of": names,
                "name_any_of_case_sensitive": exact_names,
                "schema_eq": schema_eq,
                "page_size": page_size,
            }
        )

        items = self.items
        if ids is not None:
            items = [i for i in items if i.id in ids]
        if names is not None:
            lowered = {n.lower() for n in names}
            items = [i for i in items if i.name.lower() in lowered]
        if exact_names is not None:
            items = [i for i in items if i.name in exact_names]
        if schema_eq is not None:
            items = [i for i in items if _schema_id(i) == schema_eq]
        return iter(items)


class UnfilteredResource(FakeResource):
    """A resource client without name filters, forcing client-side matching."""

    def list(self, **filters: Any) -> Iterator[Any]:  # type: ignore[override]
        self.calls.append(filters)
        return iter(self.items)


class FakeSchemaResource:
    """A schema client serving ``list_field_definitions`` from a fixed mapping."""

    def __init__(self, definitions: Mapping[str, SchemaFieldDefinitionUnpaginatedList]) -> None:
        self.definitions = dict(definitions)
        self.calls: list[str] = []

    def list_field_definitions(self, schema_id: str) -> SchemaFieldDefinitionUnpaginatedList:
        self.calls.append(schema_id)
        return self.definitions[schema_id]


class FakeClock:
    """Replaces the ``time`` module where TTLs are computed.

    Both wall-clock and monotonic time start at ``start`` and move only
    when a test calls :meth:`advance`.
    """

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

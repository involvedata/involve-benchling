"""Optional pandas adapters (``pip install involve-benchling[pandas]``).

Explicit conversion functions -- no decorators, no hidden keyword
arguments. Each V3 ``schemaFields`` entry becomes one typed column, so
scientists get analysis-ready frames::

    from involve_benchling.dataframes import field_names, to_dataframe

    names = field_names(benchling.custom_entity_schema, "ts_abc123")
    df = to_dataframe(
        benchling.custom_entity.list(schema_eq="ts_abc123"),
        field_names=names,
    )

Rows are built from the V3 wire format and field values are unwrapped by
their ``__typename``. The SDK's parsed union classes are not used,
because Pydantic resolves structurally identical value types (``TextValue``,
``DateValue``, ``DateTimeValue``) to whichever class it tries first.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["field_names", "to_dataframe"]

_SCHEMA_FIELDS = "schemaFields"
_REF_KEYS = frozenset({"__typename", "id"})
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class SchemaResource(Protocol):
    """Any SDK schema client with a ``list_field_definitions`` operation."""

    def list_field_definitions(self, schema_id: str, /) -> Any: ...


def field_names(
    schema_resource: SchemaResource,
    schema_id: str,
    *,
    key: Literal["name", "system_name"] = "name",
) -> dict[str, str]:
    """Map a schema's field definition IDs to column names.

    V3 field values reference their definition by ID only, so names come
    from the schema. Works with any schema client, e.g.
    ``benchling.custom_entity_schema`` or ``benchling.result_schema``.
    The result is JSON-safe and can be cached with ``BenchlingCache``.

    Args:
        schema_resource: the SDK schema client for the item type.
        schema_id: the schema whose fields to name.
        key: ``"name"`` for display names, ``"system_name"`` for the
            machine-readable warehouse names.
    """
    definitions = schema_resource.list_field_definitions(schema_id).items or []
    return {d.id: getattr(d, key) for d in definitions if d.id and getattr(d, key)}


def to_dataframe(
    items: Iterable[Any],
    *,
    field_names: Mapping[str, str] | None = None,
    expand_fields: bool = True,
) -> pd.DataFrame:
    """Convert SDK models (or V3 wire-format dicts) into a pandas DataFrame.

    Columns use the SDK's snake_case attribute names. References such as
    ``creator`` or ``typed_schema`` collapse to their ID, and ``*_at``
    timestamps become UTC datetimes.

    Args:
        items: any iterable of SDK models or dictionaries -- including a
            pager straight from a ``list`` call.
        field_names: field definition ID to column name, usually from
            :func:`field_names`. Unmapped fields keep their definition ID
            as the column name.
        expand_fields: expand ``schema_fields`` into one column per field.

    Raises:
        ValueError: a field column would overwrite a built-in column.
    """
    pandas = _require_pandas()
    names = field_names or {}
    rows = [_to_row(_as_wire_dict(item), names, expand_fields) for item in items]
    df = pandas.DataFrame(rows)
    for col in df.columns:
        if col.endswith("_at") and pandas.api.types.is_string_dtype(df[col]):
            converted = pandas.to_datetime(df[col], errors="coerce", utc=True)
            if not converted.isna().all():
                df[col] = converted
    return df


def _require_pandas() -> Any:
    try:
        import pandas
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pandas is required for dataframe support: pip install 'involve-benchling[pandas]'"
        ) from exc
    return pandas


def _as_wire_dict(item: Any) -> Mapping[str, Any]:
    if isinstance(item, Mapping):
        return item
    dump = getattr(item, "model_dump", None)
    if callable(dump):
        return dict(dump(mode="json", by_alias=True))
    raise TypeError(f"Cannot convert {type(item).__name__} to a dataframe row")


def _to_row(
    wire: Mapping[str, Any], names: Mapping[str, str], expand_fields: bool
) -> dict[str, Any]:
    row = {
        _snake(key): _collapse_ref(value)
        for key, value in wire.items()
        if key != "__typename" and not (expand_fields and key == _SCHEMA_FIELDS)
    }
    if not expand_fields:
        return row

    for entry in wire.get(_SCHEMA_FIELDS) or []:
        definition_id = (entry.get("fieldDefinition") or {}).get("id")
        if definition_id is None:
            continue
        column = names.get(definition_id, definition_id)
        if column in row:
            raise ValueError(
                f"Field {definition_id!r} maps to column {column!r}, which already exists. "
                "Pass a field_names mapping with a distinct name."
            )
        row[column] = _plain_value(entry.get("value"))
    return row


def _plain_value(wrapper: Any) -> Any:
    """Unwrap a V3 ``BenchlingValue`` into a plain Python value."""
    if not isinstance(wrapper, Mapping):
        return wrapper
    kind = wrapper.get("__typename")
    value = wrapper.get("value")
    if value is None:
        return None
    if kind == "DecimalValue":
        return float(value)
    if kind == "ObjectLinkValue":
        return value.get("id")
    if kind == "ObjectLinkListValue":
        return [ref.get("id") for ref in value]
    if kind == "ArrayValue":
        return [_plain_value(element) for element in value]
    if kind is None:
        return _collapse_ref(value)
    return value


def _collapse_ref(value: Any) -> Any:
    """Reduce a V3 reference (``__typename`` and ``id`` only) to its ID."""
    if _is_ref(value):
        return value["id"]
    if isinstance(value, list) and value and all(_is_ref(v) for v in value):
        return [v["id"] for v in value]
    return value


def _is_ref(value: Any) -> bool:
    return isinstance(value, Mapping) and "id" in value and set(value) <= _REF_KEYS


def _snake(key: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", key).lower()

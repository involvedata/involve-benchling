"""Optional pandas adapters (``pip install involve-benchling[pandas]``).

Explicit conversion functions -- no decorators, no hidden keyword
arguments. Benchling's ``fields`` structure is expanded into typed
columns so scientists get analysis-ready frames::

    from involve_benchling.dataframes import to_dataframe

    df = to_dataframe(benchling.custom_entity.list(schema_eq="ts_abc123"))
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["to_dataframe"]

_VALUE_KEYS = ("value",)
_TEXT_KEYS = ("text_value", "textValue", "display_value", "displayValue")


def _require_pandas() -> Any:
    try:
        import pandas
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pandas is required for dataframe support: pip install 'involve-benchling[pandas]'"
        ) from exc
    return pandas


def _as_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    dump = getattr(item, "model_dump", None)
    if callable(dump):
        return dict(dump(mode="json"))  # Pydantic SDK models
    if hasattr(item, "__dict__"):
        return dict(vars(item))
    raise TypeError(f"Cannot convert {type(item).__name__} to a dataframe row")


def _first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _expand_fields(row: dict[str, Any]) -> dict[str, Any]:
    fields = row.get("fields")
    if not isinstance(fields, dict):
        return row
    out = {k: v for k, v in row.items() if k != "fields"}
    for field_name, data in fields.items():
        if isinstance(data, dict):
            out[field_name] = _first(data, _VALUE_KEYS)
            text = _first(data, _TEXT_KEYS)
            if text is not None:
                out[f"{field_name}_text"] = text
        else:
            out[field_name] = data
    return out


def to_dataframe(items: Iterable[Any], *, expand_fields: bool = True) -> pd.DataFrame:
    """Convert SDK models (or dicts) into a pandas DataFrame.

    Args:
        items: any iterable of SDK models or dictionaries -- including a
            pager straight from a ``list`` call.
        expand_fields: expand Benchling's ``fields`` mapping into one
            column per field (plus ``<field>_text`` where a display value
            exists).
    """
    pandas = _require_pandas()
    rows = [_as_dict(item) for item in items]
    if expand_fields:
        rows = [_expand_fields(row) for row in rows]
    df = pandas.DataFrame(rows)
    for col in df.columns:
        if (
            isinstance(col, str)
            and col.endswith("_at")
            and pandas.api.types.is_string_dtype(df[col])
        ):
            converted = pandas.to_datetime(df[col], errors="coerce", utc=True)
            if not converted.isna().all():
                df[col] = converted
    return df

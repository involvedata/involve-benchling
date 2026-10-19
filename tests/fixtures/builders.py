"""Builders for V3 wire-format payloads and SDK models.

Payload builders return dicts shaped like Benchling's JSON responses,
``__typename`` included. Model builders validate those payloads into real
``benchling_v3_sdk`` types, so tests exercise the SDK's own parsing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from benchling_v3_sdk.types.custom_entity import CustomEntity
from benchling_v3_sdk.types.schema_field_definition_unpaginated_list import (
    SchemaFieldDefinitionUnpaginatedList,
)

Payload = dict[str, Any]

DEFAULT_CREATED_AT = "2026-01-02T03:04:05Z"


def ref(typename: str, id: str) -> Payload:
    return {"__typename": typename, "id": id}


# Field value wrappers (V3 ``BenchlingValue`` union members).


def _wrap(typename: str, value: Any) -> Payload:
    return {"__typename": typename, "value": value}


def text_value(value: str) -> Payload:
    return _wrap("TextValue", value)


def text_and_url_value(value: str, url: str) -> Payload:
    return {**_wrap("TextAndUrlValue", value), "url": url}


def decimal_value(value: float | str) -> Payload:
    return _wrap("DecimalValue", str(value))


def integer_value(value: int) -> Payload:
    return _wrap("IntegerValue", value)


def boolean_value(value: bool) -> Payload:
    return _wrap("BooleanValue", value)


def date_value(value: str) -> Payload:
    return _wrap("DateValue", value)


def datetime_value(value: str) -> Payload:
    return _wrap("DateTimeValue", value)


def json_value(value: Mapping[str, Any]) -> Payload:
    return _wrap("JsonValue", dict(value))


def link_value(id: str, typename: str = "CustomEntity") -> Payload:
    return _wrap("ObjectLinkValue", ref(typename, id))


def link_list_value(ids: list[str], typename: str = "CustomEntity") -> Payload:
    return _wrap("ObjectLinkListValue", [ref(typename, i) for i in ids])


def array_value(*elements: Payload) -> Payload:
    return _wrap("ArrayValue", list(elements))


# Schema fields and entities.


def schema_field(definition_id: str, value: Payload | None) -> Payload:
    return {
        "__typename": "SchemaFieldValue",
        "fieldDefinition": {"id": definition_id},
        "value": value,
    }


def custom_entity_payload(
    id: str,
    name: str,
    *,
    schema_id: str | None = None,
    fields: Mapping[str, Payload | None] | None = None,
    creator_id: str = "ent_user",
    created_at: str = DEFAULT_CREATED_AT,
    **extra: Any,
) -> Payload:
    """A ``CustomEntity`` payload. ``fields`` maps definition ID to value wrapper."""
    payload: Payload = {
        "__typename": "CustomEntity",
        "id": id,
        "name": name,
        "createdAt": created_at,
        "creator": ref("User", creator_id),
        "schemaFields": [schema_field(d, v) for d, v in (fields or {}).items()],
        **extra,
    }
    if schema_id is not None:
        payload["typedSchema"] = ref("CustomEntitySchema", schema_id)
    return payload


def custom_entity(id: str, name: str, **kwargs: Any) -> CustomEntity:
    return CustomEntity.model_validate(custom_entity_payload(id, name, **kwargs))


# Field definitions.


def field_definition_payload(
    id: str,
    name: str,
    *,
    type: str = "TEXT",
    system_name: str | None = None,
    typename: str = "TextFieldDefinition",
) -> Payload:
    return {
        "__typename": typename,
        "id": id,
        "name": name,
        "systemName": system_name or name.lower().replace(" ", "_"),
        "type": type,
    }


def field_definitions(*payloads: Payload) -> SchemaFieldDefinitionUnpaginatedList:
    return SchemaFieldDefinitionUnpaginatedList.model_validate({"items": list(payloads)})

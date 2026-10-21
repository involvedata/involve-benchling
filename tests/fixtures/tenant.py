"""A small canned tenant: one plasmid schema, its field definitions and entities.

The data covers the cases helpers must handle. It includes every common
value type, a link and a link list, an unset field, and two entities whose
names differ only by case.
"""

from __future__ import annotations

import pytest
from benchling_v3_sdk.types.custom_entity import CustomEntity
from benchling_v3_sdk.types.schema_field_definition_unpaginated_list import (
    SchemaFieldDefinitionUnpaginatedList,
)

from . import builders as b
from .fakes import FakeResource, FakeSchemaResource, UnfilteredResource

PLASMID_SCHEMA_ID = "ts_plasmid"
OTHER_SCHEMA_ID = "ts_other"

CONCENTRATION = "tsf_conc"
HOST = "tsf_host"
PARTS = "tsf_parts"
VERIFIED = "tsf_verified"
NOTES = "tsf_notes"

PLASMID_FIELD_NAMES = {
    CONCENTRATION: "Concentration",
    HOST: "Host",
    PARTS: "Parts",
    VERIFIED: "Verified",
    NOTES: "Notes",
}


@pytest.fixture
def plasmid_field_definitions() -> SchemaFieldDefinitionUnpaginatedList:
    return b.field_definitions(
        b.field_definition_payload(
            CONCENTRATION, "Concentration", type="FLOAT", typename="FloatFieldDefinition"
        ),
        b.field_definition_payload(
            HOST, "Host", type="CUSTOM_ENTITY_LINK", typename="CustomEntityLinkFieldDefinition"
        ),
        b.field_definition_payload(
            PARTS, "Parts", type="CUSTOM_ENTITY_LINK", typename="CustomEntityLinkFieldDefinition"
        ),
        b.field_definition_payload(
            VERIFIED, "Verified", type="BOOLEAN", typename="BooleanFieldDefinition"
        ),
        b.field_definition_payload(NOTES, "Notes"),
    )


@pytest.fixture
def plasmids() -> list[CustomEntity]:
    """Three plasmids plus one entity on another schema."""
    return [
        b.custom_entity(
            "bfi_001",
            "pEX-001",
            schema_id=PLASMID_SCHEMA_ID,
            fields={
                CONCENTRATION: b.decimal_value("5.25"),
                HOST: b.link_value("bfi_ecoli"),
                PARTS: b.link_list_value(["bfi_ori", "bfi_amp"]),
                VERIFIED: b.boolean_value(True),
                NOTES: b.text_value("Sequence confirmed"),
            },
        ),
        b.custom_entity(
            "bfi_002",
            "pEX-002",
            schema_id=PLASMID_SCHEMA_ID,
            fields={CONCENTRATION: b.decimal_value("1.5"), NOTES: None},
        ),
        b.custom_entity("bfi_003", "pex-002", schema_id=PLASMID_SCHEMA_ID),
        b.custom_entity("bfi_900", "Strain-900", schema_id=OTHER_SCHEMA_ID),
    ]


@pytest.fixture
def entity_resource(plasmids: list[CustomEntity]) -> FakeResource:
    """Stands in for ``benchling.custom_entity``."""
    return FakeResource(plasmids)


@pytest.fixture
def unfiltered_resource(plasmids: list[CustomEntity]) -> UnfilteredResource:
    """A resource without name filters, for client-side matching paths."""
    return UnfilteredResource(plasmids)


@pytest.fixture
def schema_resource(
    plasmid_field_definitions: SchemaFieldDefinitionUnpaginatedList,
) -> FakeSchemaResource:
    """Stands in for ``benchling.custom_entity_schema``."""
    return FakeSchemaResource({PLASMID_SCHEMA_ID: plasmid_field_definitions})

import pytest

from involve_benchling.dataframes import field_names, to_dataframe
from tests.fixtures import builders as b
from tests.fixtures.tenant import PLASMID_FIELD_NAMES, PLASMID_SCHEMA_ID

pd = pytest.importorskip("pandas")


def _row(df, entity_id):
    return df.set_index("id").loc[entity_id]


def test_expands_schema_fields_into_named_columns(plasmids):
    row = _row(to_dataframe(plasmids, field_names=PLASMID_FIELD_NAMES), "bfi_001")
    assert row["Concentration"] == 5.25
    assert row["Host"] == "bfi_ecoli"
    assert row["Parts"] == ["bfi_ori", "bfi_amp"]
    assert row["Verified"]
    assert row["Notes"] == "Sequence confirmed"


def test_unset_and_missing_fields_are_empty(plasmids):
    df = to_dataframe(plasmids, field_names=PLASMID_FIELD_NAMES)
    assert pd.isna(_row(df, "bfi_002")["Notes"])
    assert pd.isna(_row(df, "bfi_003")["Concentration"])


def test_unmapped_fields_use_definition_ids(plasmids):
    df = to_dataframe(plasmids)
    assert "tsf_conc" in df.columns
    assert "Concentration" not in df.columns


def test_unwraps_every_value_type():
    entity = b.custom_entity(
        "bfi_1",
        "values",
        fields={
            "f_int": b.integer_value(3),
            "f_date": b.date_value("2026-03-04"),
            "f_datetime": b.datetime_value("2026-03-04T05:06:07Z"),
            "f_url": b.text_and_url_value("Doc", "https://example.com"),
            "f_json": b.json_value({"id": "x", "k": 1}),
            "f_array": b.array_value(b.integer_value(1), b.decimal_value("2.5")),
        },
    )
    row = to_dataframe([entity]).iloc[0]
    assert row["f_int"] == 3
    assert row["f_date"] == "2026-03-04"
    assert row["f_datetime"] == "2026-03-04T05:06:07Z"
    assert row["f_url"] == "Doc"
    assert row["f_json"] == {"id": "x", "k": 1}
    assert row["f_array"] == [1, 2.5]


def test_builtin_columns_are_snake_case_with_refs_collapsed(plasmids):
    df = to_dataframe(plasmids)
    assert "schema_fields" not in df.columns
    assert "__typename" not in df.columns
    assert _row(df, "bfi_001")["creator"] == "ent_user"
    assert _row(df, "bfi_001")["typed_schema"] == PLASMID_SCHEMA_ID
    assert pd.api.types.is_datetime64_any_dtype(df["created_at"])


def test_no_expansion_keeps_schema_fields(plasmids):
    df = to_dataframe(plasmids, expand_fields=False)
    assert "schema_fields" in df.columns
    assert "tsf_conc" not in df.columns


def test_accepts_wire_format_dicts():
    wire = b.custom_entity_payload("bfi_1", "x", fields={"tsf_conc": b.decimal_value("7")})
    assert to_dataframe([wire], field_names=PLASMID_FIELD_NAMES).loc[0, "Concentration"] == 7.0


def test_field_name_collision_raises(plasmids):
    with pytest.raises(ValueError, match="already exists"):
        to_dataframe(plasmids, field_names={"tsf_conc": "name"})


def test_field_names_from_schema(schema_resource):
    assert field_names(schema_resource, PLASMID_SCHEMA_ID) == PLASMID_FIELD_NAMES
    assert field_names(schema_resource, PLASMID_SCHEMA_ID, key="system_name")["tsf_conc"] == (
        "concentration"
    )
    assert schema_resource.calls == [PLASMID_SCHEMA_ID, PLASMID_SCHEMA_ID]

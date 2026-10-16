import pytest
from pydantic import BaseModel

pd = pytest.importorskip("pandas")

from involve_benchling.dataframes import to_dataframe  # noqa: E402


class Entity(BaseModel):
    id: str
    name: str
    created_at: str
    fields: dict


ROWS = [
    Entity(
        id="ent_1",
        name="pIVD-001",
        created_at="2026-01-02T03:04:05Z",
        fields={
            "concentration": {"value": 5.0, "text_value": "5.0 ng/uL"},
            "host": {"value": "sfso_123", "display_value": "E. coli"},
        },
    ),
    Entity(id="ent_2", name="pIVD-002", created_at="2026-02-03T04:05:06Z", fields={}),
]


def test_expands_fields_into_columns():
    df = to_dataframe(ROWS)
    assert df.loc[0, "concentration"] == 5.0
    assert df.loc[0, "concentration_text"] == "5.0 ng/uL"
    assert df.loc[0, "host_text"] == "E. coli"
    assert "fields" not in df.columns


def test_no_expansion_keeps_fields():
    df = to_dataframe(ROWS, expand_fields=False)
    assert "fields" in df.columns


def test_datetime_columns_parsed():
    df = to_dataframe(ROWS)
    assert str(df["created_at"].dtype).startswith("datetime64")


def test_accepts_plain_dicts():
    df = to_dataframe([{"id": "x", "name": "y"}])
    assert list(df.columns) == ["id", "name"]


def test_rejects_unconvertible():
    with pytest.raises(TypeError):
        to_dataframe([42])

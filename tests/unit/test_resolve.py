import pytest

from involve_benchling import AmbiguousError, NotFoundError, resolve
from tests.fixtures.tenant import PLASMID_SCHEMA_ID


def test_get_by_name_server_side(entity_resource):
    assert resolve.get_by_name(entity_resource, "pIVD-001").id == "bfi_001"
    assert entity_resource.calls[0]["name_any_of"] == ["pIVD-001"]


def test_get_by_name_case_sensitive_server_side(entity_resource):
    item = resolve.get_by_name(entity_resource, "pivd-002", case_sensitive=True)
    assert item.id == "bfi_003"
    assert entity_resource.calls[0]["name_any_of_case_sensitive"] == ["pivd-002"]


def test_get_by_name_ambiguous(entity_resource):
    with pytest.raises(AmbiguousError) as exc:
        resolve.get_by_name(entity_resource, "PIVD-002")
    assert exc.value.count == 2


def test_get_by_name_not_found(entity_resource):
    with pytest.raises(NotFoundError):
        resolve.get_by_name(entity_resource, "pIVD-404")


def test_get_by_name_passes_extra_filters(entity_resource):
    with pytest.raises(NotFoundError):
        resolve.get_by_name(entity_resource, "Strain-900", schema_eq=PLASMID_SCHEMA_ID)
    assert entity_resource.calls[0]["schema_eq"] == PLASMID_SCHEMA_ID


def test_get_by_name_client_side_fallback(unfiltered_resource):
    assert resolve.get_by_name(unfiltered_resource, "PIVD-001").id == "bfi_001"


def test_get_by_name_client_side_case_sensitive(unfiltered_resource):
    item = resolve.get_by_name(unfiltered_resource, "pivd-002", case_sensitive=True)
    assert item.id == "bfi_003"


def test_find_one_single_match(entity_resource):
    assert resolve.find_one(entity_resource, name_any_of=["pIVD-001"]).id == "bfi_001"


def test_find_all_returns_every_match(entity_resource):
    assert len(resolve.find_all(entity_resource, schema_eq=PLASMID_SCHEMA_ID)) == 3


def test_get_id_by_name(entity_resource):
    assert resolve.get_id_by_name(entity_resource, "pIVD-001") == "bfi_001"

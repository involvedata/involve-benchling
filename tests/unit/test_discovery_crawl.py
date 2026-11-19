"""Tests for the schema crawl: a partial crawl must never present as complete."""

import asyncio
from typing import Any

from benchling_v3_sdk.core.api_error import ApiError

from involve_benchling.tools.discovery.crawl import (
    ENTITY_TYPES,
    ERD_SECTIONS,
    SCHEMA_FAMILIES,
    crawl_erd_env,
    describe_error,
)
from tests.fixtures.fakes import AsyncFakeResource, FakeModel


class Boom(RuntimeError):
    pass


def _client(
    *,
    fail_families: tuple[str, ...] = (),
    fail_sections: tuple[str, ...] = (),
    child_fail_sections: tuple[str, ...] = (),
    detail_raises: bool = False,
    entity_type: str = "custom_entity",
    found_as: str | None = None,
) -> Any:
    b = FakeModel()
    for family in SCHEMA_FAMILIES:
        extra = {"type": entity_type} if family == "entity_schema" else {}
        setattr(
            b,
            family,
            AsyncFakeResource(
                [FakeModel(id=f"{family}_0", name=f"{family} 0", **extra)],
                fail=TypeError("unhashable type") if family in fail_families else None,
                detail_fail=Boom("timeout fetching detail") if detail_raises else None,
            ),
        )
    found_as = found_as or entity_type
    for t in ENTITY_TYPES:
        missing = ApiError(status_code=404, body={"detail": "item not found"})
        setattr(b, f"{t}_schema", AsyncFakeResource(get_fail=None if t == found_as else missing))
    for sect in ERD_SECTIONS:
        has_children = sect.name in child_fail_sections
        setattr(
            b,
            sect.resource,
            AsyncFakeResource(
                [FakeModel(id=f"{sect.resource}_0", name=sect.name)] if has_children else [],
                fail=Boom("403 Forbidden") if sect.name in fail_sections else None,
                detail_fail=Boom("timeout") if has_children else None,
            ),
        )
    return b


def _crawl(b: Any = None, **kw: Any) -> dict[str, Any]:
    return asyncio.run(crawl_erd_env(b if b is not None else _client(**kw)))


def test_clean_crawl_reports_complete() -> None:
    env = _crawl()
    assert env["_status"]["complete"] is True, env["_status"]
    assert env["_status"]["incomplete_sections"] == []
    assert len(env["schemas"]) == len(SCHEMA_FAMILIES)
    assert env["_status"]["sections"].keys() == {
        "schemas",
        "dropdowns",
        "registries",
        "organizations",
    }
    assert env["_status"]["sections"]["schemas"] == {
        "status": "ok",
        "categories_expected": len(SCHEMA_FAMILIES),
        "categories_returned": len(SCHEMA_FAMILIES),
    }


def test_failed_family_is_detected_and_named() -> None:
    sec_all = _crawl(fail_families=("entity_schema",))["_status"]
    assert sec_all["complete"] is False and sec_all["incomplete_sections"] == ["schemas"]
    sec = sec_all["sections"]["schemas"]
    assert sec["status"] == "partial"
    assert sec["categories_returned"] == len(SCHEMA_FAMILIES) - 1
    # The exception type is kept, so a permissions failure reads differently from a crash.
    assert sec["failed_categories"] == {"entity_schema": "TypeError: unhashable type"}


def test_detail_fetch_failure_is_marked_on_the_schema() -> None:
    """A schema whose fields failed to load must not read as one with no fields."""
    env = _crawl(detail_raises=True)
    assert env["_status"]["complete"] is False
    assert all("_detail_error" in s for s in env["schemas"].values())
    assert all("fieldDefinitions" not in s for s in env["schemas"].values())
    assert env["_status"]["sections"]["schemas"]["detail_fetch_failed"]


def test_unknown_entity_type_is_a_detail_failure() -> None:
    """Without a typed client the naming template is unknown, not empty."""
    sch = _crawl(entity_type="hologram")["schemas"]["entity_schema_0"]
    assert "no V3 schema client for entity type 'hologram'" in sch["_detail_error"]


def test_mislabelled_entity_type_falls_back_and_is_recorded() -> None:
    """Oligo duplexes list as custom_entity; the right typed client still answers."""
    env = _crawl(entity_type="custom_entity", found_as="oligo_duplex")
    sch = env["schemas"]["entity_schema_0"]
    assert "_detail_error" not in sch
    assert sch["typeMismatch"] == {"listedAs": "custom_entity", "foundAs": "oligo_duplex"}
    assert env["_status"]["complete"] is True


def test_entity_schema_no_typed_client_finds_is_a_detail_failure() -> None:
    env = _crawl(entity_type="custom_entity", found_as="nothing")
    sch = env["schemas"]["entity_schema_0"]
    assert sch["_detail_error"] == "ApiError: HTTP 404: item not found"
    assert env["_status"]["complete"] is False


def test_schema_listed_by_two_families_is_kept_once() -> None:
    """The entity listing also returns equipment schemas; the equipment family owns them."""
    b = _client()
    b.entity_schema = AsyncFakeResource([FakeModel(id="ts_eq", name="Equipment", type=None)])
    b.equipment_schema = AsyncFakeResource([FakeModel(id="ts_eq", name="Equipment")])
    env = _crawl(b)
    assert env["schemas"]["ts_eq"]["family"] == "equipment_schema"
    assert "detail_fetch_failed" not in env["_status"]["sections"]["schemas"]


def test_entity_schema_merges_typed_detail() -> None:
    sch = _crawl()["schemas"]["entity_schema_0"]
    assert sch["family"] == "entity_schema"
    assert sch["nameTemplate"] == {"parts": []}
    assert sch["fieldDefinitions"] == [] and sch["fieldsets"] == []
    assert "typeMismatch" not in sch


def test_failed_section_is_null_not_empty_list() -> None:
    """[] means 'genuinely none'; None means 'we don't know'."""
    env = _crawl(fail_sections=("organizations",))
    assert env["organizations"] is None
    assert env["registries"] == []
    reason = env["_status"]["sections"]["organizations"]["reason"]
    assert reason == "Boom: 403 Forbidden"
    assert env["_status"]["incomplete_sections"] == ["organizations"]


def test_failed_child_fetch_is_marked_on_the_record() -> None:
    """A dropdown whose options failed must not read as one with no options."""
    env = _crawl(child_fail_sections=("dropdowns",))
    assert list(env["dropdowns"]) == ["dropdown_0"]  # keyed by id
    dd = env["dropdowns"]["dropdown_0"]
    assert "options" not in dd and dd["_detail_error"] == "Boom: timeout"
    assert env["_status"]["sections"]["dropdowns"]["status"] == "partial"


def test_api_errors_are_reduced_to_status_and_message() -> None:
    body = {"error": {"message": "Not allowed", "type": "invalid_request_error"}}
    err = ApiError(status_code=403, headers={"set-cookie": "session=secret"}, body=body)
    assert describe_error(err) == "ApiError: HTTP 403: Not allowed (invalid_request_error)"

"""Read-only schema crawl over the async V3 client.

:func:`crawl_erd_env` is the one public function. It collects every schema family
with its field definitions, validation rules and fieldsets, plus the reference data
an ERD needs (dropdowns, registries and organizations). Records keep the V3 wire
format (camelCase keys, ``__typename`` kept), so a reader can check any field against
the API reference. Sub-resource links are replaced by the fetched lists, e.g.
``fieldDefinitions`` on schemas and ``options`` on dropdowns.

Registry scoping: V3 records name their registry (``registry.id``). Entity,
container, box, plate and location schemas and dropdowns carry one; result,
run and entry schemas belong to the organization and carry none.

**A partial crawl must never present as a complete one.** Every section
records its outcome in a ``status`` dict. A section that failed is ``None``,
never ``[]``, because an empty list reads as "the tenant genuinely has none".
Callers must treat ``_status["complete"] is False`` as "do not quote these
counts as findings".
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from benchling_v3_sdk import AsyncBenchling
from benchling_v3_sdk.core.api_error import ApiError
from benchling_v3_sdk.core.pagination import AsyncPager

from ...core.errors import describe_error
from .erd import ErdError

__all__ = ["crawl_erd_env"]

#: Every V3 schema family the crawl lists. ``entity_schema`` covers all
#: registrable types (custom entities, sequences, molecules, mixtures, ...);
#: each record's ``type`` names its typed client.
_SCHEMA_FAMILIES: tuple[str, ...] = (
    "entity_schema",
    "result_schema",
    "run_schema",
    "entry_schema",
    "container_schema",
    "box_schema",
    "well_plate_schema",
    "matrix_plate_schema",
    "location_schema",
    "workflow_task_schema",
    "workflow_output_schema",
    "study_schema",
    "equipment_schema",
)

#: Extra sub-resources fetched for a schema family, as (output key, method).
_FAMILY_CHILDREN: dict[str, tuple[tuple[str, str], ...]] = {
    "run_schema": (
        ("automationInputFileConfigs", "list_automation_input_file_configs"),
        ("automationOutputFileConfigs", "list_automation_output_file_configs"),
    ),
}

#: Entity types with a typed schema client, tried in turn when the listed
#: ``type`` is wrong.
_ENTITY_TYPES: tuple[str, ...] = (
    "custom_entity",
    "dna_sequence",
    "rna_sequence",
    "aa_sequence",
    "dna_oligo",
    "rna_oligo",
    "oligo_duplex",
    "oligo_conjugate",
    "molecule",
    "mixture",
    "protein",
)

#: Page size for list calls.
_PAGE_SIZE = 100


@dataclass(frozen=True)
class _Section:
    """One tenant-wide resource list, with sub-resources fetched per record."""

    name: str
    resource: str
    children: tuple[tuple[str, str], ...] = ()
    #: Output a dict keyed by record id instead of a list.
    keyed: bool = False


#: Dropdowns with their options, keyed by dropdown id.
_DROPDOWNS = _Section("dropdowns", "dropdown", (("options", "list_options"),), keyed=True)
#: Organizations, to name a registry's owner.
_ORGANIZATIONS = _Section("organizations", "organization")


def _wire(model: Any) -> dict[str, Any]:
    """Return an SDK model as a dict in the V3 wire format."""
    out: dict[str, Any] = model.model_dump(mode="json", by_alias=True)
    return out


async def _all_items(call: Awaitable[Any], *, limit: int | None = None) -> list[Any]:
    """Await an SDK list call and return every item, across pages.

    Paged calls return an ``AsyncPager``, whose ``items`` holds only the first
    page. Unpaged calls return a model whose ``items`` is the whole list.
    """
    result = await call
    if not isinstance(result, AsyncPager):
        return list(result.items or [])[:limit]
    out: list[Any] = []
    async with aclosing(result.__aiter__()) as items:  # type: ignore[type-var]
        async for item in items:
            out.append(item)
            if limit is not None and len(out) >= limit:
                break
    return out


async def _gather(coros: Iterable[Awaitable[Any]]) -> list[Any]:
    """Run calls together, returning exceptions in place of results.

    The client's pacer decides how many requests are in flight.
    """
    return list(await asyncio.gather(*coros, return_exceptions=True))


# --- schemas -------------------------------------------------------------------


async def _typed_entity_detail(b: AsyncBenchling, listed: Any) -> tuple[Any, dict[str, Any]]:
    """Fetch an entity schema through its typed client.

    The entity-schema listing can name the wrong type (oligo duplexes come
    back as ``custom_entity``), and the wrong typed client answers 404. On a
    404 the other types are tried, and a hit is recorded as ``typeMismatch``.
    """
    listed_type = listed.type
    order = [listed_type] if listed_type in _ENTITY_TYPES else []
    order += [t for t in _ENTITY_TYPES if t != listed_type]
    first_error: ApiError | None = None
    for entity_type in order:
        client = getattr(b, f"{entity_type}_schema")
        try:
            detail = _wire(await client.get(listed.id))
        except ApiError as e:
            if e.status_code != 404:
                raise
            first_error = first_error or e
            continue
        if entity_type != listed_type:
            detail["typeMismatch"] = {"listedAs": listed_type, "foundAs": entity_type}
        return client, detail
    if first_error is not None and listed_type in _ENTITY_TYPES:
        raise first_error
    raise LookupError(f"no V3 schema client for entity type {listed_type!r}")


async def _schema_detail(b: AsyncBenchling, family: str, listed: Any) -> dict[str, Any]:
    """Return one schema with its sub-resources fetched inline.

    Entity schemas are re-read through their typed client, which adds the
    naming template (``nameTemplate``), ``itemIdPrefix`` and fieldsets. The
    listing's ``registry`` survives the merge because typed records omit it.
    """
    client = getattr(b, family)
    record = _wire(listed)
    detail_client = client
    if family == "entity_schema":
        detail_client, detail = await _typed_entity_detail(b, listed)
        record.update(detail)

    record["fieldDefinitions"] = [
        _wire(f) for f in await _all_items(client.list_field_definitions(listed.id))
    ]
    if hasattr(client, "list_validation_rules"):
        record["validationRules"] = [
            _wire(r) for r in await _all_items(client.list_validation_rules(listed.id))
        ]
    if hasattr(detail_client, "list_fieldsets"):
        record["fieldsets"] = [
            _wire(f) for f in await _all_items(detail_client.list_fieldsets(listed.id))
        ]
    for key, method in _FAMILY_CHILDREN.get(family, ()):
        record[key] = [_wire(x) for x in await _all_items(getattr(client, method)(listed.id))]
    return {"family": family, **record}


async def _crawl_schemas(b: AsyncBenchling, status: dict[str, Any]) -> dict[str, Any]:
    """Return every schema of every family, keyed by id, live and archived.

    Records the outcome in ``status["schemas"]``: ``ok`` or ``partial``, the
    families that failed to list (``failed_categories``) and the schemas whose
    detail failed to load (``detail_fetch_failed``). A schema whose detail
    failed keeps its listing record plus ``_detail_error``, never an empty
    field list.
    """
    # Archived schemas too, so a reader can tell an archived schema from a missing one.
    listed = await _gather(
        [
            _all_items(getattr(b, f).list(page_size=_PAGE_SIZE, archived_any_of=[True, False]))
            for f in _SCHEMA_FAMILIES
        ]
    )
    failed: dict[str, str] = {}
    stubs: list[tuple[str, Any]] = []
    for family, result in zip(_SCHEMA_FAMILIES, listed, strict=True):
        if isinstance(result, BaseException):
            # Keep the exception type, not just the message: it separates "this
            # tenant's app lacks a Read grant" from "the library is broken".
            failed[family] = describe_error(result)
        else:
            stubs.extend((family, s) for s in result)

    # The entity-schema listing also returns schemas another family owns
    # (equipment schemas, for one), which no typed entity client can fetch.
    owned = {s.id for family, s in stubs if family != "entity_schema"}
    stubs = [(f, s) for f, s in stubs if not (f == "entity_schema" and s.id in owned)]

    entry: dict[str, Any] = {
        "status": "partial" if failed else "ok",
        "categories_expected": len(_SCHEMA_FAMILIES),
        "categories_returned": len(_SCHEMA_FAMILIES) - len(failed),
    }
    if failed:
        entry["failed_categories"] = failed

    details = await _gather([_schema_detail(b, f, s) for f, s in stubs])
    schemas: dict[str, Any] = {}
    detail_errors: dict[str, str] = {}
    for (family, stub), det in zip(stubs, details, strict=True):
        if isinstance(det, BaseException):
            # A failed detail fetch must not read as a schema with no fields.
            detail_errors[stub.id] = describe_error(det)
            schemas[stub.id] = {
                "family": family,
                **_wire(stub),
                "_detail_error": detail_errors[stub.id],
            }
        else:
            schemas[stub.id] = det
    if detail_errors:
        entry["status"] = "partial"
        entry["detail_fetch_failed"] = detail_errors
    status["schemas"] = entry
    return schemas


# --- tenant-wide sections ------------------------------------------------------


async def _record_with_children(b: AsyncBenchling, section: _Section, item: Any) -> dict[str, Any]:
    client = getattr(b, section.resource)
    record = _wire(item)
    for key, method in section.children:
        record[key] = [_wire(x) for x in await _all_items(getattr(client, method)(item.id))]
    return record


async def _crawl_section(
    b: AsyncBenchling, section: _Section, status: dict[str, Any]
) -> list[dict[str, Any]] | dict[str, dict[str, Any]] | None:
    """List one section and fetch its children, recording the outcome in ``status``.

    Returns ``None`` on failure, deliberately not ``[]``, so a reader can tell
    "we asked and there were none" from "we never got an answer".
    """
    client = getattr(b, section.resource)
    try:
        items = await _all_items(client.list(page_size=_PAGE_SIZE))
    except Exception as e:
        status[section.name] = {"status": "error", "reason": describe_error(e)}
        return None
    status[section.name] = {"status": "ok", "count": len(items)}

    if section.children:
        details = await _gather([_record_with_children(b, section, i) for i in items])
    else:
        details = [_wire(i) for i in items]
    records: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for item, det in zip(items, details, strict=True):
        if isinstance(det, BaseException):
            # A failed child fetch must not read as a record with no children.
            errors[item.id] = describe_error(det)
            records.append({**_wire(item), "_detail_error": errors[item.id]})
        else:
            records.append(det)
    if errors:
        status[section.name]["status"] = "partial"
        status[section.name]["detail_fetch_failed"] = errors
    return {r["id"]: r for r in records} if section.keyed else records


def _summarize_status(sections: dict[str, Any]) -> dict[str, Any]:
    """Roll per-section outcomes into one verdict: ``complete``, ``incomplete_sections``
    (those that failed or came back partial) and ``sections`` (each section's outcome)."""
    bad = sorted(k for k, v in sections.items() if v.get("status") in ("error", "partial"))
    return {
        "complete": not bad,
        "incomplete_sections": bad,
        "sections": {k: sections[k] for k in sorted(sections)},
    }


def _tenant_id(tenant_url: str | None) -> str | None:
    """The tenant's short id, the first label of its host: ``example`` for example.benchling.com."""
    host = urlparse(tenant_url or "").hostname
    return host.split(".")[0] if host else None


def _tenant_url(b: AsyncBenchling) -> str | None:
    """The client's tenant URL, e.g. ``https://example.benchling.com``, if it exposes one."""
    try:
        base: str = b._client_wrapper.get_base_url()
    except AttributeError:
        return None
    parts = urlparse(base)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None


async def crawl_erd_env(b: AsyncBenchling, *, tenant_url: str | None = None) -> dict[str, Any]:
    """Crawl what an ERD needs: schemas, dropdowns, registries and organizations.

    Returns a dict in the shape
    :func:`~involve_benchling.tools.discovery.erd.build_erd_data` reads: ``schemas``
    (keyed by id), ``dropdowns`` (keyed by id), ``registries`` and ``organizations``,
    each section's outcome under ``_status``, and under ``_meta`` ``tenant`` (the short
    id, e.g. ``example``), ``tenantUrl`` and ``crawledAt`` (when the crawl started, UTC,
    ``YYYY-MM-DDTHH:MM:SSZ``). ``tenant_url`` overrides the URL read from the client.

    The crawl needs a client built with ``BenchlingConfig(early_access=True)``: most of
    the V3 endpoints it calls are beta (entity, run, entry, plate, workflow output and
    equipment schemas, and registries) and answer 403 without it.

    Registries are listed first, because no map can be built without them. If that
    fails, nothing else is crawled.

    Raises:
        ErdError: the registries could not be listed. The message carries Benchling's
            reason, which says whether early access, permissions or credentials are
            at fault.
    """
    started = datetime.now(timezone.utc)
    url = (tenant_url or _tenant_url(b) or "").rstrip("/") or None
    try:
        registries = await _all_items(b.registry.list(page_size=_PAGE_SIZE))
    except Exception as e:
        raise ErdError(f"could not list registries: {describe_error(e)}") from e
    status: dict[str, Any] = {"registries": {"status": "ok", "count": len(registries)}}
    schemas = await _crawl_schemas(b, status)
    dropdowns, organizations = await asyncio.gather(
        _crawl_section(b, _DROPDOWNS, status), _crawl_section(b, _ORGANIZATIONS, status)
    )
    return {
        "schemas": schemas,
        "dropdowns": dropdowns,
        "registries": [_wire(r) for r in registries],
        "organizations": organizations,
        "_status": _summarize_status(status),
        "_meta": {
            "tenant": _tenant_id(url),
            "tenantUrl": url,
            "crawledAt": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }

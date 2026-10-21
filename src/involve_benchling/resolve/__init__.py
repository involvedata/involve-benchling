"""Generic name -> object resolution over any Benchling V3 resource.

The V3 API exposes uniform ``list`` operations with consistent filter
parameters (``name_any_of``, ``schema_eq``, ...), so one helper works for
every resource -- no per-resource service classes::

    from involve_benchling import resolve

    plasmid = resolve.get_by_name(benchling.custom_entity, "pEX-001")
    schema = resolve.find_one(benchling.entity_schema, name_any_of=["Plasmid"])

Lookups raise :class:`~involve_benchling.errors.NotFoundError` or
:class:`~involve_benchling.errors.AmbiguousError` instead of returning
``None`` or silently picking the first match.
"""

from __future__ import annotations

import inspect
from typing import Any, Protocol, runtime_checkable

from ..errors import AmbiguousError, NotFoundError

__all__ = ["find_all", "find_one", "get_by_name", "get_id_by_name"]


@runtime_checkable
class ListableResource(Protocol):
    """Any SDK resource client with a ``list`` operation."""

    def list(self, **filters: Any) -> Any: ...


def _resource_name(resource: ListableResource) -> str:
    name = type(resource).__name__
    return name.removesuffix("Client") or name


def _supported_params(resource: ListableResource) -> set[str]:
    try:
        return set(inspect.signature(resource.list).parameters)
    except (TypeError, ValueError):  # pragma: no cover - builtins/mocks
        return set()


def find_all(resource: ListableResource, **filters: Any) -> list[Any]:
    """List every item matching the given server-side filters."""
    return list(resource.list(**filters))


def find_one(resource: ListableResource, **filters: Any) -> Any:
    """Return the single item matching ``filters``.

    Raises:
        NotFoundError: no item matched.
        AmbiguousError: more than one item matched.
    """
    items = []
    for item in resource.list(**filters):
        items.append(item)
        if len(items) > 1:
            break
    if not items:
        raise NotFoundError(_resource_name(resource), filters)
    if len(items) > 1:
        raise AmbiguousError(_resource_name(resource), filters, count=len(items))
    return items[0]


def get_by_name(
    resource: ListableResource,
    name: str,
    *,
    case_sensitive: bool = False,
    **filters: Any,
) -> Any:
    """Return the single item named ``name``.

    Uses the server-side ``name_any_of`` filter when the resource supports
    it, falling back to a client-side scan on ``.name`` otherwise. Extra
    ``filters`` (e.g. ``schema_eq=...``) narrow the search.
    """
    params = _supported_params(resource)
    criteria: dict[str, Any] = {"name": name, **filters}

    if case_sensitive and "name_any_of_case_sensitive" in params:
        return find_one(resource, name_any_of_case_sensitive=[name], **filters)
    if not case_sensitive and "name_any_of" in params:
        return find_one(resource, name_any_of=[name], **filters)

    # Client-side fallback for resources without a name filter.
    def matches(item: Any) -> bool:
        item_name = getattr(item, "name", None)
        if item_name is None:
            return False
        if case_sensitive:
            return bool(item_name == name)
        return bool(str(item_name).lower() == name.lower())

    matched = [item for item in resource.list(**filters) if matches(item)]
    if not matched:
        raise NotFoundError(_resource_name(resource), criteria)
    if len(matched) > 1:
        raise AmbiguousError(_resource_name(resource), criteria, count=len(matched))
    return matched[0]


def get_id_by_name(resource: ListableResource, name: str, **filters: Any) -> str:
    """Resolve a name to its Benchling ID."""
    item = get_by_name(resource, name, **filters)
    return str(item.id)

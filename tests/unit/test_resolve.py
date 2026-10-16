from dataclasses import dataclass

import pytest

from involve_benchling import AmbiguousError, NotFoundError, resolve


@dataclass
class Item:
    id: str
    name: str


class FilterableClient:
    """Mimics a V3 SDK resource client with server-side name filters."""

    def __init__(self, items):
        self._items = items
        self.calls = []

    def list(self, *, name_any_of=None, name_any_of_case_sensitive=None, schema_eq=None):
        self.calls.append(
            {"name_any_of": name_any_of, "cs": name_any_of_case_sensitive, "schema_eq": schema_eq}
        )
        items = self._items
        if name_any_of is not None:
            wanted = [n.lower() for n in name_any_of]
            items = [i for i in items if i.name.lower() in wanted]
        if name_any_of_case_sensitive is not None:
            items = [i for i in items if i.name in name_any_of_case_sensitive]
        yield from items


class BareClient:
    """A resource with no name filter support (client-side fallback)."""

    def __init__(self, items):
        self._items = items

    def list(self, **_filters):
        yield from self._items


ITEMS = [Item("ent_1", "Alpha"), Item("ent_2", "Beta"), Item("ent_3", "beta")]


def test_get_by_name_server_side():
    client = FilterableClient(ITEMS)
    item = resolve.get_by_name(client, "Alpha")
    assert item.id == "ent_1"
    assert client.calls[0]["name_any_of"] == ["Alpha"]


def test_get_by_name_case_sensitive_server_side():
    client = FilterableClient(ITEMS)
    assert resolve.get_by_name(client, "beta", case_sensitive=True).id == "ent_3"


def test_get_by_name_ambiguous():
    with pytest.raises(AmbiguousError) as exc:
        resolve.get_by_name(FilterableClient(ITEMS), "Beta")
    assert exc.value.count == 2


def test_get_by_name_not_found():
    with pytest.raises(NotFoundError):
        resolve.get_by_name(FilterableClient(ITEMS), "Gamma")


def test_get_by_name_client_side_fallback():
    assert resolve.get_by_name(BareClient(ITEMS), "ALPHA").id == "ent_1"


def test_get_by_name_client_side_case_sensitive():
    assert resolve.get_by_name(BareClient(ITEMS), "beta", case_sensitive=True).id == "ent_3"


def test_find_one_single_match():
    client = FilterableClient(ITEMS)
    assert resolve.find_one(client, name_any_of=["Alpha"]).id == "ent_1"


def test_find_one_stops_early_on_second_match():
    assert len(resolve.find_all(FilterableClient(ITEMS))) == 3


def test_get_id_by_name():
    assert resolve.get_id_by_name(FilterableClient(ITEMS), "Alpha") == "ent_1"

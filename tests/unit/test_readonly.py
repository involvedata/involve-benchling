import asyncio

import httpx
import pytest

from involve_benchling import BenchlingConfig, ConfigError, ReadOnlyViolationError, connect
from involve_benchling.core import connect_async
from involve_benchling.core.readonly import (
    AsyncReadOnlyTransport,
    ReadOnlyTransport,
    read_only_http_client,
)
from tests.fixtures.config import BASE_URL

TOKEN = {"access_token": "tok", "expires_in": 3600, "token_type": "Bearer"}
REGISTRIES = {"items": [], "nextToken": None}
SEARCH = {
    "hits": [],
    "metadata": {
        "queryId": "q",
        "searchedObjectTypes": [],
        "totalHits": {"relation": "eq", "value": 0},
    },
    "nextToken": "",
}


def _ok(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/oauth/token":
        return httpx.Response(200, json=TOKEN)
    if request.url.path == "/api/v3/search":
        return httpx.Response(200, json=SEARCH)
    return httpx.Response(200, json=REGISTRIES)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Replaces the network with a canned responder and records what reached it."""
    requests: list[httpx.Request] = []

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _ok(request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    return requests


def _client() -> httpx.Client:
    return httpx.Client(transport=ReadOnlyTransport(BASE_URL, inner=httpx.MockTransport(_ok)))


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_pass(method):
    assert _client().request(method, f"{BASE_URL}/api/v3/registry/items").status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_writes_blocked(method):
    with pytest.raises(ReadOnlyViolationError) as exc:
        _client().request(method, f"{BASE_URL}/api/v3/custom-entity/items")
    assert exc.value.method == method
    assert exc.value.url == f"{BASE_URL}/api/v3/custom-entity/items"


def test_token_exchange_allowed():
    assert _client().post(f"{BASE_URL}/oauth/token").status_code == 200


@pytest.mark.parametrize(
    "url",
    [
        "https://other.benchling.com/oauth/token",
        f"{BASE_URL}/api/v3/oauth/token",
        f"{BASE_URL}/oauth/token/extra",
    ],
)
def test_token_exemption_is_exact(url):
    with pytest.raises(ReadOnlyViolationError):
        _client().post(url)


def test_search_allowed():
    assert _client().post(f"{BASE_URL}/api/v3/search").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "api/v3/search/items",
        "api/v3/search:export",
        "api/v3/audit-log:export",
        "api/v3/bulk-export",
    ],
)
def test_only_exact_read_posts_allowed(path):
    with pytest.raises(ReadOnlyViolationError):
        _client().post(f"{BASE_URL}/{path}")


def test_connect_read_only_allows_sdk_search(sent):
    config = BenchlingConfig(base_url=BASE_URL, api_key="sk_test", read_only=True)
    connect(config).search.search_sync_custom(query="plasmid")
    assert [(r.method, r.url.path) for r in sent] == [("POST", "/api/v3/search")]


def test_token_exemption_ignores_query():
    assert _client().post(f"{BASE_URL}/oauth/token?x=1").status_code == 200


def test_async_transport_blocks_writes():
    async def run() -> None:
        transport = AsyncReadOnlyTransport(BASE_URL, inner=httpx.MockTransport(_ok))
        async with httpx.AsyncClient(transport=transport) as client:
            assert (await client.get(f"{BASE_URL}/api/v3/registry/items")).status_code == 200
            with pytest.raises(ReadOnlyViolationError):
                await client.delete(f"{BASE_URL}/api/v3/folder/items/lib_1")

    asyncio.run(run())


def test_read_only_http_client_follows_redirects():
    assert read_only_http_client(BASE_URL).follow_redirects is True


def test_connect_read_only_allows_reads(sent):
    config = BenchlingConfig(base_url=BASE_URL, api_key="sk_test", read_only=True)
    assert list(connect(config).registry.list()) == []
    assert [r.method for r in sent] == ["GET"]


def test_connect_read_only_blocks_sdk_writes(sent):
    config = BenchlingConfig(base_url=BASE_URL, api_key="sk_test", read_only=True)
    with pytest.raises(ReadOnlyViolationError):
        connect(config).folder.create(name="x", parent_id="lib_1")
    assert sent == []


def test_connect_read_only_oauth_fetches_token_then_blocks_writes(sent):
    config = BenchlingConfig(
        base_url=BASE_URL,
        oauth_client_id="client_id",
        oauth_client_secret="client_secret",
        read_only=True,
    )
    with pytest.raises(ReadOnlyViolationError):
        connect(config).folder.create(name="x", parent_id="lib_1")
    assert [(r.method, r.url.path) for r in sent] == [("POST", "/oauth/token")]


def test_connect_without_read_only_sends_writes(sent):
    config = BenchlingConfig(base_url=BASE_URL, api_key="sk_test")
    connect(config).folder.create(name="x", parent_id="lib_1")
    assert [r.method for r in sent] == ["POST"]


def test_connect_async_read_only_blocks_writes():
    config = BenchlingConfig(base_url=BASE_URL, api_key="sk_test", read_only=True)

    async def run() -> None:
        with pytest.raises(ReadOnlyViolationError):
            await connect_async(config).folder.create(name="x", parent_id="lib_1")

    asyncio.run(run())


@pytest.mark.parametrize("factory", [connect, connect_async])
def test_read_only_rejects_custom_httpx_client(factory):
    config = BenchlingConfig(base_url=BASE_URL, api_key="sk_test", read_only=True)
    with pytest.raises(ConfigError, match="httpx_client"):
        factory(config, httpx_client=httpx.Client())


def test_read_only_from_env(api_key_env, clean_env):
    clean_env.setenv("BENCHLING_READ_ONLY", "1")
    assert BenchlingConfig.from_env().read_only is True

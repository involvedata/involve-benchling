import asyncio

import httpx
import pytest

from involve_benchling import BenchlingConfig, ReadOnlyViolationError, connect
from involve_benchling.core import connect_async
from involve_benchling.core.client import _sync_transport
from involve_benchling.core.pacing import INITIAL_RATE, RATE_STEP
from involve_benchling.core.proxy import ProxyRules
from tests.fixtures.config import BASE_URL

PROXY = "http://proxy.example.com:3128"
REGISTRIES = {"items": [], "nextToken": None}


@pytest.fixture
def routes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str | None, str]]:
    """Replaces the network and records each request as ``(proxy, host)``."""
    sent: list[tuple[str | None, str]] = []

    def recorder(cls: type) -> None:
        init = cls.__init__

        def record_proxy(self, *args, proxy=None, **kwargs) -> None:
            init(self, *args, proxy=proxy, **kwargs)
            self.proxy_url = None if proxy is None else str(proxy)

        monkeypatch.setattr(cls, "__init__", record_proxy)

    def handle(self, request: httpx.Request) -> httpx.Response:
        sent.append((self.proxy_url, request.url.host))
        return httpx.Response(200, json=REGISTRIES)

    async def handle_async(self, request: httpx.Request) -> httpx.Response:
        return handle(self, request)

    recorder(httpx.HTTPTransport)
    recorder(httpx.AsyncHTTPTransport)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_async)
    return sent


def _read_only() -> BenchlingConfig:
    return BenchlingConfig(base_url=BASE_URL, api_key="sk_test", read_only=True)


def test_https_proxy_carries_requests(routes, clean_env):
    clean_env.setenv("HTTPS_PROXY", PROXY)
    assert list(connect(_read_only()).registry.list()) == []
    assert routes == [(PROXY, "example.benchling.com")]


def test_async_client_uses_the_proxy(routes, clean_env):
    clean_env.setenv("HTTPS_PROXY", PROXY)

    async def run() -> None:
        await connect_async(_read_only()).registry.list()

    asyncio.run(run())
    assert routes == [(PROXY, "example.benchling.com")]


def test_lowercase_and_all_proxy_variables_count(routes, clean_env):
    clean_env.setenv("all_proxy", PROXY)
    list(connect(_read_only()).registry.list())
    assert routes == [(PROXY, "example.benchling.com")]


def test_no_proxy_host_goes_direct(routes, clean_env):
    clean_env.setenv("HTTPS_PROXY", PROXY)
    clean_env.setenv("NO_PROXY", "localhost,benchling.com")
    list(connect(_read_only()).registry.list())
    assert routes == [(None, "example.benchling.com")]


def test_without_proxy_variables_requests_go_direct(routes):
    list(connect(_read_only()).registry.list())
    assert routes == [(None, "example.benchling.com")]


def test_blocked_write_never_reaches_the_proxy(routes, clean_env):
    clean_env.setenv("HTTPS_PROXY", PROXY)
    with pytest.raises(ReadOnlyViolationError):
        connect(_read_only()).folder.create(name="x", parent_id="lib_1")
    assert routes == []


def test_one_pacer_covers_proxied_and_direct_routes(routes, clean_env):
    clean_env.setenv("HTTPS_PROXY", PROXY)
    clean_env.setenv("NO_PROXY", "direct.example.com")
    transport, pacer = _sync_transport(_read_only())
    http = httpx.Client(transport=transport)
    http.get(f"{BASE_URL}/api/v3/registries")
    http.get("https://direct.example.com/api/v3/registries")
    assert routes == [(PROXY, "example.benchling.com"), (None, "direct.example.com")]
    assert pacer is not None
    assert pacer.rate == pytest.approx(INITIAL_RATE + 2 * RATE_STEP)


def test_unpaced_read_only_client_uses_the_proxy(routes, clean_env):
    clean_env.setenv("HTTPS_PROXY", PROXY)
    list(connect(_read_only().with_options(pacing=False)).registry.list())
    assert routes == [(PROXY, "example.benchling.com")]


def test_unreachable_proxy_fails_without_reaching_benchling(clean_env):
    clean_env.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    with pytest.raises(httpx.ConnectError):
        list(connect(_read_only(), max_retries=0).registry.list())


@pytest.mark.parametrize(
    ("entry", "url", "bypassed"),
    [
        ("example.com", "https://example.com/", True),
        ("example.com", "https://api.example.com/", True),
        ("example.com", "https://notexample.com/", False),
        (".example.com", "https://example.com/", False),
        (".example.com", "https://api.example.com/", True),
        ("example.com:8443", "https://example.com/", False),
        ("example.com:443", "https://example.com/", True),
        ("127.0.0.1", "http://127.0.0.1:8000/", True),
        ("::1", "http://[::1]/", True),
        ("localhost", "http://localhost/", True),
        ("http://example.com", "https://example.com/", False),
        ("https://example.com", "https://example.com/", True),
    ],
)
def test_no_proxy_entries_match_like_httpx(entry, url, bypassed):
    rules = ProxyRules({"all": PROXY}, (entry,))
    assert (rules.proxy_for(httpx.URL(url)) is None) is bypassed


def test_no_proxy_star_turns_proxies_off(clean_env):
    clean_env.setenv("HTTPS_PROXY", PROXY)
    clean_env.setenv("NO_PROXY", "*")
    assert ProxyRules.from_environment().proxies == {}


def test_scheme_proxy_beats_all_proxy(clean_env):
    clean_env.setenv("ALL_PROXY", "http://all.example.com")
    clean_env.setenv("HTTPS_PROXY", "proxy.example.com:3128")
    rules = ProxyRules.from_environment()
    assert rules.proxy_for(httpx.URL(BASE_URL)) == PROXY
    assert rules.proxy_for(httpx.URL("http://example.com")) == "http://all.example.com"

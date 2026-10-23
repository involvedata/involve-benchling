"""Environment proxies for the transports this library builds.

httpx reads proxy settings from the environment only when a client has no
transport of its own. Clients built by :func:`~involve_benchling.connect`
always pass one, so this module applies the same settings itself:

- ``HTTP_PROXY`` and ``HTTPS_PROXY`` proxy requests by URL scheme.
- ``ALL_PROXY`` proxies requests whose scheme has no proxy of its own.
- ``NO_PROXY`` lists hosts that bypass every proxy, and ``*`` turns proxies off.

Variables are read with :func:`urllib.request.getproxies`, as httpx does, so
lowercase names work and macOS and Windows fall back to system settings.
``NO_PROXY`` entries follow httpx too. ``example.com`` matches the domain
and its subdomains, ``.example.com`` only its subdomains, and IP addresses
and ``localhost`` match exactly. An entry may name a port or a scheme.

Settings are read once, when the transport is built.
"""

from __future__ import annotations

import ipaddress
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

__all__ = [
    "AsyncProxyTransport",
    "ProxyRules",
    "ProxyTransport",
    "async_http_transport",
    "http_transport",
]

_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class _Bypass:
    scheme: str
    host: str
    port: int | None

    @classmethod
    def parse(cls, entry: str) -> _Bypass:
        if "://" not in entry:
            if _is_ip(entry):
                entry = f"[{entry}]" if ":" in entry else entry
            elif entry.lower() != "localhost":
                entry = f"*{entry}"
            entry = f"all://{entry}"
        url = httpx.URL(entry)
        return cls(url.scheme, url.host, url.port)

    def matches(self, url: httpx.URL) -> bool:
        if self.scheme != "all" and self.scheme != url.scheme:
            return False
        if self.port is not None and self.port != _port(url):
            return False
        if self.host.startswith("*."):
            return url.host.endswith(self.host[1:])
        if self.host.startswith("*"):
            domain = self.host[1:]
            return url.host == domain or url.host.endswith(f".{domain}")
        return not self.host or url.host == self.host


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _port(url: httpx.URL) -> int | None:
    return url.port or _DEFAULT_PORTS.get(url.scheme)


@dataclass(frozen=True)
class ProxyRules:
    """Which proxy, if any, each request URL goes through.

    ``proxies`` maps a URL scheme, or ``"all"``, to a proxy URL. ``no_proxy``
    holds ``NO_PROXY`` entries.
    """

    proxies: Mapping[str, str] = field(default_factory=dict)
    no_proxy: tuple[str, ...] = ()
    _bypass: tuple[_Bypass, ...] = field(init=False, repr=False, compare=False)

    @classmethod
    def from_environment(cls) -> ProxyRules:
        """Read the rules from the proxy environment variables."""
        info = urllib.request.getproxies()
        no_proxy = tuple(e.strip() for e in info.get("no", "").split(",") if e.strip())
        if "*" in no_proxy:
            return cls()
        proxies = {
            scheme: value if "://" in value else f"http://{value}"
            for scheme in ("http", "https", "all")
            if (value := info.get(scheme))
        }
        return cls(proxies, no_proxy)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_bypass", tuple(_Bypass.parse(e) for e in self.no_proxy))

    def proxy_for(self, url: httpx.URL) -> str | None:
        """The proxy URL for a request to ``url``, or ``None`` to send it direct."""
        if any(b.matches(url) for b in self._bypass):
            return None
        return self.proxies.get(url.scheme) or self.proxies.get("all")


class ProxyTransport(httpx.BaseTransport):
    """Sync transport that sends each request direct or through its proxy."""

    def __init__(self, rules: ProxyRules | None = None) -> None:
        self.rules = rules or ProxyRules.from_environment()
        self._direct = httpx.HTTPTransport()
        self._proxied = {
            url: httpx.HTTPTransport(proxy=url) for url in set(self.rules.proxies.values())
        }

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        proxy = self.rules.proxy_for(request.url)
        transport = self._proxied[proxy] if proxy else self._direct
        return transport.handle_request(request)

    def close(self) -> None:
        self._direct.close()
        for transport in self._proxied.values():
            transport.close()


class AsyncProxyTransport(httpx.AsyncBaseTransport):
    """Async counterpart of :class:`ProxyTransport`."""

    def __init__(self, rules: ProxyRules | None = None) -> None:
        self.rules = rules or ProxyRules.from_environment()
        self._direct = httpx.AsyncHTTPTransport()
        self._proxied = {
            url: httpx.AsyncHTTPTransport(proxy=url) for url in set(self.rules.proxies.values())
        }

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        proxy = self.rules.proxy_for(request.url)
        transport = self._proxied[proxy] if proxy else self._direct
        return await transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self._direct.aclose()
        for transport in self._proxied.values():
            await transport.aclose()


def http_transport() -> httpx.BaseTransport:
    """A sync network transport that honours the proxy environment variables.

    Without proxy variables it is a plain ``httpx.HTTPTransport``.
    """
    rules = ProxyRules.from_environment()
    return ProxyTransport(rules) if rules.proxies else httpx.HTTPTransport()


def async_http_transport() -> httpx.AsyncBaseTransport:
    """Async counterpart of :func:`http_transport`."""
    rules = ProxyRules.from_environment()
    return AsyncProxyTransport(rules) if rules.proxies else httpx.AsyncHTTPTransport()

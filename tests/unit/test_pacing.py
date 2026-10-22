import asyncio
import threading
import time

import httpx
import pytest

from involve_benchling import BenchlingConfig, ConfigError, ReadOnlyViolationError, connect
from involve_benchling.core import connect_async, pacer_for
from involve_benchling.core.pacing import (
    INITIAL_RATE,
    MAX_PAUSE,
    MAX_RATE,
    MIN_RATE,
    RATE_STEP,
    AsyncPacedTransport,
    PacedTransport,
    Pacer,
)
from tests.fixtures.config import BASE_URL
from tests.fixtures.fakes import FakeClock

URL = f"{BASE_URL}/api/v3/registry/items"
REGISTRIES = {"items": [], "nextToken": None}


REQUEST = httpx.Request("GET", URL)


def _response(status: int, **headers: str) -> httpx.Response:
    return httpx.Response(status, headers=headers)


def pacer_of(client: httpx.Client) -> Pacer:
    return client._transport.pacer


def _paced(clock: FakeClock, responses: list[httpx.Response], **kwargs) -> httpx.Client:
    """A paced client that answers with ``responses`` in order, then ``200``."""

    def answer(request: httpx.Request) -> httpx.Response:
        return responses.pop(0) if responses else httpx.Response(200, json=REGISTRIES)

    pacer = Pacer(kwargs.pop("max_concurrency", 4), clock=clock.monotonic, **kwargs)
    transport = PacedTransport(pacer, httpx.MockTransport(answer), sleep=clock.sleep)
    return httpx.Client(transport=transport)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def test_success_sends_without_waiting(clock):
    client = _paced(clock, [])
    assert client.get(URL).status_code == 200
    assert clock.slept == []


def test_retry_after_pauses_the_next_request(clock):
    client = _paced(clock, [httpx.Response(429, headers={"Retry-After": "2"})], max_retries=0)
    assert client.get(URL).status_code == 429
    assert client.get(URL).status_code == 200
    assert clock.slept == [2.0]


def test_retry_after_pauses_every_request_on_the_client(clock):
    client = _paced(clock, [httpx.Response(429, headers={"Retry-After": "2"})], max_retries=0)
    client.get(URL)
    clock.advance(0.5)
    client.get(f"{BASE_URL}/api/v3/folder/items")
    assert clock.slept == [1.5]


def test_retry_after_accepts_an_http_date(monkeypatch, clock):
    monkeypatch.setattr(time, "time", lambda: 1_000.0)
    pacer = Pacer(4, clock=clock.monotonic)
    pacer.record(REQUEST, _response(429, **{"Retry-After": "Thu, 01 Jan 1970 00:16:45 GMT"}))
    assert pacer.wait_time() == pytest.approx(5.0)


def test_backoff_without_retry_after_doubles_up_to_the_cap(clock):
    pacer = Pacer(4, clock=clock.monotonic, jitter=lambda: 1.0)
    pauses = []
    for _ in range(9):
        pacer.record(REQUEST, _response(429))
        pauses.append(pacer.wait_time())
        clock.advance(pauses[-1])
    assert pauses == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, MAX_PAUSE, MAX_PAUSE, MAX_PAUSE]


def test_backoff_jitter_shortens_the_pause(clock):
    pacer = Pacer(4, clock=clock.monotonic, jitter=lambda: 0.0)
    pacer.record(REQUEST, _response(429))
    clock.advance(0.5)
    pacer.record(REQUEST, _response(429))
    assert pacer.wait_time() == pytest.approx(1.0)


def test_success_resets_the_backoff(clock):
    pacer = Pacer(4, clock=clock.monotonic, jitter=lambda: 1.0)
    for _ in range(3):
        pacer.record(REQUEST, _response(429))
        clock.advance(pacer.wait_time())
    pacer.record(REQUEST, _response(200))
    pacer.record(REQUEST, _response(429))
    assert pacer.wait_time() == 1.0


def test_a_shorter_retry_after_never_cuts_a_pause(clock):
    pacer = Pacer(4, clock=clock.monotonic)
    pacer.record(REQUEST, _response(429, **{"Retry-After": "10"}))
    pacer.record(REQUEST, _response(429, **{"Retry-After": "1"}))
    assert pacer.wait_time() == 10.0


def test_throttled_counts_429s(clock):
    pacer = Pacer(4, clock=clock.monotonic)
    for status in (200, 429, 200, 429):
        pacer.record(REQUEST, _response(status, **{"Retry-After": "0"}))
    assert pacer.throttled == 2


def test_429_is_logged(clock, caplog):
    Pacer(4, clock=clock.monotonic).record(REQUEST, _response(429, **{"Retry-After": "3"}))
    assert "pausing requests for 3.0s" in caplog.text


def test_429_halves_the_cap(clock):
    pacer = Pacer(8, clock=clock.monotonic)
    pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}))
    assert pacer.limit == 4


def test_cap_never_drops_below_one(clock):
    pacer = Pacer(2, clock=clock.monotonic)
    for _ in range(3):
        pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}))
    assert pacer.limit == 1


def test_a_burst_of_429s_halves_the_cap_once(clock):
    pacer = Pacer(8, clock=clock.monotonic)
    sent_at = clock.monotonic()
    clock.advance(1)
    for _ in range(5):
        pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}), sent_at)
    assert pacer.limit == 4


def test_a_429_after_the_cut_halves_again(clock):
    pacer = Pacer(8, clock=clock.monotonic)
    pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}), clock.monotonic())
    clock.advance(1)
    pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}), clock.monotonic())
    assert pacer.limit == 2


def test_successes_grow_the_cap_back_to_the_maximum(clock):
    pacer = Pacer(8, clock=clock.monotonic)
    pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}))
    limits = []
    for _ in range(40):
        pacer.record(REQUEST, _response(200))
        limits.append(pacer.limit)
    assert limits[:4] == [4, 4, 4, 5]
    assert limits[8] == 6
    assert max(limits) == pacer.limit == 8


async def _yield(seconds: float) -> None:
    await asyncio.sleep(0)


def _peak(pacer: Pacer, calls: int) -> int:
    """Sends ``calls`` requests from threads and returns the most in flight at once."""
    lock = threading.Lock()
    in_flight = peak = 0
    arrived = threading.Semaphore(0)
    release = threading.Event()

    def answer(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        arrived.release()
        release.wait(timeout=5)
        with lock:
            in_flight -= 1
        return httpx.Response(200)

    transport = PacedTransport(pacer, httpx.MockTransport(answer), sleep=lambda _: None)
    client = httpx.Client(transport=transport)
    threads = [threading.Thread(target=client.get, args=(URL,)) for _ in range(calls)]
    for thread in threads:
        thread.start()
    for _ in range(pacer.limit):
        assert arrived.acquire(timeout=5)
    release.set()
    for thread in threads:
        thread.join(timeout=5)
    return peak


def test_transport_honours_a_lowered_cap():
    pacer = Pacer(4)
    for _ in range(2):
        pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}))
    assert pacer.limit == 1
    assert _peak(pacer, 6) == 1


def test_async_transport_caps_concurrency():
    in_flight = peak = 0

    async def answer(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        in_flight -= 1
        return httpx.Response(200)

    async def run() -> None:
        transport = AsyncPacedTransport(Pacer(2), httpx.MockTransport(answer), sleep=_yield)
        async with httpx.AsyncClient(transport=transport) as client:
            await asyncio.gather(*(client.get(URL) for _ in range(6)))

    asyncio.run(run())
    assert peak == 2


def test_429_halves_the_rate(clock):
    pacer = Pacer(4, clock=clock.monotonic)
    pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}))
    assert pacer.rate == INITIAL_RATE / 2


def test_rate_never_drops_below_the_floor(clock):
    pacer = Pacer(4, clock=clock.monotonic, initial_rate=MIN_RATE)
    pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}))
    assert pacer.rate == MIN_RATE


def test_successes_raise_the_rate_up_to_the_ceiling(clock):
    pacer = Pacer(4, clock=clock.monotonic)
    pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}))
    pacer.record(REQUEST, _response(200))
    assert pacer.rate == pytest.approx(INITIAL_RATE / 2 + RATE_STEP)
    for _ in range(500):
        pacer.record(REQUEST, _response(200))
    assert pacer.rate == MAX_RATE


def test_a_burst_of_429s_halves_the_rate_once(clock):
    pacer = Pacer(4, clock=clock.monotonic)
    sent_at = clock.monotonic()
    clock.advance(1)
    for _ in range(4):
        pacer.record(REQUEST, _response(429, **{"Retry-After": "0"}), sent_at)
    assert pacer.rate == INITIAL_RATE / 2


def test_requests_are_spaced_to_the_rate(clock):
    client = _paced(clock, [])
    for _ in range(3):
        client.get(URL)
    first, second = 1 / INITIAL_RATE, 1 / (INITIAL_RATE + RATE_STEP)
    assert clock.slept == pytest.approx([first, second])


def test_spacing_widens_after_a_429(clock):
    client = _paced(clock, [httpx.Response(429, headers={"Retry-After": "0"})], max_retries=0)
    client.get(URL)
    clock.advance(1)
    client.get(URL)
    client.get(URL)
    assert clock.slept == pytest.approx([2 / INITIAL_RATE])


def test_429_is_resent_until_it_succeeds(clock):
    rejected = [httpx.Response(429, headers={"Retry-After": "1"}) for _ in range(2)]
    client = _paced(clock, rejected)
    assert client.get(URL).status_code == 200
    assert pacer_of(client).throttled == 2
    assert sum(clock.slept) >= 2.0


def test_429_retries_stop_at_max_retries(clock):
    rejected = [httpx.Response(429, headers={"Retry-After": "0"}) for _ in range(5)]
    client = _paced(clock, rejected, max_retries=2)
    assert client.get(URL).status_code == 429
    assert pacer_of(client).throttled == 3


def test_a_rejected_write_is_resent_with_its_body(clock):
    seen: list[tuple[str, bytes]] = []
    responses = [httpx.Response(429, headers={"Retry-After": "0"})]

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.content))
        return responses.pop(0) if responses else httpx.Response(201)

    pacer = Pacer(4, clock=clock.monotonic)
    transport = PacedTransport(pacer, httpx.MockTransport(answer), sleep=clock.sleep)
    response = httpx.Client(transport=transport).post(URL, json={"name": "x"})
    assert response.status_code == 201
    assert seen == [("POST", b'{"name":"x"}')] * 2


def test_async_transport_resends_a_429(clock):
    responses = [httpx.Response(429, headers={"Retry-After": "1"})]

    def answer(request: httpx.Request) -> httpx.Response:
        return responses.pop(0) if responses else httpx.Response(200)

    async def run() -> int:
        pacer = Pacer(4, clock=clock.monotonic)
        transport = AsyncPacedTransport(pacer, httpx.MockTransport(answer), sleep=clock.async_sleep)
        async with httpx.AsyncClient(transport=transport) as client:
            return (await client.get(URL)).status_code

    assert asyncio.run(run()) == 200
    assert clock.slept == [1.0]


def test_concurrency_is_capped():
    assert _peak(Pacer(2), 6) == 2


def test_async_transport_shares_the_pause(clock):
    responses = [httpx.Response(429, headers={"Retry-After": "2"})]

    def answer(request: httpx.Request) -> httpx.Response:
        return responses.pop(0) if responses else httpx.Response(200)

    async def run() -> list[int]:
        pacer = Pacer(4, clock=clock.monotonic, max_retries=0)
        transport = AsyncPacedTransport(pacer, httpx.MockTransport(answer), sleep=clock.async_sleep)
        async with httpx.AsyncClient(transport=transport) as client:
            return [(await client.get(URL)).status_code for _ in range(2)]

    assert asyncio.run(run()) == [429, 200]
    assert clock.slept == [2.0]


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> list[httpx.Response]:
    """Replaces the network and the clock; returns responses to send before ``200``."""
    queued: list[httpx.Response] = []
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    monkeypatch.setattr(time, "sleep", clock.sleep)

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        return queued.pop(0) if queued else httpx.Response(200, json=REGISTRIES)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    return queued


def test_connect_paces_by_default(network, api_key_config):
    assert pacer_for(connect(api_key_config)) is not None


def test_sdk_retry_waits_out_the_shared_pause_once(network, clock, api_key_config):
    network.append(httpx.Response(429, headers={"Retry-After": "3"}))
    benchling = connect(api_key_config)
    assert list(benchling.registry.list()) == []
    assert pacer_for(benchling).throttled == 1
    assert sum(clock.slept) == pytest.approx(3.0)


def test_clients_do_not_share_a_pacer(api_key_config):
    assert pacer_for(connect(api_key_config)) is not pacer_for(connect(api_key_config))


def test_connect_uses_max_concurrency(api_key_config):
    config = api_key_config.with_options(max_concurrency=7)
    assert pacer_for(connect(config)).max_concurrency == 7


def test_blocked_write_never_waits(network, clock):
    config = BenchlingConfig(base_url=BASE_URL, api_key="sk_test", read_only=True)
    benchling = connect(config)
    pacer_for(benchling).record(REQUEST, _response(429, **{"Retry-After": "30"}))
    with pytest.raises(ReadOnlyViolationError):
        benchling.folder.create(name="x", parent_id="lib_1")
    assert clock.slept == []


def test_pacing_off_builds_an_unpaced_client(api_key_config):
    benchling = connect(api_key_config.with_options(pacing=False))
    assert pacer_for(benchling) is None


def test_pacing_off_accepts_a_custom_httpx_client(api_key_config):
    connect(api_key_config.with_options(pacing=False), httpx_client=httpx.Client())


@pytest.mark.parametrize("factory", [connect, connect_async])
def test_pacing_rejects_custom_httpx_client(factory, api_key_config):
    with pytest.raises(ConfigError, match="pacing=False"):
        factory(api_key_config, httpx_client=httpx.Client())


def test_connect_async_paces_by_default(api_key_config):
    assert pacer_for(connect_async(api_key_config)) is not None


def test_pacing_from_env(api_key_env, clean_env):
    assert BenchlingConfig.from_env().pacing is True
    clean_env.setenv("BENCHLING_PACING", "0")
    assert BenchlingConfig.from_env().pacing is False


def test_max_concurrency_from_env(api_key_env, clean_env):
    clean_env.setenv("BENCHLING_MAX_CONCURRENCY", "2")
    assert BenchlingConfig.from_env().max_concurrency == 2


def test_max_concurrency_env_must_be_an_integer(api_key_env, clean_env):
    clean_env.setenv("BENCHLING_MAX_CONCURRENCY", "many")
    with pytest.raises(ConfigError, match="integer"):
        BenchlingConfig.from_env()


@pytest.mark.parametrize("value", [0, -1])
def test_max_concurrency_must_be_positive(value):
    with pytest.raises(ConfigError, match="max_concurrency"):
        BenchlingConfig(base_url=BASE_URL, api_key="k", max_concurrency=value)


def test_max_retries_defaults_to_eight(api_key_config):
    assert api_key_config.max_retries == 8
    assert pacer_for(connect(api_key_config)).max_retries == 8


def test_max_retries_from_env(api_key_env, clean_env):
    clean_env.setenv("BENCHLING_MAX_RETRIES", "3")
    config = BenchlingConfig.from_env()
    assert config.max_retries == 3
    assert pacer_for(connect(config)).max_retries == 3


def test_explicit_max_retries_beats_env(api_key_env, clean_env):
    clean_env.setenv("BENCHLING_MAX_RETRIES", "3")
    assert BenchlingConfig.from_env(max_retries=5).max_retries == 5


def test_max_retries_must_not_be_negative():
    with pytest.raises(ConfigError, match="max_retries"):
        BenchlingConfig(base_url=BASE_URL, api_key="k", max_retries=-1)


def test_max_retries_env_must_be_an_integer(api_key_env, clean_env):
    clean_env.setenv("BENCHLING_MAX_RETRIES", "lots")
    with pytest.raises(ConfigError, match="integer"):
        BenchlingConfig.from_env()


def test_sdk_keeps_its_own_retries(api_key_config):
    assert connect(api_key_config)._client_wrapper._max_retries == 2
    benchling = connect(api_key_config, max_retries=5)
    assert benchling._client_wrapper._max_retries == 5
    assert pacer_for(benchling).max_retries == 8

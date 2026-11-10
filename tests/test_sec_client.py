import httpx
import pytest

from pitwh.client import MAX_TRIES, TokenBucket, fetch_cached
from pitwh.sec import SecClient


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_token_bucket_burst_never_exceeds_rate():
    clock = FakeClock()
    bucket = TokenBucket(rate=8, clock=clock, sleep=clock.sleep)
    sent_at = []
    for _ in range(100):
        bucket.acquire()
        sent_at.append(clock.now)

    # No one-second window may contain more than 8 requests (SEC hard limit is 10).
    for i, t in enumerate(sent_at):
        in_window = sum(1 for u in sent_at[i:] if u < t + 1.0)
        assert in_window <= 8
    assert clock.now == pytest.approx(99 / 8)


def _client(handler, **kw) -> SecClient:
    return SecClient(
        "Test Person test@example.com",
        rate=1000,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
        **kw,
    )


def test_user_agent_header_is_sent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers["User-Agent"]
        return httpx.Response(200, json={"ok": True})

    _client(handler).get_json("https://data.sec.gov/x")
    assert seen["ua"] == "Test Person test@example.com"


def test_user_agent_without_contact_is_rejected():
    with pytest.raises(ValueError):
        SecClient("pitwh")


def test_retries_503_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"v": 1})

    assert _client(handler).get_json("https://data.sec.gov/x") == {"v": 1}
    assert len(calls) == 3


def test_gives_up_after_max_tries():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429)

    with pytest.raises(RuntimeError):
        _client(handler).get_json("https://data.sec.gov/x")
    assert len(calls) == MAX_TRIES


def test_404_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        _client(handler).get_json("https://data.sec.gov/x")
    assert len(calls) == 1


def test_cache_hit_skips_network(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"n": len(calls)})

    client = _client(handler)
    path = tmp_path / "CIK0000000001.json"
    assert fetch_cached(client, "https://data.sec.gov/x", path) == {"n": 1}
    assert fetch_cached(client, "https://data.sec.gov/x", path) == {"n": 1}
    assert len(calls) == 1
    assert fetch_cached(client, "https://data.sec.gov/x", path, refresh=True) == {"n": 2}

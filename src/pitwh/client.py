"""Throttled JSON-over-HTTP client and an on-disk response cache, shared by SEC and Tiingo."""

import json
import logging
import random
import time
from collections.abc import Callable
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_TRIES = 5


class TokenBucket:
    """Blocks until a request may be sent at no more than `rate` per second."""

    # A bucket holding N tokens could send N at once and then N more within the
    # same window, doubling the effective rate, so capacity stays at 1.
    def __init__(
        self,
        rate: float,
        capacity: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.clock = clock
        self.sleep = sleep
        self.last = clock()

    def _refill(self) -> None:
        now = self.clock()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now

    def acquire(self) -> None:
        self._refill()
        if self.tokens < 1:
            self.sleep((1 - self.tokens) / self.rate)
            self._refill()
        self.tokens -= 1


class JsonClient:
    """GETs JSON at a fixed maximum rate, retrying 429/5xx and transport errors."""

    def __init__(
        self,
        headers: dict[str, str],
        rate: float,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.http = httpx.Client(headers=headers, timeout=30.0, transport=transport)
        self.bucket = TokenBucket(rate, sleep=sleep)
        self.sleep = sleep

    def get_json(self, url: str, params: dict | None = None) -> dict | list:
        for attempt in range(1, MAX_TRIES + 1):
            self.bucket.acquire()
            try:
                resp = self.http.get(url, params=params)
            except httpx.TransportError as exc:
                log.warning("%s transport error on try %d: %s", url, attempt, exc)
            else:
                if resp.status_code not in RETRY_STATUSES:
                    resp.raise_for_status()
                    return resp.json()
                log.warning("%s returned %d on try %d", url, resp.status_code, attempt)
            if attempt < MAX_TRIES:
                self.sleep(min(2**attempt, 60) * random.uniform(0.5, 1.0))
        raise RuntimeError(f"request failed after {MAX_TRIES} tries: {url}")


def fetch_cached(
    client: JsonClient, url: str, path: Path, refresh: bool = False, params: dict | None = None
) -> dict | list:
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    data = client.get_json(url, params)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)
    return data

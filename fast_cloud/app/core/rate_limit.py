from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class RateLimit:
    attempts: int
    window_seconds: int


class InMemoryRateLimiter:
    """Small process-local limiter for sensitive public endpoints.

    FAST Cloud currently runs as a single Uvicorn process in the supported
    desktop/self-hosted setup. If Cloud later moves to multiple workers or
    containers this can be swapped for a shared Redis-backed implementation
    without changing the route contracts.
    """

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def enforce(self, key: str, limit: RateLimit) -> None:
        now = monotonic()
        cutoff = now - limit.window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit.attempts:
                retry_after = max(1, int(bucket[0] + limit.window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please wait before trying again.",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)


limiter = InMemoryRateLimiter()


def client_address(request: Request) -> str:
    # Do not trust X-Forwarded-For here unless FAST Cloud is explicitly placed
    # behind a trusted reverse proxy. request.client is safe for the current
    # local/self-hosted deployment model.
    return request.client.host if request.client else "unknown"

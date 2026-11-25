"""Simple in-process sliding-window rate limiter keyed by client IP.

Adequate for a single-process deployment. Behind multiple workers or replicas use a shared
store (e.g. Redis) or rate limit at the reverse proxy instead.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import UTC, date, datetime

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                retry = max(1, int(self.window - (now - q[0])) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please slow down.",
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class DailyQuota:
    """Global (all clients) per-UTC-day counter, used to cap LLM spend in demo mode."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._day: date | None = None
        self._used = 0
        self._lock = threading.Lock()

    def consume(self) -> None:
        today = datetime.now(UTC).date()
        with self._lock:
            if self._day != today:
                self._day, self._used = today, 0
            if self._used >= self.limit:
                raise HTTPException(
                    status_code=429,
                    detail="This demo has reached its daily question limit. Please come back "
                    "tomorrow.",
                )
            self._used += 1

    @property
    def remaining(self) -> int:
        with self._lock:
            if self._day != datetime.now(UTC).date():
                return self.limit
            return max(0, self.limit - self._used)


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"

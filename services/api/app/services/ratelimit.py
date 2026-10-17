"""A tiny in-process rate limiter.

Deliberately small: the live-voice endpoints are per-user and the goal is to
stop one account burning the shared Gemini quota, not to build a distributed
limiter. It is a sliding-window counter held in memory, so a multi-process
deployment enforces the limit per worker — documented, not hidden. Moving to
Redis later is a drop-in replacement behind the same three methods.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """Allow at most `limit` events per `window_seconds` per key."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = max(1, int(limit))
        self.window = float(window_seconds)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record an event and report whether it is within the limit.

        The event is recorded even when it is rejected, so a client that hammers
        the endpoint keeps its window full rather than resetting it."""
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            allowed = len(hits) < self.limit
            hits.append(now)
            # Drop keys that are no longer active so the map cannot grow forever.
            if not hits:
                self._hits.pop(key, None)
            return allowed

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

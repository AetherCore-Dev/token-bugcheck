"""In-memory TTL cache for audit reports."""

from __future__ import annotations

import time
from collections import OrderedDict

from rugcheck.models import AuditReport


class TTLCache:
    """Simple in-memory cache with per-entry TTL and LRU eviction."""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 10_000):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._store: OrderedDict[str, tuple[float, AuditReport]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> AuditReport | None:
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        ts, report = entry
        if time.monotonic() - ts > self.ttl:
            del self._store[key]
            self._misses += 1
            return None

        # Move to end (most recently used)
        self._store.move_to_end(key)
        self._hits += 1
        return report

    def set(self, key: str, report: AuditReport) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.monotonic(), report)

        # Evict oldest if over capacity
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    @property
    def stats(self) -> dict:
        return {
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(self._hits + self._misses, 1) * 100, 1),
        }

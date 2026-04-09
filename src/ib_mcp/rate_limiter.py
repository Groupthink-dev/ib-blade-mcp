"""Rate limiter for the IB Client Portal Gateway API.

The CP Gateway enforces per-second request limits and concurrent connection
limits. Market data snapshots have additional throttling: first request
for a conid subscribes to data and may return stale/empty values.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# IB CP Gateway limits (approximate — not formally documented)
MAX_CONCURRENT = 5
MAX_REQUESTS_PER_SECOND = 10
SNAPSHOT_COOLDOWN = 1.0  # seconds between snapshot requests for same conids


@dataclass
class RateLimiter:
    """Concurrent-request limiter for the IB Client Portal Gateway.

    Enforces a concurrency ceiling via asyncio semaphore and tracks
    request throughput for observability.
    """

    _semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(MAX_CONCURRENT))
    _request_count: int = 0
    _last_reset: float = field(default_factory=time.time)
    _last_snapshot_at: float = 0.0

    async def acquire(self) -> None:
        """Acquire a request slot (blocks if limit reached)."""
        await self._semaphore.acquire()
        self._request_count += 1

    def release(self) -> None:
        """Release a request slot."""
        self._semaphore.release()

    async def snapshot_throttle(self) -> None:
        """Enforce minimum delay between market data snapshot requests."""
        elapsed = time.time() - self._last_snapshot_at
        if elapsed < SNAPSHOT_COOLDOWN:
            await asyncio.sleep(SNAPSHOT_COOLDOWN - elapsed)
        self._last_snapshot_at = time.time()

    def get_status(self) -> dict[str, int | float]:
        """Return current rate limit status."""
        return {
            "concurrent_available": self._semaphore._value,
            "concurrent_max": MAX_CONCURRENT,
            "requests_since_reset": self._request_count,
        }

    def format_status(self) -> str:
        """Format rate limit status as a compact string."""
        status = self.get_status()
        return f"concurrent={status['concurrent_available']}/{status['concurrent_max']}"

"""Async token-bucket rate limiter for per-provider request throttling."""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class AsyncRateLimiter:
    """Async token-bucket rate limiter that caps throughput to a target RPM.

    The bucket starts full.  Each :meth:`acquire` call consumes one token.
    When the bucket is empty the caller is suspended until enough time has
    elapsed for at least one new token to have accrued.

    The implementation is safe for concurrent use within a single event-loop
    because all shared state is protected by an :class:`asyncio.Lock`.

    Args:
        requests_per_minute: Maximum number of requests allowed per 60-second
            window.  Must be a positive number.

    Example::

        limiter = AsyncRateLimiter(requests_per_minute=60)

        async def call_api():
            await limiter.acquire()
            return await provider.complete(messages, params)
    """

    def __init__(self, requests_per_minute: float) -> None:
        if requests_per_minute <= 0:
            raise ValueError(
                f"requests_per_minute must be positive, got {requests_per_minute}."
            )
        self._rpm = requests_per_minute
        # Seconds between consecutive token accruals (one token = one request slot).
        self._interval: float = 60.0 / requests_per_minute
        # Current token count; starts at capacity (full bucket).
        self._tokens: float = requests_per_minute
        # Maximum tokens the bucket can hold (burst ceiling).
        self._capacity: float = requests_per_minute
        # Monotonic timestamp of the last token-refill check.
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def acquire(self) -> None:
        """Block until a request token is available, then consume it.

        The caller will wait for at most ``60 / requests_per_minute`` seconds
        when the bucket is exhausted.

        This method is safe to call concurrently from multiple coroutines.
        """
        async with self._lock:
            self._refill()
            if self._tokens < 1.0:
                wait_seconds = (1.0 - self._tokens) * self._interval
                logger.debug(
                    "Rate limit reached (%.0f RPM). Waiting %.2fs.",
                    self._rpm,
                    wait_seconds,
                )
                # Release the lock while sleeping so other coroutines can
                # reach this point and queue behind the same sleep window.
                # We re-acquire it before touching shared state again.
                self._lock.release()
                try:
                    await asyncio.sleep(wait_seconds)
                finally:
                    await self._lock.acquire()
                # Refill again after sleeping; time has advanced.
                self._refill()

            self._tokens -= 1.0

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AsyncRateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        pass  # No release needed for rate limiting

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def requests_per_minute(self) -> float:
        """The configured rate limit in requests per minute."""
        return self._rpm

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens (snapshot, not synchronized)."""
        return self._tokens

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refill(self) -> None:
        """Add tokens proportional to elapsed time since the last refill.

        Must be called while the lock is held.
        """
        now = time.monotonic()
        elapsed = now - self._last_refill
        # Tokens accrue at a rate of ``rpm / 60`` tokens per second.
        accrued = elapsed / self._interval
        self._tokens = min(self._capacity, self._tokens + accrued)
        self._last_refill = now

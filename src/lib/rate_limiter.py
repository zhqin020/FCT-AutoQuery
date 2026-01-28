"""Rate limiting utilities for ethical web scraping."""

import time
import random
from typing import Optional
from loguru import logger


class RateLimiter:
    """Implements rate limiting for web scraping operations."""

    def __init__(self, min_interval_seconds: float = 3.0, max_interval_seconds: float = 6.0):
        """Initialize rate limiter with random delay.

        Args:
            min_interval_seconds: Minimum interval between requests (default: 3.0)
            max_interval_seconds: Maximum interval between requests (default: 6.0)
        """
        self.min_interval_seconds = min_interval_seconds
        self.max_interval_seconds = max_interval_seconds
        self.last_request_time: Optional[float] = None

    def wait_if_needed(self) -> float:
        """Wait if necessary to maintain rate limit with random delay.

        Returns:
            float: Actual wait time in seconds
        """
        if self.last_request_time is None:
            wait_time = 0.0
        else:
            elapsed = time.time() - self.last_request_time
            required_delay = random.uniform(self.min_interval_seconds, self.max_interval_seconds)
            wait_time = max(0.0, required_delay - elapsed)

        if wait_time > 0:
            logger.debug(".2f")
            time.sleep(wait_time)

        self.last_request_time = time.time()
        return wait_time

    def reset(self) -> None:
        """Reset the rate limiter (useful for testing)."""
        self.last_request_time = None


class EthicalRateLimiter(RateLimiter):
    """Rate limiter specifically designed for ethical web scraping.

    This implementation keeps a simple, test-friendly surface:
    - `interval_seconds`: fixed interval between requests
    - `max_burst`: how many immediate requests are allowed in a short burst
    - `validate_ethical_delay(actual_delay)`: returns True if the provided delay
      meets or exceeds the configured ethical interval.
    """

    def __init__(
        self,
        interval_seconds: float = 1.0,
        max_burst: int = 1,
        backoff_factor: float = 1.0,
        max_backoff_seconds: float = 60.0,
    ):
        """Initialize ethical rate limiter with fixed interval.

        Args:
            interval_seconds: Fixed interval between requests (default: 1.0)
            max_burst: Number of allowed immediate requests in a burst (default: 1)
        """
        super().__init__(min_interval_seconds=interval_seconds, max_interval_seconds=interval_seconds)
        self.interval_seconds = interval_seconds
        self.max_burst = int(max_burst)
        # Backoff configuration
        self.failure_count = 0
        self.backoff_factor = float(backoff_factor)
        self.max_backoff_seconds = float(max_backoff_seconds)

    def wait_if_needed(self) -> float:
        """Wait with fixed ethical scraping interval."""
        if self.last_request_time is None:
            wait_time = 0.0
        else:
            elapsed = time.time() - self.last_request_time
            wait_time = max(0.0, self.interval_seconds - elapsed)

        if wait_time > 0:
            logger.debug("Waiting for %0.2fs to respect ethical interval", wait_time)
            time.sleep(wait_time)

        self.last_request_time = time.time()
        return wait_time

    def validate_ethical_delay(self, actual_delay: float) -> bool:
        """Return True if `actual_delay` meets the configured ethical delay.

        For now this simply checks actual_delay >= interval_seconds.
        """
        try:
            return float(actual_delay) >= float(self.interval_seconds)
        except Exception:
            return False

    # Backoff helpers
    def record_failure(self, status_code: int | None = None) -> float:
        """Record a failure occurrence and return the next backoff delay.

        Args:
            status_code: Optional HTTP status code observed (e.g., 429, 503)

        Returns:
            float: computed backoff delay in seconds
        """
        # Increase failure count
        self.failure_count = (self.failure_count or 0) + 1

        # If server explicitly signals throttling (429/503), treat as a stronger signal
        multiplier = 2.0 if status_code in (429, 503) else 1.0

        delay = min(self.max_backoff_seconds, self.backoff_factor * multiplier * (2 ** (self.failure_count - 1)))
        return delay

    def reset_failures(self) -> None:
        """Reset failure counter (after a successful request or manual reset)."""
        self.failure_count = 0

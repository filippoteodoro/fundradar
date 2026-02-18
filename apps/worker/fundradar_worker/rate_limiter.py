"""
Rate limiting for Fundradar scraping.

Provides per-domain and global rate limiting with priority queuing.
"""

import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from heapq import heappush, heappop
from typing import Callable, Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    # Default delay between requests to the same domain (seconds)
    default_delay: float = 2.0

    # Global rate limit (requests per minute across all domains)
    # We fetch from ~100+ different domains, not one server.
    # Per-domain 2s delay already throttles individual sites.
    global_requests_per_minute: int = 120

    # Per-domain overrides: domain -> delay in seconds
    domain_delays: dict[str, float] = field(default_factory=dict)

    # Priority levels (lower = higher priority)
    priority_high: int = 0
    priority_normal: int = 5
    priority_low: int = 10

    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        """Load config from environment variables."""
        return cls(
            default_delay=float(os.environ.get("FUNDRADAR_RATE_LIMIT_DEFAULT", "2.0")),
            global_requests_per_minute=int(os.environ.get("FUNDRADAR_GLOBAL_RATE_LIMIT", "120")),
        )


@dataclass(order=True)
class QueuedRequest:
    """A request waiting in the queue."""

    priority: int
    enqueued_at: float = field(compare=False)
    domain: str = field(compare=False)
    callback: Callable[[], Any] = field(compare=False)
    request_id: str = field(compare=False, default="")


class RateLimiter:
    """
    Rate limiter with per-domain and global limits.

    Features:
    - Per-domain rate limiting (configurable delays)
    - Global rate limiting (requests per minute)
    - Priority queue for request ordering
    - Thread-safe
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig.from_env()

        # Track last request time per domain
        self._domain_last_request: dict[str, float] = {}

        # Track global request times (sliding window)
        self._global_request_times: list[float] = []

        # Priority queue for pending requests
        self._queue: list[QueuedRequest] = []

        # Lock for thread safety
        self._lock = threading.RLock()

        # Request counter
        self._request_counter = 0

        # Running state
        self._running = True

    def get_delay_for_domain(self, domain: str) -> float:
        """Get the configured delay for a domain."""
        return self.config.domain_delays.get(domain, self.config.default_delay)

    def set_domain_delay(self, domain: str, delay: float):
        """Set custom delay for a domain."""
        with self._lock:
            self.config.domain_delays[domain] = delay
            logger.debug(f"Set rate limit for {domain}: {delay}s")

    def _clean_global_window(self):
        """Remove old entries from global rate limit window."""
        cutoff = time.time() - 60  # 1 minute window
        self._global_request_times = [t for t in self._global_request_times if t > cutoff]

    def _can_make_global_request(self) -> bool:
        """Check if global rate limit allows a request."""
        self._clean_global_window()
        return len(self._global_request_times) < self.config.global_requests_per_minute

    def _get_global_wait_time(self) -> float:
        """Get time to wait for global rate limit."""
        self._clean_global_window()
        if len(self._global_request_times) < self.config.global_requests_per_minute:
            return 0.0
        # Wait until oldest request falls out of window
        oldest = min(self._global_request_times)
        return max(0.0, (oldest + 60) - time.time())

    def _get_domain_wait_time(self, domain: str) -> float:
        """Get time to wait for domain rate limit."""
        last_request = self._domain_last_request.get(domain)
        if last_request is None:
            return 0.0

        delay = self.get_delay_for_domain(domain)
        elapsed = time.time() - last_request
        return max(0.0, delay - elapsed)

    def wait_for_domain(self, domain: str) -> float:
        """
        Wait until a request to the domain is allowed.

        Returns the actual wait time.
        """
        with self._lock:
            # Check domain rate limit
            domain_wait = self._get_domain_wait_time(domain)

            # Check global rate limit
            global_wait = self._get_global_wait_time()

            # Wait for the longer of the two
            wait_time = max(domain_wait, global_wait)

        if wait_time > 0:
            logger.debug(f"Rate limiting {domain}: waiting {wait_time:.2f}s")
            time.sleep(wait_time)

        # Record this request
        with self._lock:
            now = time.time()
            self._domain_last_request[domain] = now
            self._global_request_times.append(now)

        return wait_time

    def acquire(self, domain: str) -> "RateLimitContext":
        """
        Acquire rate limit permission for a domain.

        Usage:
            with rate_limiter.acquire("example.com"):
                # make request
        """
        return RateLimitContext(self, domain)

    def enqueue(
        self,
        domain: str,
        callback: Callable[[], Any],
        priority: int | None = None,
    ) -> str:
        """
        Enqueue a request for later execution.

        Args:
            domain: Target domain
            callback: Function to call when ready
            priority: Priority level (lower = higher priority)

        Returns:
            Request ID
        """
        with self._lock:
            self._request_counter += 1
            request_id = f"req-{self._request_counter:06d}"

            request = QueuedRequest(
                priority=priority if priority is not None else self.config.priority_normal,
                enqueued_at=time.time(),
                domain=domain,
                callback=callback,
                request_id=request_id,
            )
            heappush(self._queue, request)

            logger.debug(f"Enqueued request {request_id} for {domain} (priority={request.priority})")
            return request_id

    def process_queue(self, max_requests: int | None = None) -> int:
        """
        Process pending requests from the queue.

        Args:
            max_requests: Maximum requests to process (None = all)

        Returns:
            Number of requests processed
        """
        processed = 0

        while self._running:
            with self._lock:
                if not self._queue:
                    break
                if max_requests is not None and processed >= max_requests:
                    break

                request = heappop(self._queue)

            # Wait for rate limit
            self.wait_for_domain(request.domain)

            # Execute callback
            try:
                request.callback()
                processed += 1
                logger.debug(f"Processed request {request.request_id}")
            except Exception as e:
                logger.error(f"Request {request.request_id} failed: {e}")

        return processed

    def queue_size(self) -> int:
        """Get current queue size."""
        with self._lock:
            return len(self._queue)

    def stop(self):
        """Stop processing queue."""
        self._running = False

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        with self._lock:
            self._clean_global_window()
            return {
                "queue_size": len(self._queue),
                "domains_tracked": len(self._domain_last_request),
                "requests_last_minute": len(self._global_request_times),
                "global_limit": self.config.global_requests_per_minute,
                "default_delay": self.config.default_delay,
                "custom_delays": dict(self.config.domain_delays),
            }


class RateLimitContext:
    """Context manager for rate-limited requests."""

    def __init__(self, limiter: RateLimiter, domain: str):
        self.limiter = limiter
        self.domain = domain
        self.wait_time = 0.0

    def __enter__(self):
        self.wait_time = self.limiter.wait_for_domain(self.domain)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


# Module-level rate limiter
_limiter: RateLimiter | None = None


def get_rate_limiter(config: RateLimitConfig | None = None) -> RateLimiter:
    """Get the global rate limiter."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(config)
    return _limiter


def wait_for_rate_limit(domain: str) -> float:
    """Convenience function to wait for rate limit."""
    return get_rate_limiter().wait_for_domain(domain)

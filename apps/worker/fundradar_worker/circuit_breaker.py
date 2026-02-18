"""
Circuit breaker pattern for Fundradar scraping.

Temporarily disables failing domains to prevent cascading failures.
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """States of a circuit breaker."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failure threshold exceeded, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitConfig:
    """Configuration for circuit breaker."""

    # Number of consecutive failures before opening circuit
    failure_threshold: int = 5

    # Time in seconds before attempting recovery (half-open state)
    cooldown_seconds: float = 300.0  # 5 minutes

    # Number of successful requests needed to close circuit
    success_threshold: int = 2

    # Time window for counting failures (0 = no window, count all)
    failure_window_seconds: float = 0.0

    @classmethod
    def from_env(cls) -> "CircuitConfig":
        """Load config from environment variables."""
        return cls(
            failure_threshold=int(os.environ.get("FUNDRADAR_CIRCUIT_FAILURE_THRESHOLD", "5")),
            cooldown_seconds=float(os.environ.get("FUNDRADAR_CIRCUIT_COOLDOWN", "300")),
            success_threshold=int(os.environ.get("FUNDRADAR_CIRCUIT_SUCCESS_THRESHOLD", "2")),
        )


@dataclass
class CircuitStats:
    """Statistics for a single circuit."""

    domain: str
    state: str
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_at: str | None = None
    last_success_at: str | None = None
    opened_at: str | None = None
    last_state_change_at: str | None = None


class CircuitBreaker:
    """
    Circuit breaker for a single domain.

    States:
    - CLOSED: Normal operation, requests allowed
    - OPEN: Too many failures, requests blocked
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    def __init__(self, domain: str, config: CircuitConfig | None = None):
        self.domain = domain
        self.config = config or CircuitConfig.from_env()

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._total_failures = 0
        self._total_successes = 0
        self._last_failure_time: float | None = None
        self._last_success_time: float | None = None
        self._opened_at: float | None = None
        self._last_state_change: float = time.time()

        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, potentially transitioning to half-open."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if cooldown has passed
                if self._opened_at is not None:
                    elapsed = time.time() - self._opened_at
                    if elapsed >= self.config.cooldown_seconds:
                        self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
            self._consecutive_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0
            self._opened_at = None
        elif new_state == CircuitState.HALF_OPEN:
            self._consecutive_successes = 0

        logger.info(f"Circuit {self.domain}: {old_state.value} -> {new_state.value}")

    def is_allowed(self) -> bool:
        """Check if a request is allowed."""
        state = self.state  # This may trigger half-open transition
        return state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self):
        """Record a successful request."""
        with self._lock:
            self._consecutive_successes += 1
            self._consecutive_failures = 0
            self._total_successes += 1
            self._last_success_time = time.time()

            # If half-open and enough successes, close circuit
            if self._state == CircuitState.HALF_OPEN:
                if self._consecutive_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def record_failure(self):
        """Record a failed request."""
        with self._lock:
            self._consecutive_failures += 1
            self._consecutive_successes = 0
            self._total_failures += 1
            self._last_failure_time = time.time()

            # If half-open, immediately re-open
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            # If closed and threshold exceeded, open
            elif self._state == CircuitState.CLOSED:
                if self._consecutive_failures >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def reset(self):
        """Reset the circuit breaker to closed state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            logger.info(f"Circuit {self.domain}: manually reset")

    def get_stats(self) -> CircuitStats:
        """Get circuit statistics."""
        with self._lock:
            return CircuitStats(
                domain=self.domain,
                state=self.state.value,
                consecutive_failures=self._consecutive_failures,
                consecutive_successes=self._consecutive_successes,
                total_failures=self._total_failures,
                total_successes=self._total_successes,
                last_failure_at=datetime.fromtimestamp(self._last_failure_time, tz=timezone.utc).isoformat()
                if self._last_failure_time else None,
                last_success_at=datetime.fromtimestamp(self._last_success_time, tz=timezone.utc).isoformat()
                if self._last_success_time else None,
                opened_at=datetime.fromtimestamp(self._opened_at, tz=timezone.utc).isoformat()
                if self._opened_at else None,
                last_state_change_at=datetime.fromtimestamp(self._last_state_change, tz=timezone.utc).isoformat(),
            )

    def execute(self, func: Callable[[], T]) -> T:
        """
        Execute a function with circuit breaker protection.

        Raises:
            CircuitOpenError: If circuit is open
        """
        if not self.is_allowed():
            raise CircuitOpenError(f"Circuit open for {self.domain}")

        try:
            result = func()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise


class CircuitOpenError(Exception):
    """Raised when attempting to use an open circuit."""

    pass


class CircuitBreakerRegistry:
    """
    Registry of circuit breakers for all domains.

    Manages multiple circuit breakers and provides persistence.
    """

    def __init__(
        self,
        config: CircuitConfig | None = None,
        state_path: Path | None = None,
    ):
        self.config = config or CircuitConfig.from_env()
        self.state_path = state_path
        self._circuits: dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()
        self._dirty = False  # Track if state changed since last save

        if state_path:
            self._load_state()

    def _load_state(self):
        """Load circuit states from disk."""
        if not self.state_path or not self.state_path.exists():
            return

        try:
            with open(self.state_path) as f:
                data = json.load(f)

            for domain, state_data in data.get("circuits", {}).items():
                circuit = self.get_circuit(domain)
                # Restore state if it was open
                if state_data.get("state") == "open":
                    opened_at = state_data.get("opened_at")
                    if opened_at:
                        circuit._opened_at = datetime.fromisoformat(opened_at).timestamp()
                        circuit._state = CircuitState.OPEN
                        circuit._consecutive_failures = state_data.get("consecutive_failures", 0)

            logger.info(f"Loaded circuit breaker state for {len(self._circuits)} domains")
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"Failed to load circuit breaker state: {e}")

    def _save_state(self):
        """Save circuit states to disk."""
        if not self.state_path:
            return

        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        circuits_data = {}
        with self._lock:
            for domain, circuit in self._circuits.items():
                stats = circuit.get_stats()
                circuits_data[domain] = asdict(stats)

        data = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "circuits": circuits_data,
        }

        with open(self.state_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_circuit(self, domain: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a domain."""
        with self._lock:
            if domain not in self._circuits:
                self._circuits[domain] = CircuitBreaker(domain, self.config)
            return self._circuits[domain]

    def is_allowed(self, domain: str) -> bool:
        """Check if requests to a domain are allowed."""
        return self.get_circuit(domain).is_allowed()

    def record_success(self, domain: str):
        """Record a successful request."""
        self.get_circuit(domain).record_success()
        self._dirty = True

    def record_failure(self, domain: str):
        """Record a failed request."""
        self.get_circuit(domain).record_failure()
        self._dirty = True

    def save_if_dirty(self):
        """Save state to disk if any changes occurred. Call at end of monitoring."""
        if self._dirty:
            self._save_state()
            self._dirty = False

    def reset(self, domain: str):
        """Reset circuit for a domain."""
        self.get_circuit(domain).reset()
        self._save_state()

    def reset_all(self):
        """Reset all circuits."""
        with self._lock:
            for circuit in self._circuits.values():
                circuit.reset()
        self._save_state()

    def get_all_stats(self) -> list[CircuitStats]:
        """Get stats for all circuits."""
        with self._lock:
            return [circuit.get_stats() for circuit in self._circuits.values()]

    def get_open_circuits(self) -> list[str]:
        """Get list of domains with open circuits."""
        with self._lock:
            return [
                domain for domain, circuit in self._circuits.items()
                if circuit.state == CircuitState.OPEN
            ]

    def get_summary(self) -> dict:
        """Get summary of all circuits."""
        stats = self.get_all_stats()
        return {
            "total_circuits": len(stats),
            "open_circuits": sum(1 for s in stats if s.state == "open"),
            "half_open_circuits": sum(1 for s in stats if s.state == "half_open"),
            "closed_circuits": sum(1 for s in stats if s.state == "closed"),
            "total_failures": sum(s.total_failures for s in stats),
            "total_successes": sum(s.total_successes for s in stats),
        }


# Module-level registry
_registry: CircuitBreakerRegistry | None = None


def get_circuit_registry(
    config: CircuitConfig | None = None,
    state_path: Path | None = None,
) -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry."""
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry(config, state_path)
    return _registry


def is_circuit_open(domain: str) -> bool:
    """Check if circuit is open for a domain."""
    return not get_circuit_registry().is_allowed(domain)


def record_circuit_success(domain: str):
    """Record success for a domain."""
    get_circuit_registry().record_success(domain)


def record_circuit_failure(domain: str):
    """Record failure for a domain."""
    get_circuit_registry().record_failure(domain)

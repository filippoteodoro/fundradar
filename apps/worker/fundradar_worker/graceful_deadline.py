"""
Graceful shutdown and deadline handling for long-running pipeline scripts.

Provides a single GracefulDeadline class used by enricher, translator, and
any other pipeline step that needs:
  - SIGTERM/SIGINT handling (set flag, check at safe points)
  - Wall-clock deadline enforcement
  - Combined "should_stop" check

Usage:
    deadline = GracefulDeadline(
        deadline_seconds=50 * 60,
        env_var="ENRICHER_DEADLINE_SECONDS",
    )
    deadline.install_signals()
    deadline.start()

    for item in items:
        if deadline.should_stop():
            break
        process(item)

    print(f"Elapsed: {deadline.elapsed():.0f}s / {deadline.deadline_seconds}s")
"""

import signal as _signal_mod
import time


class GracefulDeadline:
    """Unified graceful shutdown + deadline handler for pipeline scripts.

    This is the SINGLE implementation — do NOT reimplement shutdown/deadline
    logic inline in individual scripts.
    """

    def __init__(
        self,
        deadline_seconds: int,
        env_var: str | None = None,
    ):
        """
        Args:
            deadline_seconds: Default wall-clock deadline in seconds.
            env_var: Optional environment variable name that overrides deadline_seconds.
                     If set and the env var exists, its int value is used instead.
        """
        import os
        if env_var:
            deadline_seconds = int(os.environ.get(env_var, deadline_seconds))
        self.deadline_seconds = deadline_seconds
        self._shutdown_requested = False
        self._start_time: float = 0.0

    def install_signals(self) -> None:
        """Install SIGTERM and SIGINT handlers. Call once at script startup."""
        _signal_mod.signal(_signal_mod.SIGTERM, self._handle_signal)
        _signal_mod.signal(_signal_mod.SIGINT, self._handle_signal)

    def start(self) -> None:
        """Mark the start time. Call when processing begins."""
        self._start_time = time.time()

    def elapsed(self) -> float:
        """Seconds elapsed since start()."""
        if self._start_time <= 0:
            return 0.0
        return time.time() - self._start_time

    def is_deadline_exceeded(self) -> bool:
        """True if wall-clock time exceeds the deadline."""
        if self._start_time <= 0:
            return False
        return self.elapsed() >= self.deadline_seconds

    @property
    def shutdown_requested(self) -> bool:
        """True if SIGTERM/SIGINT was received."""
        return self._shutdown_requested

    def should_stop(self) -> bool:
        """True if the script should save and exit (deadline or signal)."""
        return self._shutdown_requested or self.is_deadline_exceeded()

    def _handle_signal(self, signum, _frame):
        self._shutdown_requested = True
        print(f"\n  SIGNAL {signum} received — will save and exit at next checkpoint")

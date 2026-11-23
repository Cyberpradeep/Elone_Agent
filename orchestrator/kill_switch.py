"""Authoritative Kill Switch Subsystem.

Provides an instant, fail-closed emergency halt mechanism enforced at both global
engine level and per-thread level, immediately stopping pending mutations.
"""

import threading
from typing import Set


class KillSwitch:
    """Thread-safe emergency stop mechanism for runtime engine operations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._global_stop = False
        self._stopped_threads: Set[str] = set()

    def engage_global(self) -> None:
        """Engage engine-wide emergency stop halting all active executions."""
        with self._lock:
            self._global_stop = True

    def disengage_global(self) -> None:
        """Disengage global stop (typically for recovery/re-enabling)."""
        with self._lock:
            self._global_stop = False

    def is_global_engaged(self) -> bool:
        """Check if global emergency stop is active."""
        with self._lock:
            return self._global_stop

    def engage_thread(self, thread_id: str) -> None:
        """Engage kill switch for a specific execution thread."""
        with self._lock:
            self._stopped_threads.add(thread_id)

    def disengage_thread(self, thread_id: str) -> None:
        """Clear thread kill switch flag."""
        with self._lock:
            self._stopped_threads.discard(thread_id)

    def is_thread_stopped(self, thread_id: str) -> bool:
        """Check if a specific thread or the global engine has been stopped."""
        with self._lock:
            return self._global_stop or (thread_id in self._stopped_threads)

    def reset_all(self) -> None:
        """Reset all global and per-thread stop flags."""
        with self._lock:
            self._global_stop = False
            self._stopped_threads.clear()


# Authoritative process-wide singleton
GLOBAL_KILL_SWITCH = KillSwitch()


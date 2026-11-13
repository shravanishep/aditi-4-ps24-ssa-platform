"""
backend.refresh.scheduler — Lightweight in-process periodic scheduler.

Orchestrates periodic dataset refresh on a background daemon thread with
clean lifecycle control (start, stop, is_running), thread-safe concurrency
prevention, and global singleton access for FastAPI application lifecycle.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from backend.refresh.metadata import RefreshMetadata
from backend.refresh.service import DataRefreshService

logger = logging.getLogger(__name__)

# Default refresh interval: 6 hours = 21,600 seconds
DEFAULT_REFRESH_INTERVAL_SECONDS: float = 21600.0


class PeriodicRefreshScheduler:
    """Runs data refresh at a periodic interval on a background daemon thread.

    Avoids external task brokers (Airflow, Celery, Redis) while providing
    clean lifecycle control (start, stop, is_running) and preventing
    overlapping or duplicate downloads.
    """

    def __init__(
        self,
        service: DataRefreshService,
        interval_seconds: float = DEFAULT_REFRESH_INTERVAL_SECONDS,  # default 6 hours
        run_immediately: bool = False,
    ) -> None:
        self.service = service
        self.interval_seconds = max(0.01, interval_seconds)
        self.run_immediately = run_immediately
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()  # Mutex to prevent simultaneous downloads
        self._last_result: RefreshMetadata | None = None

    @property
    def is_running(self) -> bool:
        """Return True if background thread is active."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_result(self) -> RefreshMetadata | None:
        """Return result of latest refresh execution."""
        return self._last_result

    def start(self) -> None:
        """Start the periodic refresh thread."""
        with self._lock:
            if self.is_running:
                logger.warning("PeriodicRefreshScheduler is already running.")
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="DataRefreshSchedulerThread",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "Started PeriodicRefreshScheduler (interval=%.1fs [%.1fh], immediate=%s)",
                self.interval_seconds,
                self.interval_seconds / 3600.0,
                self.run_immediately,
            )

    def stop(self, timeout: float = 5.0) -> None:
        """Signal scheduler thread to stop and wait for completion."""
        with self._lock:
            if not self.is_running:
                return

            self._stop_event.set()
            if self._thread is not None:
                self._thread.join(timeout=timeout)
                self._thread = None
            logger.info("Stopped PeriodicRefreshScheduler.")

    def trigger_now(self, force: bool = False) -> RefreshMetadata:
        """Execute a refresh immediately in the calling thread (thread-safe)."""
        logger.info("Triggering refresh via scheduler (force=%s)...", force)
        with self._refresh_lock:
            res = self.service.refresh_all(force=force)
            self._last_result = res
            return res

    def _run_loop(self) -> None:
        """Background thread execution loop."""
        if self.run_immediately:
            try:
                with self._refresh_lock:
                    self._last_result = self.service.refresh_all(force=False)
            except Exception as exc:
                logger.error("Error during initial scheduler refresh: %s", exc)

        while not self._stop_event.is_set():
            # Wait for interval or stop signal
            if self._stop_event.wait(timeout=self.interval_seconds):
                return

            try:
                logger.info("PeriodicRefreshScheduler executing scheduled refresh cycle...")
                with self._refresh_lock:
                    self._last_result = self.service.refresh_all(force=False)
            except Exception as exc:
                logger.error("Error during scheduled refresh cycle: %s", exc)


# ---------------------------------------------------------------------------
# Global Singleton Management (FastAPI application lifecycle)
# ---------------------------------------------------------------------------

_GLOBAL_SCHEDULER: PeriodicRefreshScheduler | None = None
_GLOBAL_LOCK = threading.Lock()


def get_global_scheduler() -> PeriodicRefreshScheduler | None:
    """Retrieve the active global scheduler instance, if initialized."""
    return _GLOBAL_SCHEDULER


def init_global_scheduler(
    service: DataRefreshService | None = None,
    interval_seconds: float = DEFAULT_REFRESH_INTERVAL_SECONDS,
    run_immediately: bool = False,
) -> PeriodicRefreshScheduler:
    """Initialize and start the global periodic refresh scheduler singleton.

    Ensures only a single scheduler instance runs across the entire application.
    """
    global _GLOBAL_SCHEDULER
    with _GLOBAL_LOCK:
        if _GLOBAL_SCHEDULER is not None and _GLOBAL_SCHEDULER.is_running:
            logger.warning("Global PeriodicRefreshScheduler is already active.")
            return _GLOBAL_SCHEDULER

        if service is None:
            from backend.api.routes import invalidate_catalog_cache

            service = DataRefreshService(on_refresh_success=invalidate_catalog_cache)

        _GLOBAL_SCHEDULER = PeriodicRefreshScheduler(
            service=service,
            interval_seconds=interval_seconds,
            run_immediately=run_immediately,
        )
        _GLOBAL_SCHEDULER.start()
        return _GLOBAL_SCHEDULER


def shutdown_global_scheduler(timeout: float = 5.0) -> None:
    """Cleanly stop and release the global scheduler instance."""
    global _GLOBAL_SCHEDULER
    with _GLOBAL_LOCK:
        if _GLOBAL_SCHEDULER is not None:
            _GLOBAL_SCHEDULER.stop(timeout=timeout)
            _GLOBAL_SCHEDULER = None


def get_scheduler_status() -> str:
    """Return the operational status of the global scheduler."""
    sched = get_global_scheduler()
    if sched is not None and sched.is_running:
        return "active"
    return "disabled"

"""
backend.refresh.scheduler — Lightweight in-process periodic scheduler.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from backend.refresh.metadata import RefreshMetadata
from backend.refresh.service import DataRefreshService

logger = logging.getLogger(__name__)


class PeriodicRefreshScheduler:
    """Runs data refresh at a periodic interval on a background daemon thread.

    Avoids external task brokers (Airflow, Celery, Redis) while providing
    clean lifecycle control (start, stop, is_running).
    """

    def __init__(
        self,
        service: DataRefreshService,
        interval_seconds: float = 86400.0,  # default 24 hours
        run_immediately: bool = False,
    ) -> None:
        self.service = service
        self.interval_seconds = max(0.01, interval_seconds)
        self.run_immediately = run_immediately
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
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
                "Started PeriodicRefreshScheduler (interval=%.1fs, immediate=%s)",
                self.interval_seconds, self.run_immediately,
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

    def trigger_now(self) -> RefreshMetadata:
        """Execute a refresh immediately in the calling thread."""
        logger.info("Triggering manual refresh via scheduler...")
        res = self.service.refresh_all()
        self._last_result = res
        return res

    def _run_loop(self) -> None:
        """Background thread execution loop."""
        if self.run_immediately:
            try:
                self._last_result = self.service.refresh_all()
            except Exception as exc:
                logger.error("Error during initial scheduler refresh: %s", exc)

        while not self._stop_event.is_set():
            # Wait for interval or stop signal
            if self._stop_event.wait(timeout=self.interval_seconds):
                return

            try:
                logger.info("PeriodicRefreshScheduler executing scheduled refresh cycle...")
                self._last_result = self.service.refresh_all()
            except Exception as exc:
                logger.error("Error during scheduled refresh cycle: %s", exc)

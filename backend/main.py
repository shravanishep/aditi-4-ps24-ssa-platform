"""ADITI 4.0 SSA Platform — FastAPI application entry point.

Manages application lifecycle including automated background data refresh scheduler,
orbital propagation, conjunction analysis, CAM simulation, event intelligence, and Pc evaluation.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.routes import router, invalidate_catalog_cache
from backend.events.routes import router as events_router
from backend.ml.routes import router as ml_router
from backend.refresh.scheduler import (
    DEFAULT_REFRESH_INTERVAL_SECONDS,
    init_global_scheduler,
    shutdown_global_scheduler,
)
from backend.refresh.service import DataRefreshService

logger = logging.getLogger("backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifecycle context manager.

    Starts the automated dataset refresh scheduler on startup (if enabled)
    and ensures graceful shutdown upon application termination.
    """
    refresh_enabled = os.environ.get("SSA_REFRESH_ENABLED", "true").lower() in ("true", "1", "yes")
    interval_hours = float(os.environ.get("SSA_REFRESH_INTERVAL_HOURS", "6.0"))
    interval_seconds = max(60.0, interval_hours * 3600.0)
    run_immediately = os.environ.get("SSA_REFRESH_RUN_IMMEDIATELY", "false").lower() in ("true", "1", "yes")

    if refresh_enabled:
        logger.info(
            "Initializing automated catalogue refresh scheduler (interval=%.1f hours)...",
            interval_hours,
        )
        service = DataRefreshService(on_refresh_success=invalidate_catalog_cache)
        init_global_scheduler(
            service=service,
            interval_seconds=interval_seconds,
            run_immediately=run_immediately,
        )
    else:
        logger.info("Automated catalogue refresh scheduler is disabled via SSA_REFRESH_ENABLED.")

    yield

    logger.info("Shutting down automated catalogue refresh scheduler...")
    shutdown_global_scheduler(timeout=5.0)


app = FastAPI(
    title="ADITI 4.0 SSA Platform",
    description=(
        "AI-assisted Space Situational Awareness and Training Platform. "
        "Exposes orbital propagation, conjunction analysis, CAM simulation, "
        "event intelligence, collision probability, and automated data refresh via REST API."
    ),
    version="0.5.0",
    lifespan=lifespan,
)

# Mount API routers
app.include_router(router)
app.include_router(events_router, prefix="/events", tags=["events"])
app.include_router(ml_router, prefix="/ml", tags=["ml"])

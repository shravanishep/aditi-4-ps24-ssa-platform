"""ADITI 4.0 SSA Platform — FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from backend.api.routes import router

app = FastAPI(
    title="ADITI 4.0 SSA Platform",
    description=(
        "AI-assisted Space Situational Awareness and Training Platform. "
        "Exposes orbital propagation and conjunction analysis via REST API."
    ),
    version="0.4.0",
)

app.include_router(router)

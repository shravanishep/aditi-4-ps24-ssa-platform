"""FastAPI routes for Layer 8 ML Anomaly Detection (ADITI 4.0)."""

from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.ml.service import MLAnomalyService
from backend.ml.schemas import (
    MLModelStatusResponse,
    MLOfflineMetricsResponse,
    MLAnomaliesOverviewResponse,
    AnomalyObservation,
)

logger = logging.getLogger("backend.ml.routes")
router = APIRouter()


@router.get("/status", response_model=MLModelStatusResponse, summary="Get active ML model status and configuration")
def get_model_status():
    """Return model name, version, dataset version, regime summaries, and threshold configuration."""
    service = MLAnomalyService.get_instance()
    return service.get_model_status()


@router.get("/metrics", response_model=MLOfflineMetricsResponse, summary="Get offline validated ML performance metrics")
def get_offline_metrics():
    """Return verified offline test performance metrics (precision, recall, F1, ROC-AUC, FAR) across regimes."""
    service = MLAnomalyService.get_instance()
    return service.get_offline_metrics()


@router.get("/anomalies", response_model=MLAnomaliesOverviewResponse, summary="Get ML anomaly detection evaluation overview")
def get_anomalies_overview(limit: int = Query(default=50, ge=1, le=200)):
    """Return evaluated satellite observations, regime alert counts, and score distribution."""
    service = MLAnomalyService.get_instance()
    return service.get_anomalies_overview(limit=limit)


@router.get("/anomalies/{norad_id}", response_model=AnomalyObservation, summary="Get ML anomaly evaluation for a specific satellite")
def get_satellite_anomaly(norad_id: int):
    """Retrieve the latest evaluated anomaly state for a specific satellite by NORAD ID."""
    service = MLAnomalyService.get_instance()
    overview = service.get_anomalies_overview(limit=200)
    for obs in overview["recent_anomalies"]:
        if obs["norad_id"] == norad_id:
            return obs

    raise HTTPException(status_code=404, detail=f"No evaluated anomaly record found for NORAD ID {norad_id}")

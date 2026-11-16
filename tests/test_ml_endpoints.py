"""Unit tests for backend.ml endpoints and service."""

import pytest
from backend.ml.service import MLAnomalyService


def test_ml_service_singleton_and_loading():
    service = MLAnomalyService.get_instance()
    assert service.loading_status == "loaded"
    assert service.detector is not None


def test_ml_model_status():
    service = MLAnomalyService.get_instance()
    status = service.get_model_status()
    assert status["model_name"] == "ADITI-4-RegimeSpecific-IsolationForest"
    assert status["model_version"] == "v3.0.0"
    assert status["dataset_version"] == "v3"
    assert status["satellites_total"] == 350
    assert status["loading_status"] == "loaded"
    assert len(status["regime_summaries"]) == 4
    regimes = [r["regime"] for r in status["regime_summaries"]]
    assert set(regimes) == {"LEO", "MEO", "GEO", "HEO"}


def test_ml_offline_metrics():
    service = MLAnomalyService.get_instance()
    metrics = service.get_offline_metrics()
    assert metrics["is_offline_benchmark"] is True
    assert "disclaimer" in metrics
    assert metrics["overall_test_roc_auc"] == 0.8000
    assert metrics["unseen_satellites_evaluated"] == 70
    assert len(metrics["regime_metrics"]) == 4


def test_ml_anomalies_overview_and_scoring():
    service = MLAnomalyService.get_instance()
    overview = service.get_anomalies_overview(limit=20)
    assert overview["total_evaluated_objects"] > 0
    assert overview["total_observations_evaluated"] > 0
    assert "score_distribution" in overview
    assert "mean" in overview["score_distribution"]
    assert "alerts_by_regime" in overview
    assert len(overview["recent_anomalies"]) > 0

    # Test individual observation fields
    obs = overview["recent_anomalies"][0]
    assert "norad_id" in obs
    assert "regime" in obs
    assert "anomaly_score" in obs
    assert "severity" in obs
    assert obs["severity"] in ("NORMAL", "WARNING", "CRITICAL")
    assert "altitude_km" in obs
    assert "speed_km_s" in obs

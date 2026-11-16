"""Pydantic schemas for ML Anomaly Detection endpoints (Layer 8 / v3 Production)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RegimeThresholdInfo(BaseModel):
    warning_threshold: float
    critical_threshold: float
    decision_threshold: float
    validation_p90: Optional[float] = None
    validation_p95: Optional[float] = None
    notes: Optional[str] = None


class RegimeSummaryInfo(BaseModel):
    regime: str
    satellite_count: int
    observation_count: int
    warning_threshold: float
    critical_threshold: float


class MLModelStatusResponse(BaseModel):
    model_name: str
    model_version: str
    architecture: str
    dataset_version: str
    dataset_rows: int
    satellites_total: int
    training_split_satellites: int
    supported_regimes: List[str]
    features_used: List[str]
    feature_count: int
    loading_status: str  # "loaded", "unavailable", "error"
    trained_timestamp: str
    thresholds: Dict[str, RegimeThresholdInfo]
    regime_summaries: List[RegimeSummaryInfo]


class OfflineRegimeMetric(BaseModel):
    regime: str
    roc_auc: float
    recall: float
    precision: float
    f1_score: float
    false_alarm_rate: float
    unseen_alert_rate: float


class MLOfflineMetricsResponse(BaseModel):
    is_offline_benchmark: bool = True
    disclaimer: str = (
        "Offline validation metrics are computed on historical validation/test partitions "
        "and controlled physical injection scenarios. They do not represent live operational accuracy "
        "or collision probabilities."
    )
    overall_test_roc_auc: float
    overall_test_recall: float
    overall_test_precision: float
    overall_test_f1: float
    overall_test_far: float
    unseen_satellites_evaluated: int
    unseen_alert_rate_overall: float
    regime_metrics: List[OfflineRegimeMetric]


class AnomalyObservation(BaseModel):
    norad_id: int
    object_name: str
    regime: str
    observation_utc: str
    anomaly_score: float
    raw_decision_score: Optional[float] = None
    threshold_crossed: float
    severity: str  # "NORMAL", "WARNING", "CRITICAL"
    is_anomaly: bool
    regime_model_used: str
    altitude_km: float
    speed_km_s: float
    specific_energy_km2_s2: float
    d_altitude_km: float
    d_speed_km_s: float
    d_specific_energy_km2_s2: float
    notes: str


class MLAnomaliesOverviewResponse(BaseModel):
    model_version: str
    total_evaluated_objects: int
    total_observations_evaluated: int
    normal_count: int
    warning_count: int
    critical_count: int
    score_distribution: Dict[str, float]  # mean, median, p75, p95, min, max
    alerts_by_regime: Dict[str, Dict[str, int]]  # {regime: {normal: X, warning: Y, critical: Z}}
    recent_anomalies: List[AnomalyObservation]

"""
tests/test_v3_models.py — Unit and regression tests for Layer 8 v3 models and dataset.

Verifies:
1. v3 Dataset Integrity:
   - 33,950 rows, 42 columns.
   - Zero SGP4 errors.
   - Zero data leakage between train_sats (280) and holdout_sats (70).
2. v3 Model Artifacts Persistence and Prediction:
   - v3 Global model loads and produces valid predictions.
   - v3 Regime-Specific models load and correctly route across 4 regimes.
   - v3 Temporal-Only model loads and predicts with 5 temporal features.
   - v3 Hybrid detector loads from manifest and fuses scores properly.
3. Hybrid Score Fusion:
   - Verifies 'max' fusion mathematically satisfies max(s_regime, s_temporal).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.models.anomaly_detector import OrbitalAnomalyDetector
from ml.models.config import BEHAVIOURAL_FEATURES, TEMPORAL_FEATURES
from ml.models.hybrid_detector import HybridAnomalyDetector
from ml.models.regime_detector import RegimeSpecificAnomalyDetector
from ml.models.temporal_detector import TemporalAnomalyDetector


def test_v3_dataset_schema_and_zero_leakage():
    """Verify v3 dataset shape, column count, and strict satellite isolation."""
    parquet_path = Path("data/processed/orbital_features_v3.parquet")
    if not parquet_path.exists():
        pytest.skip("orbital_features_v3.parquet not found")

    df = pd.read_parquet(parquet_path)
    assert len(df) == 33950
    assert len(df.columns) == 42
    assert (df["sgp4_error"] == 0).all()

    train_sats = set(df.loc[df["sat_split"] == "train_sats", "norad_cat_id"].unique())
    holdout_sats = set(df.loc[df["sat_split"] == "holdout_sats", "norad_cat_id"].unique())

    assert len(train_sats) == 280
    assert len(holdout_sats) == 70
    assert len(train_sats.intersection(holdout_sats)) == 0


def test_v3_global_model_loading_and_prediction():
    """Verify v3 global model loads and predicts on sample observations."""
    model_path = Path("models/isolation_forest_v3_global.joblib")
    if not model_path.exists():
        pytest.skip("v3 global model not found")

    detector = OrbitalAnomalyDetector.load(str(model_path))
    assert detector.is_fitted
    assert len(detector.features) == 12

    # Predict on small slice
    parquet_path = Path("data/processed/orbital_features_v3.parquet")
    df = pd.read_parquet(parquet_path).head(20)
    scored = detector.predict(df)

    assert len(scored) == 20
    assert "normalized_anomaly_score" in scored.columns
    scores = scored["normalized_anomaly_score"].dropna()
    assert (scores >= 0.0).all() and (scores <= 1.0).all()


def test_v3_regime_specific_models():
    """Verify all 4 regime-specific v3 models load and route properly."""
    prefix = "models/isolation_forest_v3_regime"
    detector = RegimeSpecificAnomalyDetector.load(prefix)
    assert detector.is_fitted
    assert set(detector.regime_models.keys()) == {"LEO", "MEO", "GEO", "HEO"}

    parquet_path = Path("data/processed/orbital_features_v3.parquet")
    df = pd.read_parquet(parquet_path)
    # Take 2 samples from each regime
    sample = df.groupby("regime").head(2).reset_index(drop=True)
    scored = detector.predict(sample)

    assert len(scored) == 8
    assert (scored["regime_model_used"] == scored["regime"]).all()


def test_v3_temporal_model():
    """Verify v3 temporal-only model uses only 5 d_* features."""
    model_path = Path("models/isolation_forest_v3_temporal.joblib")
    if not model_path.exists():
        pytest.skip("v3 temporal model not found")

    detector = TemporalAnomalyDetector.load(str(model_path))
    assert detector.is_fitted
    assert len(detector.features) == 5
    for f in detector.features:
        assert f.startswith("d_")


def test_v3_hybrid_detector_manifest_and_score_fusion():
    """Verify v3 hybrid detector loads from manifest and executes max-fusion."""
    manifest_path = Path("models/isolation_forest_v3_hybrid_manifest.json")
    if not manifest_path.exists():
        pytest.skip("v3 hybrid manifest not found")

    hybrid = HybridAnomalyDetector.load(str(manifest_path))
    assert hybrid.is_fitted
    assert hybrid.fusion_method == "max"

    parquet_path = Path("data/processed/orbital_features_v3.parquet")
    df = pd.read_parquet(parquet_path).head(10)
    scored = hybrid.predict(df)

    assert "regime_score" in scored.columns
    assert "temporal_score" in scored.columns
    assert "normalized_anomaly_score" in scored.columns

    # Verify max fusion logic
    expected = np.maximum(scored["regime_score"], scored["temporal_score"])
    np.testing.assert_allclose(scored["normalized_anomaly_score"], expected, atol=1e-5)

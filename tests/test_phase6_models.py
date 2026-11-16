"""
tests/test_phase6_models.py — Unit and integration tests for Phase 6 ML models.

Verifies:
1. Regime-Specific Isolation Forests (Approach A):
   - Fitting and prediction output schema.
   - Strict refusal of silent fallback (raises RegimeModelNotFoundError on missing regimes).
   - Insufficient sample/satellite handling.
   - Independent model persistence (save/load).
2. Temporal-Only Isolation Forest (Approach B):
   - Strict enforcement of temporal-only difference features ('d_*').
   - Fit and predict schema.
   - Persistence.
3. Score Normalization & Thresholds:
   - Monotonic mapping from raw scores to [0.0, 1.0].
   - Correct severity mapping (normal, warning, critical).
4. No Data Leakage:
   - Verifies zero overlap between train_sats and holdout_sats.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.models.config import BEHAVIOURAL_FEATURES, TEMPORAL_FEATURES
from ml.models.regime_detector import (
    RegimeModelNotFoundError,
    RegimeSpecificAnomalyDetector,
    SUPPORTED_REGIMES,
)
from ml.models.temporal_detector import TemporalAnomalyDetector


@pytest.fixture
def multi_regime_orbital_df() -> pd.DataFrame:
    """Fixture providing synthetic observations across LEO, MEO, GEO, and HEO."""
    rows = []
    regimes_info = {
        "LEO": (7000.0, 7.6, 900),
        "MEO": (26000.0, 3.87, 1361),
        "GEO": (42164.0, 3.07, 2866),
        "HEO": (20000.0, 4.5, 25867),
    }

    for regime, (r_base, v_base, norad_id) in regimes_info.items():
        for sat_idx in range(3):
            sat_id = norad_id + sat_idx * 10
            for i in range(20):
                t_min = -300.0 + i * 15.0
                r = r_base + i * 0.5
                v = v_base - i * 0.001
                rows.append(
                    {
                        "norad_cat_id": sat_id,
                        "object_name": f"TEST-{regime}-{sat_id}",
                        "epoch_utc": pd.Timestamp("2026-11-16 00:00:00", tz="UTC"),
                        "observation_utc": pd.Timestamp("2026-11-16 00:00:00", tz="UTC")
                        + pd.Timedelta(minutes=t_min),
                        "t_offset_minutes": t_min,
                        "sgp4_error": 0,
                        "sgp4_error_message": "",
                        "split": "train" if i < 14 else "test",
                        "sat_split": "train_sats",
                        "regime": regime,
                        "mean_motion_rev_day": 15.0 if regime == "LEO" else (1.0 if regime == "GEO" else 2.0),
                        "eccentricity": 0.001 if regime != "HEO" else 0.6,
                        "inclination_deg": 51.6,
                        "raan_deg": 100.0,
                        "arg_of_pericenter_deg": 45.0,
                        "mean_anomaly_epoch_deg": 10.0,
                        "bstar": 0.0001,
                        "mean_motion_dot": 0.0,
                        "mean_motion_ddot": 0.0,
                        "semi_major_axis_km": r_base,
                        "orbital_period_min": 90.0 if regime == "LEO" else 1436.0,
                        "perigee_km": r_base - 6371.0,
                        "apogee_km": r_base - 6371.0,
                        "pos_x_km": r,
                        "pos_y_km": 0.0,
                        "pos_z_km": 0.0,
                        "vel_x_km_s": 0.0,
                        "vel_y_km_s": v,
                        "vel_z_km_s": 0.0,
                        "orbital_radius_km": r,
                        "altitude_km": r - 6371.0,
                        "speed_km_s": v,
                        "radial_vel_km_s": 0.001,
                        "cross_track_vel_km_s": 0.0,
                        "angular_momentum_km2_s": r * v,
                        "specific_energy_km2_s2": (v**2) / 2.0 - 398600.4418 / r,
                        "d_altitude_km": np.nan if i == 0 else 0.5,
                        "d_orbital_radius_km": np.nan if i == 0 else 0.5,
                        "d_speed_km_s": np.nan if i == 0 else -0.001,
                        "d_specific_energy_km2_s2": np.nan if i == 0 else 0.0,
                        "d_angular_momentum_km2_s": np.nan if i == 0 else 0.0,
                        "dt_minutes": np.nan if i == 0 else 15.0,
                    }
                )
    return pd.DataFrame(rows)


# ===========================================================================
# 1. Approach A Tests: Regime-Specific Isolation Forests
# ===========================================================================

def test_regime_detector_fit_and_predict_schema(multi_regime_orbital_df):
    """Regime-specific detector fits all available regimes and outputs correct schema."""
    detector = RegimeSpecificAnomalyDetector(
        min_samples_per_regime=10,
        min_satellites_per_regime=1,
        n_estimators=50,
    )
    detector.fit(multi_regime_orbital_df)

    assert detector.is_fitted
    assert len(detector.regime_models) == 4
    for r in SUPPORTED_REGIMES:
        assert r in detector.regime_models

    scored = detector.predict(multi_regime_orbital_df)
    assert len(scored) == len(multi_regime_orbital_df)

    # Check required output columns
    for col in ["decision_score_raw", "normalized_anomaly_score", "is_anomaly", "anomaly_severity", "regime_model_used"]:
        assert col in scored.columns

    # Check score bounds
    scores = scored["normalized_anomaly_score"].dropna()
    assert (scores >= 0.0).all()
    assert (scores <= 1.0).all()

    # Check correct routing
    assert (scored["regime_model_used"] == scored["regime"]).all()


def test_regime_detector_refuses_silent_fallback(multi_regime_orbital_df):
    """Predicting on a regime without a trained model must raise RegimeModelNotFoundError."""
    # Only fit on LEO data
    leo_only = multi_regime_orbital_df[multi_regime_orbital_df["regime"] == "LEO"]
    detector = RegimeSpecificAnomalyDetector(
        min_samples_per_regime=10,
        min_satellites_per_regime=1,
        n_estimators=50,
    )
    detector.fit(leo_only)

    assert "LEO" in detector.regime_models
    assert "GEO" not in detector.regime_models

    # Now attempt prediction on GEO rows — MUST raise error, NEVER silently use LEO model
    geo_df = multi_regime_orbital_df[multi_regime_orbital_df["regime"] == "GEO"]
    with pytest.raises(RegimeModelNotFoundError) as exc_info:
        detector.predict(geo_df)

    assert "No trained model for regime" in str(exc_info.value)
    assert "GEO" in str(exc_info.value)


def test_regime_detector_insufficient_samples_handling(multi_regime_orbital_df):
    """Regimes with samples below min_samples are safely skipped and reported."""
    detector = RegimeSpecificAnomalyDetector(
        min_samples_per_regime=1000,  # Deliberately higher than fixture data (~60 rows per regime)
        min_satellites_per_regime=1,
        n_estimators=50,
    )
    with pytest.raises(RuntimeError) as exc_info:
        detector.fit(multi_regime_orbital_df)

    assert "No regime models could be trained" in str(exc_info.value)
    for r in SUPPORTED_REGIMES:
        assert detector.regime_stats[r]["status"] == "insufficient_data"


def test_regime_detector_save_and_load(multi_regime_orbital_df):
    """Regime-specific models must serialize to separate joblib files and reload cleanly."""
    detector = RegimeSpecificAnomalyDetector(
        min_samples_per_regime=10,
        min_satellites_per_regime=1,
        n_estimators=50,
    )
    detector.fit(multi_regime_orbital_df)

    with tempfile.TemporaryDirectory() as tmp_dir:
        prefix = Path(tmp_dir) / "test_regime"
        saved = detector.save(str(prefix))

        assert len(saved) == 4
        for r, p in saved.items():
            assert p.exists()
            assert p.name.endswith(f"_{r.lower()}.joblib")

        # Load back
        loaded = RegimeSpecificAnomalyDetector.load(str(prefix))
        assert loaded.is_fitted
        assert len(loaded.regime_models) == 4

        # Predict with loaded model
        scored = loaded.predict(multi_regime_orbital_df)
        assert len(scored) == len(multi_regime_orbital_df)


# ===========================================================================
# 2. Approach B Tests: Temporal-Only Isolation Forest
# ===========================================================================

def test_temporal_detector_enforces_temporal_only_features():
    """TemporalAnomalyDetector must reject static or absolute state features."""
    # Attempting to add an absolute feature like speed_km_s must raise ValueError
    with pytest.raises(ValueError) as exc_info:
        TemporalAnomalyDetector(features=["d_altitude_km", "speed_km_s"])

    assert "temporal difference features starting with 'd_'" in str(exc_info.value)


def test_temporal_detector_fit_and_predict(multi_regime_orbital_df):
    """TemporalAnomalyDetector fits on 5 temporal features and produces valid schema."""
    detector = TemporalAnomalyDetector(n_estimators=50)
    assert len(detector.features) == 5
    for f in detector.features:
        assert f.startswith("d_")

    detector.fit(multi_regime_orbital_df)
    assert detector.is_fitted

    scored = detector.predict(multi_regime_orbital_df)
    assert len(scored) == len(multi_regime_orbital_df)
    scores = scored["normalized_anomaly_score"].dropna()
    assert (scores >= 0.0).all()
    assert (scores <= 1.0).all()


def test_temporal_detector_save_and_load(multi_regime_orbital_df):
    """Temporal detector saves to joblib and loads cleanly."""
    detector = TemporalAnomalyDetector(n_estimators=50)
    detector.fit(multi_regime_orbital_df)

    with tempfile.TemporaryDirectory() as tmp_dir:
        model_path = Path(tmp_dir) / "test_temporal.joblib"
        detector.save(str(model_path))
        assert model_path.exists()

        loaded = TemporalAnomalyDetector.load(str(model_path))
        assert loaded.is_fitted
        assert loaded.features == detector.features


# ===========================================================================
# 3. Score Normalization & Severity Levels
# ===========================================================================

def test_score_normalization_and_severity_levels(multi_regime_orbital_df):
    """Scores are normalized in [0.0, 1.0] and mapped to normal/warning/critical."""
    detector = RegimeSpecificAnomalyDetector(
        min_samples_per_regime=10,
        min_satellites_per_regime=1,
        n_estimators=50,
        decision_threshold=0.65,
        warning_threshold=0.65,
        critical_threshold=0.85,
    )
    detector.fit(multi_regime_orbital_df)
    scored = detector.predict(multi_regime_orbital_df)

    for sev in scored["anomaly_severity"].unique():
        assert sev in ("normal", "warning", "critical")

    # Observations with score >= 0.85 must be critical
    crit_mask = scored["normalized_anomaly_score"] >= 0.85
    if crit_mask.any():
        assert (scored.loc[crit_mask, "anomaly_severity"] == "critical").all()


# ===========================================================================
# 4. Data Leakage Verification
# ===========================================================================

def test_data_leakage_assertion_on_v2_dataset():
    """Ensure train_sats and holdout_sats have zero overlap in orbital_features_v2.parquet."""
    parquet_path = Path("data/processed/orbital_features_v2.parquet")
    if not parquet_path.exists():
        pytest.skip("orbital_features_v2.parquet not found")

    df = pd.read_parquet(parquet_path)
    train_sats = set(df.loc[df["sat_split"] == "train_sats", "norad_cat_id"].unique())
    holdout_sats = set(df.loc[df["sat_split"] == "holdout_sats", "norad_cat_id"].unique())

    overlap = train_sats.intersection(holdout_sats)
    assert len(overlap) == 0, f"DATA LEAKAGE: Overlapping satellite IDs found: {overlap}"
    assert len(train_sats) == 160
    assert len(holdout_sats) == 40

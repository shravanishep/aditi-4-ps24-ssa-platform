"""
tests/test_anomaly_detector.py — Unit tests for Layer 8 OrbitalAnomalyDetector.

Verifies feature preparation, model fitting, prediction output schema,
reproducibility, persistence, and physically consistent synthetic anomaly detection.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.models.anomaly_detector import OrbitalAnomalyDetector
from ml.models.config import BEHAVIOURAL_FEATURES, AnomalyModelConfig
from ml.models.synthetic_anomalies import inject_altitude_step_anomaly, inject_velocity_impulse_anomaly


@pytest.fixture
def sample_orbital_df() -> pd.DataFrame:
    """Fixture providing a synthetic 2-satellite orbital DataFrame matching Layer 7 schema."""
    rows = []
    for norad in [900, 902]:
        base_r = 7000.0 if norad == 900 else 42164.0  # LEO vs GEO
        base_h = base_r - 6371.0
        base_v = np.sqrt(398600.4418 / base_r)

        for i in range(10):
            t_min = -720.0 + i * 15.0
            rows.append(
                {
                    "norad_cat_id": norad,
                    "object_name": f"SAT-{norad}",
                    "epoch_utc": pd.Timestamp("2026-09-17 12:00:00", tz="UTC"),
                    "observation_utc": pd.Timestamp("2026-09-17 12:00:00", tz="UTC") + pd.Timedelta(minutes=t_min),
                    "t_offset_minutes": t_min,
                    "sgp4_error": 0,
                    "sgp4_error_message": "",
                    "split": "train" if i < 6 else ("val" if i < 8 else "test"),
                    "mean_motion_rev_day": 15.0 if norad == 900 else 1.0,
                    "eccentricity": 0.001,
                    "inclination_deg": 51.6,
                    "raan_deg": 100.0,
                    "arg_of_pericenter_deg": 45.0,
                    "mean_anomaly_epoch_deg": 10.0,
                    "bstar": 0.0001,
                    "mean_motion_dot": 0.0,
                    "mean_motion_ddot": 0.0,
                    "semi_major_axis_km": base_r,
                    "orbital_period_min": 90.0 if norad == 900 else 1436.0,
                    "perigee_km": base_h,
                    "apogee_km": base_h,
                    "pos_x_km": base_r * np.cos(i * 0.1),
                    "pos_y_km": base_r * np.sin(i * 0.1),
                    "pos_z_km": 0.0,
                    "vel_x_km_s": -base_v * np.sin(i * 0.1),
                    "vel_y_km_s": base_v * np.cos(i * 0.1),
                    "vel_z_km_s": 0.0,
                    "orbital_radius_km": base_r + float(i) * 0.1,
                    "altitude_km": base_h + float(i) * 0.1,
                    "speed_km_s": base_v,
                    "radial_vel_km_s": 0.001,
                    "cross_track_vel_km_s": 0.0,
                    "angular_momentum_km2_s": base_r * base_v,
                    "specific_energy_km2_s2": (base_v**2) / 2.0 - 398600.4418 / base_r,
                    "d_altitude_km": np.nan if i == 0 else 0.1,
                    "d_orbital_radius_km": np.nan if i == 0 else 0.1,
                    "d_speed_km_s": np.nan if i == 0 else 0.0,
                    "d_specific_energy_km2_s2": np.nan if i == 0 else 0.0,
                    "d_angular_momentum_km2_s": np.nan if i == 0 else 0.0,
                    "dt_minutes": np.nan if i == 0 else 15.0,
                }
            )
    return pd.DataFrame(rows)


def test_static_features_excluded_from_model():
    """Model feature list must contain ONLY 12 dynamic/temporal features."""
    detector = OrbitalAnomalyDetector()
    assert len(detector.features) == 12
    assert detector.features == BEHAVIOURAL_FEATURES
    for static_col in ["inclination_deg", "eccentricity", "semi_major_axis_km", "perigee_km", "apogee_km"]:
        assert static_col not in detector.features


def test_prepare_features_imputes_initial_nans(sample_orbital_df):
    """prepare_features must impute NaNs in initial observation temporal differences."""
    detector = OrbitalAnomalyDetector()
    X = detector.prepare_features(sample_orbital_df)
    assert len(X.columns) == 12
    assert X.isna().sum().sum() == 0


def test_fit_and_predict_schema(sample_orbital_df):
    """predict() must add output columns with expected names and dtypes."""
    detector = OrbitalAnomalyDetector()
    detector.fit(sample_orbital_df)
    assert detector.is_fitted

    preds = detector.predict(sample_orbital_df)
    for col in ["decision_score_raw", "normalized_anomaly_score", "is_anomaly", "anomaly_severity"]:
        assert col in preds.columns

    assert pd.api.types.is_float_dtype(preds["normalized_anomaly_score"])
    assert pd.api.types.is_bool_dtype(preds["is_anomaly"])
    assert (preds["normalized_anomaly_score"] >= 0.0).all()
    assert (preds["normalized_anomaly_score"] <= 1.0).all()


def test_model_reproducibility(sample_orbital_df):
    """Identical random_state must produce identical prediction outputs."""
    cfg = AnomalyModelConfig(random_state=42)

    d1 = OrbitalAnomalyDetector(cfg).fit(sample_orbital_df)
    p1 = d1.predict(sample_orbital_df)

    d2 = OrbitalAnomalyDetector(cfg).fit(sample_orbital_df)
    p2 = d2.predict(sample_orbital_df)

    np.testing.assert_allclose(
        p1["normalized_anomaly_score"].to_numpy(),
        p2["normalized_anomaly_score"].to_numpy(),
        rtol=1e-5,
    )


def test_model_persistence(sample_orbital_df):
    """Serialized and reloaded detector must produce identical predictions."""
    detector = OrbitalAnomalyDetector().fit(sample_orbital_df)
    orig_preds = detector.predict(sample_orbital_df)

    with tempfile.TemporaryDirectory() as tmp_dir:
        save_path = Path(tmp_dir) / "test_model.joblib"
        detector.save(str(save_path))

        reloaded = OrbitalAnomalyDetector.load(str(save_path))
        reloaded_preds = reloaded.predict(sample_orbital_df)

        np.testing.assert_allclose(
            orig_preds["normalized_anomaly_score"].to_numpy(),
            reloaded_preds["normalized_anomaly_score"].to_numpy(),
            rtol=1e-5,
        )


def test_synthetic_velocity_anomaly_detection(sample_orbital_df):
    """A physically consistent 0.5 km/s velocity impulse must produce elevated anomaly score."""
    detector = OrbitalAnomalyDetector().fit(sample_orbital_df)
    baseline_preds = detector.predict(sample_orbital_df)

    # Inject impulse into satellite 900
    t_target = sample_orbital_df[sample_orbital_df["norad_cat_id"] == 900]["t_offset_minutes"].iloc[4]
    perturbed_df, indices = inject_velocity_impulse_anomaly(
        sample_orbital_df, norad_id=900, t_offset_target=t_target, delta_v_km_s=0.50
    )

    perturbed_preds = detector.predict(perturbed_df)

    perturbed_score = perturbed_preds.loc[indices[0], "normalized_anomaly_score"]
    baseline_score = baseline_preds.loc[indices[0], "normalized_anomaly_score"]

    # Score of perturbed state must be elevated relative to baseline
    assert perturbed_score > baseline_score


def test_altitude_step_physical_consistency(sample_orbital_df):
    """Altitude drop must produce strictly coherent 3D state, energy, and momentum vectors."""
    t_start = sample_orbital_df[sample_orbital_df["norad_cat_id"] == 900]["t_offset_minutes"].iloc[5]
    perturbed_df, indices = inject_altitude_step_anomaly(
        sample_orbital_df, norad_id=900, t_offset_start=t_start, delta_h_km=-150.0
    )

    assert len(indices) > 0
    mu = 398600.4418
    r_earth = 6371.0

    for idx in indices:
        row = perturbed_df.loc[idx]
        rx, ry, rz = row["pos_x_km"], row["pos_y_km"], row["pos_z_km"]
        vx, vy, vz = row["vel_x_km_s"], row["vel_y_km_s"], row["vel_z_km_s"]

        r_calc = np.sqrt(rx**2 + ry**2 + rz**2)
        v_calc = np.sqrt(vx**2 + vy**2 + vz**2)

        # Check radius and altitude
        np.testing.assert_allclose(row["orbital_radius_km"], r_calc, rtol=1e-5)
        np.testing.assert_allclose(row["altitude_km"], r_calc - r_earth, rtol=1e-5)
        np.testing.assert_allclose(row["speed_km_s"], v_calc, rtol=1e-5)

        # Check energy & angular momentum
        expected_energy = (v_calc**2) / 2.0 - mu / r_calc
        np.testing.assert_allclose(row["specific_energy_km2_s2"], expected_energy, rtol=1e-5)

        hx = ry * vz - rz * vy
        hy = rz * vx - rx * vz
        hz = rx * vy - ry * vx
        h_calc = np.sqrt(hx**2 + hy**2 + hz**2)
        np.testing.assert_allclose(row["angular_momentum_km2_s"], h_calc, rtol=1e-5)
        np.testing.assert_allclose(row["cross_track_vel_km_s"], h_calc / r_calc, rtol=1e-5)

    # Confirm row 0 of the satellite did not get corrupted into NaN
    sat900_row0 = perturbed_df[perturbed_df["norad_cat_id"] == 900].iloc[0]
    orig_row0 = sample_orbital_df[sample_orbital_df["norad_cat_id"] == 900].iloc[0]
    assert np.isclose(sat900_row0["pos_x_km"], orig_row0["pos_x_km"])
    assert np.isclose(sat900_row0["speed_km_s"], orig_row0["speed_km_s"])

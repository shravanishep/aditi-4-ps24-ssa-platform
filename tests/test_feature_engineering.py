"""
tests/test_feature_engineering.py — Unit tests for Layer 7 feature engineering.

These tests verify each feature computation function in isolation using
synthetic orbital states and GP rows. They do NOT require a running
backend or GP CSV file.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from ml.pipeline.feature_engineering import (
    EXPECTED_COLUMNS,
    FEATURE_SCHEMA,
    PROPAGATED_FEATURE_COLUMNS,
    add_temporal_diff_features,
    assign_split,
    compute_propagated_features,
    compute_static_features,
)
from backend.orbital.models import PropagatedOrbitState
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = timezone.utc
_MU = 398600.4418  # km^3/s^2
_R_EARTH = 6371.0  # km


def _make_gp_row(
    mean_motion: float = 15.5,  # rev/day — roughly LEO
    eccentricity: float = 0.001,
    inclination: float = 51.6,
    raan: float = 100.0,
    arg_of_pericenter: float = 90.0,
    mean_anomaly: float = 0.0,
    bstar: float = 1.0e-4,
    mean_motion_dot: float = 0.0,
    mean_motion_ddot: float = 0.0,
) -> pd.Series:
    return pd.Series(
        {
            "NORAD_CAT_ID": 99999,
            "OBJECT_NAME": "TEST_SAT",
            "EPOCH": "2026-01-01T00:00:00",
            "MEAN_MOTION": mean_motion,
            "ECCENTRICITY": eccentricity,
            "INCLINATION": inclination,
            "RA_OF_ASC_NODE": raan,
            "ARG_OF_PERICENTER": arg_of_pericenter,
            "MEAN_ANOMALY": mean_anomaly,
            "BSTAR": bstar,
            "MEAN_MOTION_DOT": mean_motion_dot,
            "MEAN_MOTION_DDOT": mean_motion_ddot,
        }
    )


def _make_state(
    pos_x: float = 6778.0,
    pos_y: float = 0.0,
    pos_z: float = 0.0,
    vel_x: float = 0.0,
    vel_y: float = 7.67,
    vel_z: float = 0.0,
    sgp4_error: int = 0,
    error_message: str = "",
) -> PropagatedOrbitState:
    return PropagatedOrbitState(
        object_name="TEST_SAT",
        norad_cat_id=99999,
        timestamp=datetime(2026, 1, 1, tzinfo=_UTC),
        position_x_km=pos_x,
        position_y_km=pos_y,
        position_z_km=pos_z,
        velocity_x_km_s=vel_x,
        velocity_y_km_s=vel_y,
        velocity_z_km_s=vel_z,
        sgp4_error=sgp4_error,
        error_message=error_message,
    )


# ---------------------------------------------------------------------------
# Tests: compute_static_features
# ---------------------------------------------------------------------------


class TestStaticFeatures:

    def test_semi_major_axis_iss(self):
        """ISS mean motion ~15.5 rev/day should give SMA ~6750-6800 km."""
        row = _make_gp_row(mean_motion=15.5)
        feats = compute_static_features(row)
        # ISS orbits at ~408 km altitude => radius ~6779 km
        # SMA for n=15.5 rev/day
        n_rad_s = 15.5 * 2 * math.pi / 86400.0
        expected_sma = (_MU / n_rad_s**2) ** (1.0 / 3.0)
        assert abs(feats["semi_major_axis_km"] - expected_sma) < 1.0

    def test_perigee_apogee_circular(self):
        """For e=0, perigee_km == apogee_km."""
        row = _make_gp_row(eccentricity=0.0)
        feats = compute_static_features(row)
        assert abs(feats["perigee_km"] - feats["apogee_km"]) < 1e-6

    def test_orbital_period(self):
        """Orbital period should equal 1440 / mean_motion minutes."""
        mean_motion = 15.5
        row = _make_gp_row(mean_motion=mean_motion)
        feats = compute_static_features(row)
        expected_period = 1440.0 / mean_motion
        assert abs(feats["orbital_period_min"] - expected_period) < 1e-9

    def test_static_features_returns_all_keys(self):
        """compute_static_features must return exactly the expected static keys."""
        row = _make_gp_row()
        feats = compute_static_features(row)
        expected_keys = {
            "mean_motion_rev_day", "eccentricity", "inclination_deg",
            "raan_deg", "arg_of_pericenter_deg", "mean_anomaly_epoch_deg",
            "bstar", "mean_motion_dot", "mean_motion_ddot",
            "semi_major_axis_km", "orbital_period_min",
            "perigee_km", "apogee_km",
        }
        assert set(feats.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Tests: compute_propagated_features
# ---------------------------------------------------------------------------


class TestPropagatedFeatures:

    def test_angular_momentum_positive(self):
        """angular_momentum_km2_s should be positive for a valid orbit."""
        state = _make_state()
        feats = compute_propagated_features(state)
        assert feats["angular_momentum_km2_s"] > 0.0

    def test_specific_energy_negative_bound(self):
        """A bound orbit should have negative specific energy."""
        # Circular orbit at ~408 km: r=6779, v~7.67 km/s
        state = _make_state(pos_x=6779.0, vel_y=7.67)
        feats = compute_propagated_features(state)
        assert feats["specific_energy_km2_s2"] < 0.0

    def test_radial_velocity_near_zero_at_apsis(self):
        """For a velocity perpendicular to position, radial_vel_km_s ~ 0."""
        # r along X, v along Y => dot(r, v) = 0
        state = _make_state(pos_x=7000.0, pos_y=0.0, pos_z=0.0,
                            vel_x=0.0, vel_y=7.5, vel_z=0.0)
        feats = compute_propagated_features(state)
        assert abs(feats["radial_vel_km_s"]) < 1e-9

    def test_orbital_radius_magnitude(self):
        """orbital_radius_km should equal norm([x, y, z])."""
        state = _make_state(pos_x=3000.0, pos_y=4000.0, pos_z=5000.0)
        expected = math.sqrt(3000**2 + 4000**2 + 5000**2)
        feats = compute_propagated_features(state)
        assert abs(feats["orbital_radius_km"] - expected) < 1e-9

    def test_altitude_is_radius_minus_earth(self):
        """altitude_km = orbital_radius_km - 6371.0."""
        state = _make_state(pos_x=6779.0, pos_y=0.0, pos_z=0.0, vel_y=7.67)
        feats = compute_propagated_features(state)
        expected_alt = feats["orbital_radius_km"] - _R_EARTH
        assert abs(feats["altitude_km"] - expected_alt) < 1e-6

    def test_sgp4_error_features_all_nan(self):
        """When sgp4_error != 0, all propagated/derived features must be NaN."""
        state = _make_state(sgp4_error=1, error_message="test error")
        feats = compute_propagated_features(state)
        for col in PROPAGATED_FEATURE_COLUMNS:
            assert math.isnan(feats[col]), f"{col} should be NaN on error row"


# ---------------------------------------------------------------------------
# Tests: add_temporal_diff_features
# ---------------------------------------------------------------------------


class TestTemporalDiffFeatures:

    def _make_sat_df(self, n: int = 5) -> pd.DataFrame:
        """Build a simple DataFrame of n rows for one satellite."""
        rows = []
        for i in range(n):
            rows.append(
                {
                    "norad_cat_id": 99999,
                    "t_offset_minutes": float(i * 15),
                    "altitude_km": 400.0 + float(i) * 0.5,
                    "orbital_radius_km": 6771.0 + float(i) * 0.5,
                    "speed_km_s": 7.67 + float(i) * 0.001,
                    "specific_energy_km2_s2": -29.3 + float(i) * 0.01,
                    "angular_momentum_km2_s": 51900.0 + float(i),
                }
            )
        return pd.DataFrame(rows)

    def test_first_row_d_features_nan(self):
        """The first row of each satellite must have NaN for all d_* columns."""
        df = add_temporal_diff_features(self._make_sat_df())
        first = df.iloc[0]
        assert math.isnan(first["d_altitude_km"])
        assert math.isnan(first["d_orbital_radius_km"])
        assert math.isnan(first["d_speed_km_s"])
        assert math.isnan(first["d_specific_energy_km2_s2"])
        assert math.isnan(first["d_angular_momentum_km2_s"])
        assert math.isnan(first["dt_minutes"])

    def test_d_altitude_computed_correctly(self):
        """d_altitude_km[i] should equal altitude_km[i] - altitude_km[i-1]."""
        df = add_temporal_diff_features(self._make_sat_df())
        for i in range(1, len(df)):
            expected = df.iloc[i]["altitude_km"] - df.iloc[i - 1]["altitude_km"]
            actual = df.iloc[i]["d_altitude_km"]
            assert abs(actual - expected) < 1e-9, f"Row {i}: expected {expected}, got {actual}"

    def test_dt_minutes_is_step(self):
        """dt_minutes should equal step_minutes (15) for consecutive rows."""
        df = add_temporal_diff_features(self._make_sat_df())
        for i in range(1, len(df)):
            assert abs(df.iloc[i]["dt_minutes"] - 15.0) < 1e-9


# ---------------------------------------------------------------------------
# Tests: assign_split
# ---------------------------------------------------------------------------


class TestAssignSplit:

    def _make_split_df(self, n: int = 97) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "t_offset_minutes": [float(i * 15) for i in range(n)],
                "norad_cat_id": [99999] * n,
            }
        )

    def test_split_values_valid(self):
        """split column must contain only 'train', 'val', 'test'."""
        df = assign_split(self._make_split_df(), train_frac=0.6, val_frac=0.2)
        assert set(df["split"].unique()) <= {"train", "val", "test"}

    def test_split_fractions_approximately_correct(self):
        """Split fractions should be close to 0.60 / 0.20 / 0.20."""
        n = 97
        df = assign_split(self._make_split_df(n), train_frac=0.6, val_frac=0.2)
        counts = df["split"].value_counts()
        assert abs(counts.get("train", 0) / n - 0.60) < 0.05
        assert abs(counts.get("val", 0) / n - 0.20) < 0.05
        assert abs(counts.get("test", 0) / n - 0.20) < 0.05

    def test_chronological_order(self):
        """train rows must all precede val rows, val must all precede test rows."""
        df = assign_split(self._make_split_df(), train_frac=0.6, val_frac=0.2)
        train_max = df.loc[df["split"] == "train", "t_offset_minutes"].max()
        val_min = df.loc[df["split"] == "val", "t_offset_minutes"].min()
        val_max = df.loc[df["split"] == "val", "t_offset_minutes"].max()
        test_min = df.loc[df["split"] == "test", "t_offset_minutes"].min()
        assert train_max < val_min, "train overlaps with val"
        assert val_max < test_min, "val overlaps with test"

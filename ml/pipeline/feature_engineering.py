"""
ml.pipeline.feature_engineering — Orbital feature computation for Layer 7.

This module is responsible for computing all ML features from:
  - A raw GP orbital element row (static features)
  - A propagated SGP4 orbit state (dynamic features per observation)
  - A sequence of same-satellite observations (temporal difference features)

Design notes
------------
- All orbital calculations in this file use full float64 precision.
  Float32 downcasting occurs only at dataset write time in dataset_builder.py.
- Existing Layer 1/2 orbital calculation functions (calculations.py,
  sgp4_propagator.py) are not modified.
- Features are documented with their units in column-name docstrings and in
  the FEATURE_SCHEMA dict at the bottom of this file.

Temporal difference features ("d_*")
-------------------------------------
The d_* features are fixed-interval temporal differences between consecutive
observations of the same satellite.  They are not divided by dt_minutes,
because the sampling interval is uniform (step_minutes).  The companion
dt_minutes column records the actual elapsed time so that downstream
consumers can normalise if needed.

Data leakage prevention
------------------------
Leakage prevention is not a property of t_offset_minutes itself.
It is enforced by the per-satellite chronological train/val/test split
(no shuffling) and by the finite-difference construction of d_* features,
which only uses the immediately preceding observation — never a future one.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from backend.orbital.models import PropagatedOrbitState

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

# Earth's gravitational parameter (km^3/s^2)
_MU_KM3_S2: float = 398600.4418

# Earth's mean radius (km) — used for altitude calculation
_R_EARTH_KM: float = 6371.0

# Seconds per day
_SEC_PER_DAY: float = 86400.0

# Minutes per day
_MIN_PER_DAY: float = 1440.0

# Two-pi
_TWO_PI: float = 2.0 * math.pi


# ---------------------------------------------------------------------------
# Static orbital element features
# (computed once per satellite from the GP row)
# ---------------------------------------------------------------------------


def compute_static_features(row: pd.Series) -> dict:
    """Compute static orbital element features from a GP row.

    These values are the same for every observation of the same satellite
    because they come directly from the element set, not from propagation.

    Parameters
    ----------
    row:
        A single row from the GP CSV as a pandas Series.

    Returns
    -------
    dict
        Keys and float values for the static feature columns.
    """
    mean_motion_rev_day = float(row["MEAN_MOTION"])
    eccentricity = float(row["ECCENTRICITY"])

    # Mean motion in rad/s (used for derived static features)
    mean_motion_rad_s = mean_motion_rev_day * _TWO_PI / _SEC_PER_DAY

    # Semi-major axis from vis-viva: a = (mu / n^2)^(1/3)
    semi_major_axis_km = (_MU_KM3_S2 / (mean_motion_rad_s ** 2)) ** (1.0 / 3.0)

    # Orbital period
    orbital_period_min = _MIN_PER_DAY / mean_motion_rev_day

    # Perigee and apogee altitudes
    perigee_km = semi_major_axis_km * (1.0 - eccentricity) - _R_EARTH_KM
    apogee_km = semi_major_axis_km * (1.0 + eccentricity) - _R_EARTH_KM

    return {
        # Raw element columns (preserved verbatim)
        "mean_motion_rev_day": mean_motion_rev_day,
        "eccentricity": eccentricity,
        "inclination_deg": float(row["INCLINATION"]),
        "raan_deg": float(row["RA_OF_ASC_NODE"]),
        "arg_of_pericenter_deg": float(row["ARG_OF_PERICENTER"]),
        "mean_anomaly_epoch_deg": float(row["MEAN_ANOMALY"]),
        "bstar": float(row["BSTAR"]),
        "mean_motion_dot": float(row["MEAN_MOTION_DOT"]),
        "mean_motion_ddot": float(row["MEAN_MOTION_DDOT"]),
        # Derived static features
        "semi_major_axis_km": semi_major_axis_km,
        "orbital_period_min": orbital_period_min,
        "perigee_km": perigee_km,
        "apogee_km": apogee_km,
    }


# ---------------------------------------------------------------------------
# Propagated state features
# (computed per observation from an SGP4 PropagatedOrbitState)
# ---------------------------------------------------------------------------


def compute_propagated_features(state: PropagatedOrbitState) -> dict:
    """Compute physical features from one propagated orbit state.

    Returns NaN for all derived features when sgp4_error != 0.

    Parameters
    ----------
    state:
        A PropagatedOrbitState returned by the Layer 1 propagator.

    Returns
    -------
    dict
        Keys and values for the propagated feature columns.
    """
    # Raw TEME position and velocity (always stored even on error)
    pos_x = state.position_x_km
    pos_y = state.position_y_km
    pos_z = state.position_z_km
    vel_x = state.velocity_x_km_s
    vel_y = state.velocity_y_km_s
    vel_z = state.velocity_z_km_s

    if state.sgp4_error != 0:
        # Return NaN for all propagated/derived features
        nan = float("nan")
        return {
            "pos_x_km": nan,
            "pos_y_km": nan,
            "pos_z_km": nan,
            "vel_x_km_s": nan,
            "vel_y_km_s": nan,
            "vel_z_km_s": nan,
            "orbital_radius_km": nan,
            "altitude_km": nan,
            "speed_km_s": nan,
            "radial_vel_km_s": nan,
            "cross_track_vel_km_s": nan,
            "angular_momentum_km2_s": nan,
            "specific_energy_km2_s2": nan,
        }

    r_vec = np.array([pos_x, pos_y, pos_z], dtype=np.float64)
    v_vec = np.array([vel_x, vel_y, vel_z], dtype=np.float64)

    r_mag = float(np.linalg.norm(r_vec))
    v_mag = float(np.linalg.norm(v_vec))

    # Altitude above mean Earth radius
    altitude_km = r_mag - _R_EARTH_KM

    # Radial velocity (positive = moving away from Earth centre)
    radial_vel_km_s = float(np.dot(r_vec, v_vec) / r_mag) if r_mag > 0.0 else float("nan")

    # Specific angular momentum vector and magnitude
    h_vec = np.cross(r_vec, v_vec)
    h_mag = float(np.linalg.norm(h_vec))

    # Cross-track (tangential) speed = |h| / |r|
    cross_track_vel_km_s = (h_mag / r_mag) if r_mag > 0.0 else float("nan")

    # Specific orbital energy: v^2/2 - mu/r (negative for bound orbit)
    specific_energy = (v_mag ** 2) / 2.0 - _MU_KM3_S2 / r_mag if r_mag > 0.0 else float("nan")

    return {
        "pos_x_km": pos_x,
        "pos_y_km": pos_y,
        "pos_z_km": pos_z,
        "vel_x_km_s": vel_x,
        "vel_y_km_s": vel_y,
        "vel_z_km_s": vel_z,
        "orbital_radius_km": r_mag,
        "altitude_km": altitude_km,
        "speed_km_s": v_mag,
        "radial_vel_km_s": radial_vel_km_s,
        "cross_track_vel_km_s": cross_track_vel_km_s,
        "angular_momentum_km2_s": h_mag,
        "specific_energy_km2_s2": specific_energy,
    }


# ---------------------------------------------------------------------------
# Temporal difference features
# (computed across consecutive observations of the same satellite)
# ---------------------------------------------------------------------------

# Columns for which a temporal difference is computed
_DIFF_COLUMNS = [
    "altitude_km",
    "orbital_radius_km",
    "speed_km_s",
    "specific_energy_km2_s2",
    "angular_momentum_km2_s",
]


def add_temporal_diff_features(sat_df: pd.DataFrame) -> pd.DataFrame:
    """Add temporal difference features (d_* columns) to a per-satellite DataFrame.

    Differences are computed between consecutive rows, sorted by
    t_offset_minutes.  The first row per satellite has NaN for all d_*
    columns because there is no preceding observation to diff against.

    These are fixed-interval temporal differences (not rates-per-unit-time).
    The companion dt_minutes column records the elapsed time between
    consecutive observations so that downstream consumers can normalise.

    Data leakage note: differences are always backward-looking
    (current minus previous).  Future observations are never used to
    construct any feature for an earlier row.

    Parameters
    ----------
    sat_df:
        DataFrame containing observations for exactly one satellite,
        sorted ascending by t_offset_minutes.

    Returns
    -------
    pd.DataFrame
        Input DataFrame with d_* and dt_minutes columns appended.
    """
    df = sat_df.copy()

    # Temporal difference of the temporal coordinate itself
    df["dt_minutes"] = df["t_offset_minutes"].diff()

    for col in _DIFF_COLUMNS:
        df[f"d_{col}"] = df[col].diff()

    return df


# ---------------------------------------------------------------------------
# Split assignment
# (per-satellite chronological train/val/test split)
# ---------------------------------------------------------------------------


def assign_split(
    sat_df: pd.DataFrame,
    train_frac: float,
    val_frac: float,
) -> pd.DataFrame:
    """Assign chronological train/val/test split labels to one satellite's rows.

    The split is applied in temporal order (ascending t_offset_minutes).
    No shuffling is performed.  This is essential: the model will be
    evaluated on later observations of the same satellite, not on
    unseen satellites, matching the anomaly-detection use case.

    Actual leakage prevention is achieved here — by keeping train
    observations strictly before val observations, and val strictly before
    test observations, within each satellite's time series.

    Parameters
    ----------
    sat_df:
        DataFrame for one satellite, sorted ascending by t_offset_minutes.
    train_frac:
        Fraction of observations for "train" (first portion).
    val_frac:
        Fraction for "val" (middle portion).

    Returns
    -------
    pd.DataFrame
        Input DataFrame with a "split" column appended.
    """
    df = sat_df.copy()
    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    split_labels = (
        ["train"] * train_end
        + ["val"] * (val_end - train_end)
        + ["test"] * (n - val_end)
    )
    df["split"] = split_labels
    return df


# ---------------------------------------------------------------------------
# Feature schema registry
# (used by validation.py and documentation)
# ---------------------------------------------------------------------------

FEATURE_SCHEMA: dict[str, str] = {
    # --- Identity / metadata ---
    "norad_cat_id": "int32",
    "object_name": "string",
    "epoch_utc": "datetime64[ns, UTC]",
    "observation_utc": "datetime64[ns, UTC]",
    "t_offset_minutes": "float32",
    "sgp4_error": "int8",
    "sgp4_error_message": "string",
    "split": "string",
    # --- Static orbital elements ---
    "mean_motion_rev_day": "float32",
    "eccentricity": "float32",
    "inclination_deg": "float32",
    "raan_deg": "float32",
    "arg_of_pericenter_deg": "float32",
    "mean_anomaly_epoch_deg": "float32",
    "bstar": "float32",
    "mean_motion_dot": "float32",
    "mean_motion_ddot": "float32",
    # --- Derived static features ---
    "semi_major_axis_km": "float32",
    "orbital_period_min": "float32",
    "perigee_km": "float32",
    "apogee_km": "float32",
    # --- Propagated state ---
    "pos_x_km": "float32",
    "pos_y_km": "float32",
    "pos_z_km": "float32",
    "vel_x_km_s": "float32",
    "vel_y_km_s": "float32",
    "vel_z_km_s": "float32",
    # --- Derived propagated features ---
    "orbital_radius_km": "float32",
    "altitude_km": "float32",
    "speed_km_s": "float32",
    "radial_vel_km_s": "float32",
    "cross_track_vel_km_s": "float32",
    "angular_momentum_km2_s": "float32",
    "specific_energy_km2_s2": "float32",
    # --- Temporal difference features ---
    "d_altitude_km": "float32",
    "d_orbital_radius_km": "float32",
    "d_speed_km_s": "float32",
    "d_specific_energy_km2_s2": "float32",
    "d_angular_momentum_km2_s": "float32",
    "dt_minutes": "float32",
}

# Ordered list of all expected columns (defines output column order)
EXPECTED_COLUMNS: list[str] = list(FEATURE_SCHEMA.keys())

# Propagated + derived feature columns (set to NaN on sgp4_error != 0)
PROPAGATED_FEATURE_COLUMNS: list[str] = [
    "pos_x_km",
    "pos_y_km",
    "pos_z_km",
    "vel_x_km_s",
    "vel_y_km_s",
    "vel_z_km_s",
    "orbital_radius_km",
    "altitude_km",
    "speed_km_s",
    "radial_vel_km_s",
    "cross_track_vel_km_s",
    "angular_momentum_km2_s",
    "specific_energy_km2_s2",
]

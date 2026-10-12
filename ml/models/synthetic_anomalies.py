"""
ml.models.synthetic_anomalies — Physically consistent synthetic anomaly generation.

This module provides utility functions for generating synthetic orbital anomalies
for evaluating unsupervised anomaly detection models.

Physical consistency requirement
----------------------------------
To avoid creating physically impossible state vectors, synthetic perturbations modify
a fundamental physical state parameter (e.g. applying a velocity impulse delta-v or
an orbital radius step delta-r) and then explicitly recompute ALL dependent features
(speed, specific energy, angular momentum, radial velocity, and temporal differences).
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd

_MU_KM3_S2: float = 398600.4418
_R_EARTH_KM: float = 6371.0


def inject_velocity_impulse_anomaly(
    df: pd.DataFrame,
    norad_id: int,
    t_offset_target: float,
    delta_v_km_s: float = 0.50,
) -> tuple[pd.DataFrame, list[int]]:
    """Inject a physically consistent velocity impulse (simulated maneuver) into a satellite observation.

    Parameters
    ----------
    df:
        DataFrame containing Layer 7 feature rows.
    norad_id:
        Target satellite NORAD catalog ID.
    t_offset_target:
        Target observation offset timestamp to perturb.
    delta_v_km_s:
        Magnitude of velocity impulse added to velocity vector (default: 0.5 km/s = 500 m/s).

    Returns
    -------
    tuple[pd.DataFrame, list[int]]:
        (Perturbed DataFrame copy, List of modified row indices).
    """
    out_df = df.copy()

    mask = (out_df["norad_cat_id"] == norad_id) & (np.isclose(out_df["t_offset_minutes"], t_offset_target))
    indices = out_df.index[mask].tolist()

    if not indices:
        return out_df, []

    idx = indices[0]
    row = out_df.loc[idx]

    # Current position and velocity
    rx, ry, rz = float(row["pos_x_km"]), float(row["pos_y_km"]), float(row["pos_z_km"])
    vx, vy, vz = float(row["vel_x_km_s"]), float(row["vel_y_km_s"]), float(row["vel_z_km_s"])

    r_mag = math.sqrt(rx**2 + ry**2 + rz**2)
    v_mag = math.sqrt(vx**2 + vy**2 + vz**2)

    if v_mag < 1e-6:
        return out_df, []

    # Add velocity impulse along velocity vector (prograde maneuver)
    scale = (v_mag + delta_v_km_s) / v_mag
    vx_new, vy_new, vz_new = vx * scale, vy * scale, vz * scale
    v_new_mag = math.sqrt(vx_new**2 + vy_new**2 + vz_new**2)

    # Recompute all dependent physical quantities
    # 1. Angular momentum vector: h = r x v
    hx = ry * vz_new - rz * vy_new
    hy = rz * vx_new - rx * vz_new
    hz = rx * vy_new - ry * vx_new
    h_mag = math.sqrt(hx**2 + hy**2 + hz**2)

    # 2. Specific energy: E = v^2 / 2 - mu / r
    energy = (v_new_mag**2) / 2.0 - _MU_KM3_S2 / r_mag

    # 3. Radial velocity: v_r = (r . v) / r
    r_dot_v = rx * vx_new + ry * vy_new + rz * vz_new
    v_radial = r_dot_v / r_mag

    # Update state features in perturbed row
    out_df.loc[idx, "vel_x_km_s"] = vx_new
    out_df.loc[idx, "vel_y_km_s"] = vy_new
    out_df.loc[idx, "vel_z_km_s"] = vz_new
    out_df.loc[idx, "speed_km_s"] = v_new_mag
    out_df.loc[idx, "angular_momentum_km2_s"] = h_mag
    out_df.loc[idx, "specific_energy_km2_s2"] = energy
    out_df.loc[idx, "radial_vel_km_s"] = v_radial
    out_df.loc[idx, "cross_track_vel_km_s"] = h_mag / r_mag

    # Recompute temporal difference features for this satellite ONLY around the perturbed index
    sat_mask = out_df["norad_cat_id"] == norad_id
    sat_df = out_df[sat_mask].sort_values("t_offset_minutes")
    sat_indices = sat_df.index.tolist()
    pos = sat_indices.index(idx)

    # 1. Update temporal differences at idx (relative to pos - 1)
    if pos > 0:
        prev_idx = sat_indices[pos - 1]
        out_df.loc[idx, "d_altitude_km"] = float(out_df.loc[idx, "altitude_km"]) - float(out_df.loc[prev_idx, "altitude_km"])
        out_df.loc[idx, "d_orbital_radius_km"] = float(out_df.loc[idx, "orbital_radius_km"]) - float(out_df.loc[prev_idx, "orbital_radius_km"])
        out_df.loc[idx, "d_speed_km_s"] = float(out_df.loc[idx, "speed_km_s"]) - float(out_df.loc[prev_idx, "speed_km_s"])
        out_df.loc[idx, "d_specific_energy_km2_s2"] = float(out_df.loc[idx, "specific_energy_km2_s2"]) - float(out_df.loc[prev_idx, "specific_energy_km2_s2"])
        out_df.loc[idx, "d_angular_momentum_km2_s"] = float(out_df.loc[idx, "angular_momentum_km2_s"]) - float(out_df.loc[prev_idx, "angular_momentum_km2_s"])

    # 2. Update temporal differences at pos + 1 (counter-spike relative to perturbed idx)
    modified_indices = [idx]
    if pos + 1 < len(sat_indices):
        next_idx = sat_indices[pos + 1]
        out_df.loc[next_idx, "d_altitude_km"] = float(out_df.loc[next_idx, "altitude_km"]) - float(out_df.loc[idx, "altitude_km"])
        out_df.loc[next_idx, "d_orbital_radius_km"] = float(out_df.loc[next_idx, "orbital_radius_km"]) - float(out_df.loc[idx, "orbital_radius_km"])
        out_df.loc[next_idx, "d_speed_km_s"] = float(out_df.loc[next_idx, "speed_km_s"]) - float(out_df.loc[idx, "speed_km_s"])
        out_df.loc[next_idx, "d_specific_energy_km2_s2"] = float(out_df.loc[next_idx, "specific_energy_km2_s2"]) - float(out_df.loc[idx, "specific_energy_km2_s2"])
        out_df.loc[next_idx, "d_angular_momentum_km2_s"] = float(out_df.loc[next_idx, "angular_momentum_km2_s"]) - float(out_df.loc[idx, "angular_momentum_km2_s"])
        modified_indices.append(next_idx)

    return out_df, modified_indices


def inject_altitude_step_anomaly(
    df: pd.DataFrame,
    norad_id: int,
    t_offset_start: float,
    delta_h_km: float = -150.0,
) -> tuple[pd.DataFrame, list[int]]:
    """Inject a physically consistent altitude step anomaly (simulated orbit drop / drag decay).

    Scales the 3D position vector and orbital velocity consistently, updating all dependent
    kinematic and energetic features (pos_*, vel_*, speed, energy, angular momentum, and differences).

    Parameters
    ----------
    df:
        DataFrame containing Layer 7 feature rows.
    norad_id:
        Target satellite NORAD catalog ID.
    t_offset_start:
        Start offset timestamp from which altitude is dropped.
    delta_h_km:
        Altitude drop in km (default: -150 km).

    Returns
    -------
    tuple[pd.DataFrame, list[int]]:
        (Perturbed DataFrame copy, List of modified row indices).
    """
    out_df = df.copy()

    sat_mask = out_df["norad_cat_id"] == norad_id
    target_mask = sat_mask & (out_df["t_offset_minutes"] >= t_offset_start)
    indices = out_df.index[target_mask].tolist()

    if not indices:
        return out_df, []

    for idx in indices:
        rx, ry, rz = float(out_df.loc[idx, "pos_x_km"]), float(out_df.loc[idx, "pos_y_km"]), float(out_df.loc[idx, "pos_z_km"])
        vx, vy, vz = float(out_df.loc[idx, "vel_x_km_s"]), float(out_df.loc[idx, "vel_y_km_s"]), float(out_df.loc[idx, "vel_z_km_s"])

        r_orig = math.sqrt(rx**2 + ry**2 + rz**2)
        v_orig = math.sqrt(vx**2 + vy**2 + vz**2)

        r_new = r_orig + delta_h_km
        if r_new < 100.0 or v_orig < 1e-6:
            continue

        scale_r = r_new / r_orig
        rx_new, ry_new, rz_new = rx * scale_r, ry * scale_r, rz * scale_r

        # Recompute circular orbit speed from vis-viva: v = sqrt(mu / r)
        v_new = math.sqrt(_MU_KM3_S2 / r_new)
        scale_v = v_new / v_orig
        vx_new, vy_new, vz_new = vx * scale_v, vy * scale_v, vz * scale_v

        # Dependent quantities
        energy_new = (v_new**2) / 2.0 - _MU_KM3_S2 / r_new
        hx = ry_new * vz_new - rz_new * vy_new
        hy = rz_new * vx_new - rx_new * vz_new
        hz = rx_new * vy_new - ry_new * vx_new
        h_mag_new = math.sqrt(hx**2 + hy**2 + hz**2)
        r_dot_v = rx_new * vx_new + ry_new * vy_new + rz_new * vz_new
        v_radial = r_dot_v / r_new

        out_df.loc[idx, "pos_x_km"] = rx_new
        out_df.loc[idx, "pos_y_km"] = ry_new
        out_df.loc[idx, "pos_z_km"] = rz_new
        out_df.loc[idx, "vel_x_km_s"] = vx_new
        out_df.loc[idx, "vel_y_km_s"] = vy_new
        out_df.loc[idx, "vel_z_km_s"] = vz_new
        out_df.loc[idx, "orbital_radius_km"] = r_new
        out_df.loc[idx, "altitude_km"] = r_new - _R_EARTH_KM
        out_df.loc[idx, "speed_km_s"] = v_new
        out_df.loc[idx, "specific_energy_km2_s2"] = energy_new
        out_df.loc[idx, "angular_momentum_km2_s"] = h_mag_new
        out_df.loc[idx, "radial_vel_km_s"] = v_radial
        out_df.loc[idx, "cross_track_vel_km_s"] = h_mag_new / r_new

    # Recompute temporal differences ONLY from the step index onwards
    sat_df = out_df[sat_mask].sort_values("t_offset_minutes")
    sat_indices = sat_df.index.tolist()
    first_idx = indices[0]
    pos_start = sat_indices.index(first_idx)

    for p in range(pos_start, len(sat_indices)):
        cur_idx = sat_indices[p]
        if p > 0:
            p_prev = sat_indices[p - 1]
            out_df.loc[cur_idx, "d_altitude_km"] = float(out_df.loc[cur_idx, "altitude_km"]) - float(out_df.loc[p_prev, "altitude_km"])
            out_df.loc[cur_idx, "d_orbital_radius_km"] = float(out_df.loc[cur_idx, "orbital_radius_km"]) - float(out_df.loc[p_prev, "orbital_radius_km"])
            out_df.loc[cur_idx, "d_speed_km_s"] = float(out_df.loc[cur_idx, "speed_km_s"]) - float(out_df.loc[p_prev, "speed_km_s"])
            out_df.loc[cur_idx, "d_specific_energy_km2_s2"] = float(out_df.loc[cur_idx, "specific_energy_km2_s2"]) - float(out_df.loc[p_prev, "specific_energy_km2_s2"])
            out_df.loc[cur_idx, "d_angular_momentum_km2_s"] = float(out_df.loc[cur_idx, "angular_momentum_km2_s"]) - float(out_df.loc[p_prev, "angular_momentum_km2_s"])

    return out_df, indices

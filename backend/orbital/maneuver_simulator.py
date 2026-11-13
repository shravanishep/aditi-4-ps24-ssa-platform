"""Collision Avoidance Maneuver (CAM) Simulation — Feature 1.

Implements an impulsive ΔV maneuver model using two-body + J2 numerical
integration (RK4) for the post-maneuver trajectory.  The pre-maneuver
trajectory continues to use SGP4 for physical consistency.

DISCLAIMER: Post-maneuver propagation uses numerical two-body+J2 integration,
not SGP4; accuracy degrades over time. This is a research prototype, not an
operational collision avoidance system.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from .sgp4_propagator import propagate_orbit

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
_MU: float = 398600.4418       # Earth gravitational parameter [km³/s²]
_J2: float = 1.08263e-3        # J2 oblateness coefficient [dimensionless]
_RE: float = 6378.137          # Earth equatorial radius [km]
_DV_WARN_THRESHOLD: float = 0.5  # km/s — warn above this
_DV_MAX: float = 2.0            # km/s — hard reject above this

_DISCLAIMER = (
    "Post-maneuver propagation uses numerical two-body+J2 integration, "
    "not SGP4; accuracy degrades over time. This is a research prototype, "
    "not an operational collision avoidance system."
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ManeuverSimulationResult:
    """Full result of a CAM simulation run."""

    original_tca: datetime
    original_miss_km: float
    original_rel_speed: float
    modified_tca: datetime
    modified_miss_km: float
    modified_rel_speed: float
    dv_magnitude_km_s: float
    improvement_km: float          # positive = better (larger) separation
    maneuver_time: datetime
    original_trajectory: list[dict[str, Any]]  # [{t, x, y, z}, ...]
    modified_trajectory: list[dict[str, Any]]  # [{t, x, y, z}, ...]
    disclaimer: str = _DISCLAIMER


# ---------------------------------------------------------------------------
# Two-body + J2 acceleration
# ---------------------------------------------------------------------------

def _gravity_j2(r_vec: np.ndarray) -> np.ndarray:
    """Return acceleration [km/s²] due to two-body gravity + J2.

    Args:
        r_vec: Position vector in TEME [km] (shape (3,)).

    Returns:
        Acceleration vector [km/s²] (shape (3,)).
    """
    x, y, z = r_vec
    r = math.sqrt(x * x + y * y + z * z)
    if r < 100.0:
        # Guard against unphysical states (re-entry / degenerate)
        raise ValueError(f"Orbital radius {r:.1f} km is unphysically small.")

    r3 = r * r * r
    r5 = r3 * r * r

    # Two-body term
    a_2body = -(_MU / r3) * r_vec

    # J2 term — ECEF z-axis approximation in TEME (error < 1 % for LEO)
    factor = (3.0 / 2.0) * _J2 * _MU * (_RE ** 2) / r5
    z_r2 = (z / r) ** 2

    a_j2 = factor * np.array([
        x * (5.0 * z_r2 - 1.0),
        y * (5.0 * z_r2 - 1.0),
        z * (5.0 * z_r2 - 3.0),
    ])

    return a_2body + a_j2


# ---------------------------------------------------------------------------
# RK4 integrator
# ---------------------------------------------------------------------------

def _rk4_step(r: np.ndarray, v: np.ndarray, h: float) -> tuple[np.ndarray, np.ndarray]:
    """Advance one RK4 step of duration h seconds.

    Args:
        r: Position [km].
        v: Velocity [km/s].
        h: Step size [s].

    Returns:
        (r_new, v_new) advanced by h seconds.
    """
    def f(rv: np.ndarray) -> np.ndarray:
        pos = rv[:3]
        vel = rv[3:]
        acc = _gravity_j2(pos)
        return np.concatenate([vel, acc])

    state = np.concatenate([r, v])
    k1 = f(state)
    k2 = f(state + 0.5 * h * k1)
    k3 = f(state + 0.5 * h * k2)
    k4 = f(state + h * k3)

    state_new = state + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
    return state_new[:3], state_new[3:]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _state_from_sgp4(sat_row, t: datetime):
    """Return (position_km: ndarray, velocity_km_s: ndarray) or raise ValueError."""
    state = propagate_orbit(sat_row, t)
    if state.sgp4_error != 0:
        msg = state.error_message or f"SGP4 error code {state.sgp4_error}"
        raise ValueError(f"SGP4 propagation failed at {t.isoformat()}: {msg}")
    r = np.array([state.position_x_km, state.position_y_km, state.position_z_km])
    v = np.array([state.velocity_x_km_s, state.velocity_y_km_s, state.velocity_z_km_s])
    return r, v


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def simulate_maneuver(
    sat_row,
    other_sat_row,
    maneuver_time_utc: datetime,
    dv_x: float,
    dv_y: float,
    dv_z: float,
    window_hours: float = 24.0,
    step_sec: float = 60.0,
) -> ManeuverSimulationResult:
    """Simulate a CAM and return pre/post comparison.

    Args:
        sat_row: GP row of the protected satellite (dict-like).
        other_sat_row: GP row of the threat/other object.
        maneuver_time_utc: UTC datetime of the impulsive burn.
        dv_x, dv_y, dv_z: Velocity perturbation components [km/s] in TEME.
        window_hours: Propagation window length [hours] starting at maneuver_time.
        step_sec: RK4 / SGP4 sampling step [s].

    Returns:
        ManeuverSimulationResult with before/after comparison.

    Raises:
        ValueError: On invalid inputs or SGP4 failure at maneuver time.
    """
    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------
    maneuver_time_utc = _ensure_utc(maneuver_time_utc)
    dv_mag = math.sqrt(dv_x ** 2 + dv_y ** 2 + dv_z ** 2)

    if dv_mag > _DV_MAX:
        raise ValueError(
            f"ΔV magnitude {dv_mag:.4f} km/s exceeds the maximum allowed "
            f"{_DV_MAX} km/s.  Reduce the maneuver delta-V."
        )
    if dv_mag > _DV_WARN_THRESHOLD:
        warnings.warn(
            f"ΔV magnitude {dv_mag:.4f} km/s is large (> {_DV_WARN_THRESHOLD} km/s). "
            "Results are for research purposes only.",
            UserWarning,
            stacklevel=2,
        )

    # ------------------------------------------------------------------
    # Build time grid
    # ------------------------------------------------------------------
    end_time = maneuver_time_utc + timedelta(hours=window_hours)
    n_steps = max(1, int((end_time - maneuver_time_utc).total_seconds() / step_sec))
    times: list[datetime] = [
        maneuver_time_utc + timedelta(seconds=i * step_sec)
        for i in range(n_steps + 1)
    ]
    # Clamp last point to end_time
    if times[-1] > end_time:
        times[-1] = end_time
    elif times[-1] < end_time:
        times.append(end_time)

    # ------------------------------------------------------------------
    # Get maneuver-time state from SGP4 (raises ValueError on error)
    # ------------------------------------------------------------------
    r_burn, v_burn = _state_from_sgp4(sat_row, maneuver_time_utc)
    dv_vec = np.array([dv_x, dv_y, dv_z])

    # Post-maneuver initial state
    r_mod = r_burn.copy()
    v_mod = v_burn + dv_vec

    # ------------------------------------------------------------------
    # Build original trajectory (SGP4 for sat1) and sat2 trajectory (SGP4)
    # ------------------------------------------------------------------
    original_trajectory: list[dict[str, Any]] = []
    sat2_trajectory: list[tuple[datetime, np.ndarray]] = []  # (t, r)

    for t in times:
        # Sat1 original — full SGP4
        s1 = propagate_orbit(sat_row, t)
        if s1.sgp4_error == 0:
            original_trajectory.append({
                "t": t.isoformat(),
                "x": s1.position_x_km,
                "y": s1.position_y_km,
                "z": s1.position_z_km,
            })
        else:
            # Include NaN-safe sentinel for broken steps
            original_trajectory.append({
                "t": t.isoformat(),
                "x": float("nan"),
                "y": float("nan"),
                "z": float("nan"),
            })

        # Sat2 — always SGP4
        s2 = propagate_orbit(other_sat_row, t)
        if s2.sgp4_error == 0:
            sat2_trajectory.append(
                (t, np.array([s2.position_x_km, s2.position_y_km, s2.position_z_km]))
            )

    # ------------------------------------------------------------------
    # Build modified trajectory (RK4+J2 for sat1 from maneuver_time)
    # ------------------------------------------------------------------
    modified_trajectory: list[dict[str, Any]] = []

    # First point is at maneuver_time — use the SGP4 position with post-burn velocity
    r_cur = r_mod.copy()
    v_cur = v_mod.copy()
    h = step_sec  # integration step in seconds

    for i, t in enumerate(times):
        modified_trajectory.append({
            "t": t.isoformat(),
            "x": float(r_cur[0]),
            "y": float(r_cur[1]),
            "z": float(r_cur[2]),
        })

        # Advance state if not at the last step
        if i < len(times) - 1:
            dt_next = (times[i + 1] - t).total_seconds()
            # Use the actual time delta for the last (possibly shorter) step
            try:
                r_cur, v_cur = _rk4_step(r_cur, v_cur, dt_next)
            except ValueError:
                # Unphysical state — stop propagation, fill remaining NaN
                for t_rem in times[i + 1:]:
                    modified_trajectory.append({
                        "t": t_rem.isoformat(),
                        "x": float("nan"),
                        "y": float("nan"),
                        "z": float("nan"),
                    })
                break

    # ------------------------------------------------------------------
    # Find original TCA: scan SGP4 sat1 vs SGP4 sat2
    # ------------------------------------------------------------------
    orig_tca, orig_miss, orig_rel_speed = _find_tca_sgp4(
        sat_row, other_sat_row, times
    )

    # ------------------------------------------------------------------
    # Find modified TCA: scan RK4 sat1 vs SGP4 sat2
    # ------------------------------------------------------------------
    mod_tca, mod_miss, mod_rel_speed = _find_tca_modified(
        modified_trajectory, sat2_trajectory, sat_row, other_sat_row, times
    )

    improvement = mod_miss - orig_miss

    return ManeuverSimulationResult(
        original_tca=orig_tca,
        original_miss_km=orig_miss,
        original_rel_speed=orig_rel_speed,
        modified_tca=mod_tca,
        modified_miss_km=mod_miss,
        modified_rel_speed=mod_rel_speed,
        dv_magnitude_km_s=dv_mag,
        improvement_km=improvement,
        maneuver_time=maneuver_time_utc,
        original_trajectory=original_trajectory,
        modified_trajectory=modified_trajectory,
        disclaimer=_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# TCA helpers
# ---------------------------------------------------------------------------

def _find_tca_sgp4(sat_row, other_sat_row, times: list[datetime]):
    """Scan SGP4-propagated positions to find minimum separation."""
    min_dist = float("inf")
    tca = times[0]
    rel_speed_at_tca = 0.0

    # Pre-compute sat2 states to avoid double SGP4 calls
    for t in times:
        s1 = propagate_orbit(sat_row, t)
        s2 = propagate_orbit(other_sat_row, t)
        if s1.sgp4_error != 0 or s2.sgp4_error != 0:
            continue
        r1 = np.array([s1.position_x_km, s1.position_y_km, s1.position_z_km])
        r2 = np.array([s2.position_x_km, s2.position_y_km, s2.position_z_km])
        dist = float(np.linalg.norm(r2 - r1))
        if dist < min_dist:
            min_dist = dist
            tca = t
            v1 = np.array([s1.velocity_x_km_s, s1.velocity_y_km_s, s1.velocity_z_km_s])
            v2 = np.array([s2.velocity_x_km_s, s2.velocity_y_km_s, s2.velocity_z_km_s])
            rel_speed_at_tca = float(np.linalg.norm(v2 - v1))

    return tca, min_dist, rel_speed_at_tca


def _find_tca_modified(
    mod_traj: list[dict],
    sat2_traj: list[tuple[datetime, np.ndarray]],
    sat_row,
    other_sat_row,
    times: list[datetime],
):
    """Find minimum separation between RK4-propagated sat1 and SGP4 sat2."""
    # Build a dict for quick sat2 lookup by ISO timestamp
    sat2_by_t: dict[str, np.ndarray] = {
        t.isoformat(): r for t, r in sat2_traj
    }

    min_dist = float("inf")
    tca_str = times[0].isoformat()
    rel_speed_at_tca = 0.0

    for pt in mod_traj:
        t_iso = pt["t"]
        if math.isnan(pt["x"]):
            continue
        r1 = np.array([pt["x"], pt["y"], pt["z"]])
        r2 = sat2_by_t.get(t_iso)
        if r2 is None:
            continue
        dist = float(np.linalg.norm(r2 - r1))
        if dist < min_dist:
            min_dist = dist
            tca_str = t_iso
            # Approximate rel speed: use sat2 SGP4 velocity vs RK4 (no stored v for sat1 mod)
            # We reconstruct sat2 velocity from SGP4 at this time
            try:
                t_dt = datetime.fromisoformat(tca_str)
                s2 = propagate_orbit(other_sat_row, t_dt)
                if s2.sgp4_error == 0:
                    v2 = np.array([
                        s2.velocity_x_km_s,
                        s2.velocity_y_km_s,
                        s2.velocity_z_km_s,
                    ])
                    # Use original sat1 velocity from SGP4 as approximation
                    s1_orig = propagate_orbit(sat_row, t_dt)
                    if s1_orig.sgp4_error == 0:
                        v1 = np.array([
                            s1_orig.velocity_x_km_s,
                            s1_orig.velocity_y_km_s,
                            s1_orig.velocity_z_km_s,
                        ])
                        rel_speed_at_tca = float(np.linalg.norm(v2 - v1))
            except Exception:
                pass

    tca_dt = datetime.fromisoformat(tca_str)
    return tca_dt, min_dist, rel_speed_at_tca

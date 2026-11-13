"""Tests for backend/orbital/maneuver_simulator.py — Feature 1 (CAM Simulation).

Uses synthetic ISS-like GP rows; no network calls or real CSV required.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

import pytest

from backend.orbital.maneuver_simulator import simulate_maneuver, ManeuverSimulationResult


# ---------------------------------------------------------------------------
# Shared synthetic GP row (ISS-like orbital parameters)
# ---------------------------------------------------------------------------

def _today_epoch() -> str:
    """Return today's UTC date in ISO format suitable for EPOCH field."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000")


def _make_iss_row(norad: int, name: str) -> dict:
    """Minimal GP dict matching the keys consumed by sgp4_propagator."""
    return {
        "NORAD_CAT_ID": norad,
        "OBJECT_NAME": name,
        "EPOCH": _today_epoch(),
        "MEAN_MOTION": 15.49,          # rev/day — ISS-like LEO
        "ECCENTRICITY": 0.0002,
        "INCLINATION": 51.64,
        "RA_OF_ASC_NODE": 0.0,
        "ARG_OF_PERICENTER": 0.0,
        "MEAN_ANOMALY": 0.0,
        "BSTAR": 0.00013,
        "MEAN_MOTION_DOT": 0.0,
        "MEAN_MOTION_DDOT": 0.0,
    }


# Two different satellites with slightly different mean anomaly so they
# don't occupy the same position (avoid zero-distance TCA).
SAT1 = _make_iss_row(25544, "ISS (ZARYA)")
SAT2 = {**_make_iss_row(99999, "DEBRIS-SYNTH"), "MEAN_ANOMALY": 10.0}


def _maneuver_time() -> datetime:
    """Return a maneuver time 1 minute into the future (past epoch)."""
    return datetime.now(timezone.utc) + timedelta(minutes=1)


# ---------------------------------------------------------------------------
# Common helper: run a simulation with given ΔV components
# ---------------------------------------------------------------------------

def _run(dv_x=0.0, dv_y=0.0, dv_z=0.0, window_hours=1.0, step_sec=60.0):
    return simulate_maneuver(
        sat_row=SAT1,
        other_sat_row=SAT2,
        maneuver_time_utc=_maneuver_time(),
        dv_x=dv_x,
        dv_y=dv_y,
        dv_z=dv_z,
        window_hours=window_hours,
        step_sec=step_sec,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestManeuverSimulator:

    def test_zero_dv(self):
        """With dv=0 the improvement should be near 0 (within 2 km, SGP4 vs RK4 discrepancy)."""
        result = _run(dv_x=0.0, dv_y=0.0, dv_z=0.0)
        assert isinstance(result, ManeuverSimulationResult)
        # Both paths share same dynamics at zero ΔV — difference should be small
        assert abs(result.improvement_km) < 2.0, (
            f"Expected near-zero improvement for zero ΔV, got {result.improvement_km:.4f} km"
        )

    def test_dv_magnitude_calculation(self):
        """dv_magnitude_km_s must equal sqrt(dv_x² + dv_y² + dv_z²)."""
        dx, dy, dz = 0.01, 0.02, 0.03
        expected_mag = math.sqrt(dx**2 + dy**2 + dz**2)
        result = _run(dv_x=dx, dv_y=dy, dv_z=dz)
        assert abs(result.dv_magnitude_km_s - expected_mag) < 1e-10, (
            f"Expected dv_magnitude={expected_mag}, got {result.dv_magnitude_km_s}"
        )

    def test_improvement_definition(self):
        """improvement_km must equal modified_miss_km - original_miss_km."""
        result = _run(dv_x=0.05, dv_y=0.0, dv_z=0.0)
        expected = result.modified_miss_km - result.original_miss_km
        assert abs(result.improvement_km - expected) < 1e-9, (
            f"improvement_km mismatch: {result.improvement_km} vs {expected}"
        )

    def test_original_trajectory_nonempty(self):
        """original_trajectory must contain at least one point."""
        result = _run()
        assert len(result.original_trajectory) > 0, "original_trajectory is empty"

    def test_modified_trajectory_nonempty(self):
        """modified_trajectory must contain at least one point."""
        result = _run(dv_x=0.01)
        assert len(result.modified_trajectory) > 0, "modified_trajectory is empty"

    def test_maneuver_time_in_result(self):
        """result.maneuver_time must equal the input maneuver_time within 1 second."""
        t0 = _maneuver_time()
        result = simulate_maneuver(
            sat_row=SAT1,
            other_sat_row=SAT2,
            maneuver_time_utc=t0,
            dv_x=0.0,
            dv_y=0.0,
            dv_z=0.0,
            window_hours=1.0,
            step_sec=60.0,
        )
        diff = abs((result.maneuver_time - t0).total_seconds())
        assert diff <= 1.0, (
            f"maneuver_time mismatch: input={t0.isoformat()}, "
            f"result={result.maneuver_time.isoformat()}, diff={diff}s"
        )

    def test_disclaimer_present(self):
        """result.disclaimer must be a non-empty string."""
        result = _run()
        assert isinstance(result.disclaimer, str)
        assert len(result.disclaimer.strip()) > 0, "disclaimer is empty"

    def test_excessive_dv_raises(self):
        """ΔV magnitude > 2.0 km/s must raise ValueError."""
        # 3 km/s total — well above the 2.0 km/s hard limit
        big_dv = math.sqrt(3.0) + 0.01  # ~1.74 each axis gives ~3.0 mag
        with pytest.raises(ValueError, match="exceed"):
            simulate_maneuver(
                sat_row=SAT1,
                other_sat_row=SAT2,
                maneuver_time_utc=_maneuver_time(),
                dv_x=big_dv,
                dv_y=big_dv,
                dv_z=0.0,
                window_hours=1.0,
                step_sec=60.0,
            )

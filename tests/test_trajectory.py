"""Tests for Layer 6 additive trajectory endpoint.

Tests the GET /satellites/{norad_id}/trajectory endpoint:
  - Valid structure and coordinate frames
  - Step size and time window enforcement
  - Timezone validation and UTC normalization
  - Point ordering and bounds
  - Error inclusion (non-zero SGP4 errors preserved in response)
  - 404 on unknown satellites and 422 on invalid parameters
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.orbital.models import PropagatedOrbitState

client = TestClient(app, raise_server_exceptions=False)

KNOWN_ID = 900
START_UTC = "2026-09-17T12:00:00Z"
END_UTC = "2026-09-17T13:00:00Z"  # 1-hour window


class TestTrajectoryEndpoint:
    def test_trajectory_returns_correct_structure(self):
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={START_UTC}&end={END_UTC}&step_sec=60"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["norad_cat_id"] == KNOWN_ID
        assert "object_name" in data
        assert data["frame"] == "TEME"
        assert data["step_sec"] == 60.0
        assert "points" in data
        assert isinstance(data["points"], list)
        assert len(data["points"]) > 0

        first_point = data["points"][0]
        required_fields = [
            "timestamp",
            "position_x_km",
            "position_y_km",
            "position_z_km",
            "velocity_x_km_s",
            "velocity_y_km_s",
            "velocity_z_km_s",
            "sgp4_error",
        ]
        for field in required_fields:
            assert field in first_point

    def test_trajectory_points_are_in_expected_range(self):
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={START_UTC}&end={END_UTC}&step_sec=120"
        )
        assert resp.status_code == 200
        points = resp.json()["points"]

        for pt in points:
            for coord in ("position_x_km", "position_y_km", "position_z_km"):
                assert -50000.0 <= pt[coord] <= 50000.0, f"{coord} out of physical range: {pt[coord]}"
            for vel in ("velocity_x_km_s", "velocity_y_km_s", "velocity_z_km_s"):
                assert -15.0 <= pt[vel] <= 15.0, f"{vel} out of physical range: {pt[vel]}"

    def test_trajectory_step_respected(self):
        # 1-hour window (3600 seconds) with step 60s -> 61 points inclusive
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={START_UTC}&end={END_UTC}&step_sec=60"
        )
        assert resp.status_code == 200
        points = resp.json()["points"]
        assert len(points) == 61

    def test_trajectory_point_ordering(self):
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={START_UTC}&end={END_UTC}&step_sec=60"
        )
        assert resp.status_code == 200
        points = resp.json()["points"]

        prev_dt = datetime.fromisoformat(points[0]["timestamp"].replace("Z", "+00:00"))
        for pt in points[1:]:
            curr_dt = datetime.fromisoformat(pt["timestamp"].replace("Z", "+00:00"))
            assert curr_dt > prev_dt
            prev_dt = curr_dt

    def test_trajectory_unknown_norad_returns_404(self):
        resp = client.get(
            f"/satellites/9999999/trajectory?start={START_UTC}&end={END_UTC}"
        )
        assert resp.status_code == 404

    def test_trajectory_naive_start_returns_422(self):
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start=2026-09-17T12:00:00&end={END_UTC}"
        )
        assert resp.status_code == 422
        assert "timezone-aware" in resp.json()["detail"].lower()

    def test_trajectory_naive_end_returns_422(self):
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={START_UTC}&end=2026-09-17T13:00:00"
        )
        assert resp.status_code == 422
        assert "timezone-aware" in resp.json()["detail"].lower()

    def test_trajectory_end_before_start_returns_422(self):
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={END_UTC}&end={START_UTC}"
        )
        assert resp.status_code == 422

    def test_trajectory_step_too_small_returns_422(self):
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={START_UTC}&end={END_UTC}&step_sec=5.0"
        )
        assert resp.status_code == 422

    def test_trajectory_step_too_large_returns_422(self):
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={START_UTC}&end={END_UTC}&step_sec=4000.0"
        )
        assert resp.status_code == 422

    def test_trajectory_window_too_large_returns_422(self):
        # 25 hours window
        start = "2026-09-17T00:00:00Z"
        end = "2026-09-18T01:00:00Z"
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={start}&end={end}&step_sec=300"
        )
        assert resp.status_code == 422
        assert "24 hours" in resp.json()["detail"].lower()

    def test_trajectory_sgp4_error_points_included(self):
        mock_error_state = PropagatedOrbitState(
            norad_cat_id=KNOWN_ID,
            object_name="CALSPHERE 1",
            timestamp=datetime.fromisoformat(START_UTC),
            position_x_km=0.0,
            position_y_km=0.0,
            position_z_km=0.0,
            velocity_x_km_s=0.0,
            velocity_y_km_s=0.0,
            velocity_z_km_s=0.0,
            sgp4_error=6,
            error_message="decayed",
        )
        with patch("backend.api.routes.propagate_orbit", return_value=mock_error_state):
            resp = client.get(
                f"/satellites/{KNOWN_ID}/trajectory?start={START_UTC}&end={END_UTC}&step_sec=600"
            )
            assert resp.status_code == 200
            points = resp.json()["points"]
            assert len(points) > 0
            for pt in points:
                assert pt["sgp4_error"] == 6

    def test_trajectory_frame_is_teme(self):
        resp = client.get(
            f"/satellites/{KNOWN_ID}/trajectory?start={START_UTC}&end={END_UTC}"
        )
        assert resp.status_code == 200
        assert resp.json()["frame"] == "TEME"

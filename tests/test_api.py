"""Tests for Layer 4 FastAPI endpoints.

Uses FastAPI TestClient (backed by httpx) to exercise each endpoint
with both success and failure cases.

NORAD IDs used in integration tests must exist in the real GP dataset.
Satellite list/detail tests use only NORAD IDs that are always present
in the CelesTrak active-satellite export.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /satellites  (list)
# ---------------------------------------------------------------------------

class TestListSatellites:
    def test_default_limit(self):
        resp = client.get("/satellites")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) <= 100
        assert len(data) > 0
        # Verify each item has the required fields
        for sat in data:
            assert "norad_cat_id" in sat
            assert "object_name" in sat

    def test_custom_limit(self):
        resp = client.get("/satellites?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 5

    def test_limit_too_low(self):
        resp = client.get("/satellites?limit=0")
        assert resp.status_code == 422

    def test_limit_too_high(self):
        resp = client.get("/satellites?limit=1001")
        assert resp.status_code == 422

    def test_limit_minimum_valid(self):
        resp = client.get("/satellites?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_limit_maximum_valid(self):
        resp = client.get("/satellites?limit=1000")
        assert resp.status_code == 200
        assert len(resp.json()) <= 1000


# ---------------------------------------------------------------------------
# /satellites/{norad_id}  (detail)
# ---------------------------------------------------------------------------

class TestGetSatellite:
    # NORAD 900 = a well-known object present in the CelesTrak GP export
    KNOWN_ID = 900

    def test_known_satellite(self):
        resp = client.get(f"/satellites/{self.KNOWN_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["norad_cat_id"] == self.KNOWN_ID
        assert "object_name" in data
        assert "epoch" in data
        assert "mean_motion" in data

    def test_unknown_satellite_returns_404(self):
        resp = client.get("/satellites/9999999")
        assert resp.status_code == 404

    def test_invalid_norad_type_returns_422(self):
        resp = client.get("/satellites/not_a_number")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /satellites/{norad_id}/orbit
# ---------------------------------------------------------------------------

class TestGetOrbit:
    KNOWN_ID = 900
    VALID_TS = "2026-09-17T12:00:00Z"
    OFFSET_TS = "2026-09-17T17:30:00+05:30"  # same moment in IST

    def test_orbit_utc_timestamp(self):
        resp = client.get(f"/satellites/{self.KNOWN_ID}/orbit?timestamp={self.VALID_TS}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["norad_cat_id"] == self.KNOWN_ID
        assert "position_x_km" in data
        assert "velocity_x_km_s" in data
        assert "timestamp" in data

    def test_orbit_offset_timestamp_normalized(self):
        resp_utc = client.get(f"/satellites/{self.KNOWN_ID}/orbit?timestamp={self.VALID_TS}")
        resp_offset = client.get(f"/satellites/{self.KNOWN_ID}/orbit?timestamp={self.OFFSET_TS}")
        assert resp_utc.status_code == 200
        assert resp_offset.status_code == 200
        # Both timestamps represent the same moment — positions must match
        assert resp_utc.json()["position_x_km"] == pytest.approx(
            resp_offset.json()["position_x_km"], rel=1e-6
        )

    def test_orbit_naive_timestamp_rejected(self):
        resp = client.get(f"/satellites/{self.KNOWN_ID}/orbit?timestamp=2026-09-17T12:00:00")
        assert resp.status_code == 422

    def test_orbit_unknown_satellite_returns_404(self):
        resp = client.get(f"/satellites/9999999/orbit?timestamp={self.VALID_TS}")
        assert resp.status_code == 404

    def test_orbit_missing_timestamp_returns_422(self):
        resp = client.get(f"/satellites/{self.KNOWN_ID}/orbit")
        assert resp.status_code == 422

    def test_orbit_invalid_timestamp_format_returns_422(self):
        resp = client.get(f"/satellites/{self.KNOWN_ID}/orbit?timestamp=not-a-date")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /conjunction/analyze
# ---------------------------------------------------------------------------

class TestConjunctionAnalyze:
    # Two satellites that are present in the real GP dataset
    NORAD1 = 900
    NORAD2 = 902

    VALID_BODY = {
        "norad1": NORAD1,
        "norad2": NORAD2,
        "start_time": "2026-09-17T12:00:00Z",
        "end_time": "2026-09-17T12:10:00Z",
        "threshold_km": 500.0,
        "coarse_step_sec": 60.0,
        "fine_step_sec": 1.0,
    }

    def test_successful_analysis(self):
        resp = client.post("/conjunction/analyze", json=self.VALID_BODY)
        assert resp.status_code == 200
        data = resp.json()
        assert data["object1_norad_id"] == self.NORAD1
        assert data["object2_norad_id"] == self.NORAD2
        assert "time_of_closest_approach" in data
        assert "minimum_separation_km" in data
        assert "relative_speed_km_s" in data
        assert "is_candidate_close_approach" in data

    def test_same_norad_returns_400(self):
        body = {**self.VALID_BODY, "norad2": self.NORAD1}
        resp = client.post("/conjunction/analyze", json=body)
        assert resp.status_code == 400

    def test_unknown_norad1_returns_404(self):
        body = {**self.VALID_BODY, "norad1": 9999999}
        resp = client.post("/conjunction/analyze", json=body)
        assert resp.status_code == 404

    def test_unknown_norad2_returns_404(self):
        body = {**self.VALID_BODY, "norad2": 9999999}
        resp = client.post("/conjunction/analyze", json=body)
        assert resp.status_code == 404

    def test_end_before_start_returns_400(self):
        body = {
            **self.VALID_BODY,
            "start_time": "2026-09-17T12:10:00Z",
            "end_time": "2026-09-17T12:00:00Z",
        }
        resp = client.post("/conjunction/analyze", json=body)
        assert resp.status_code == 400

    def test_zero_threshold_returns_422(self):
        body = {**self.VALID_BODY, "threshold_km": 0}
        resp = client.post("/conjunction/analyze", json=body)
        assert resp.status_code == 422

    def test_naive_timestamp_returns_422(self):
        body = {
            **self.VALID_BODY,
            "start_time": "2026-09-17T12:00:00",  # no timezone
        }
        resp = client.post("/conjunction/analyze", json=body)
        assert resp.status_code == 422

    def test_offset_timestamps_accepted(self):
        body = {
            **self.VALID_BODY,
            "start_time": "2026-09-17T17:30:00+05:30",
            "end_time": "2026-09-17T17:40:00+05:30",
        }
        resp = client.post("/conjunction/analyze", json=body)
        assert resp.status_code == 200

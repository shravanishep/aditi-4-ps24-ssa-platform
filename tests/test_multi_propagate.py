"""
tests.test_multi_propagate — Tests for Layer 13 multi-object orbital propagation
and catalogue distribution endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app, raise_server_exceptions=False)


class TestMultiPropagate:
    """Test suite for GET /satellites/multi-propagate."""

    def test_default_multi_propagate(self):
        resp = client.get("/satellites/multi-propagate")
        assert resp.status_code == 200
        data = resp.json()

        assert "timestamp" in data
        assert "total_matching" in data
        assert data["total_matching"] > 0
        assert "propagated_count" in data
        assert data["propagated_count"] <= 50
        assert len(data["objects"]) == data["propagated_count"]
        assert "disclaimer" in data
        assert "data_source_notes" in data

        if data["objects"]:
            first = data["objects"][0]
            assert "norad_cat_id" in first
            assert "object_name" in first
            assert "position_x_km" in first
            assert "position_y_km" in first
            assert "position_z_km" in first
            assert "velocity_x_km_s" in first
            assert "velocity_y_km_s" in first
            assert "velocity_z_km_s" in first
            assert "altitude_km" in first
            assert "speed_km_s" in first
            assert "sgp4_error" in first
            assert first["sgp4_error"] == 0

    def test_bounded_limit(self):
        resp = client.get("/satellites/multi-propagate?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["objects"]) == 5
        assert data["propagated_count"] == 5

    def test_limit_bounds_validation(self):
        # limit must be between 1 and 200
        resp_low = client.get("/satellites/multi-propagate?limit=0")
        assert resp_low.status_code == 422

        resp_high = client.get("/satellites/multi-propagate?limit=201")
        assert resp_high.status_code == 422

    def test_explicit_norad_ids(self):
        resp = client.get("/satellites/multi-propagate?norad_ids=900,25544")
        assert resp.status_code == 200
        data = resp.json()
        ids = [o["norad_cat_id"] for o in data["objects"]]
        assert 900 in ids
        assert 25544 in ids

    def test_search_filter(self):
        resp = client.get("/satellites/multi-propagate?search=CALSPHERE&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        for o in data["objects"]:
            assert "CALSPHERE" in o["object_name"].upper()

    def test_regime_filter_leo(self):
        resp = client.get("/satellites/multi-propagate?regime=LEO&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        for o in data["objects"]:
            assert o["altitude_km"] < 2500  # typical LEO

    def test_invalid_target_time(self):
        resp = client.get("/satellites/multi-propagate?target_time=invalid-date")
        assert resp.status_code == 422


class TestCatalogDistribution:
    """Test suite for catalogue regime and classification distribution analytics."""

    def test_catalog_status_includes_distributions(self):
        resp = client.get("/catalog/status")
        assert resp.status_code == 200
        data = resp.json()

        assert "orbit_regimes" in data
        regimes = data["orbit_regimes"]
        assert "LEO" in regimes
        assert "MEO" in regimes
        assert "GEO" in regimes
        assert "Other" in regimes
        assert regimes["LEO"] > 0

        assert "classifications" in data
        cls_map = data["classifications"]
        assert "ACTIVE_SATELLITE" in cls_map
        assert cls_map["ACTIVE_SATELLITE"] > 0

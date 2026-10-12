"""
tests/test_threat_api.py — Unit and integration tests for Layer 11 Threat Prioritization API.

Tests:
1. Successful POST /threats/screen with specific protected target.
2. Successful GET /threats/screen with query parameters.
3. Empty results handling when threshold is extremely tight (200 with empty list).
4. Validation errors: negative threshold, zero window, invalid policy, invalid NORAD IDs (422).
5. 404 error when protected NORAD ID does not exist in catalogue.
6. 503 error when underlying GP dataset is missing.
7. Metadata and provenance preservation in event responses (classifications, provenance, explanations).
8. Visible stale-data warnings preserved in screening_notes when max_epoch_age_days is exceeded.
9. Stale data exclude policy filtering out stale objects.
"""

from __future__ import annotations

from unittest.mock import patch
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------

class TestThreatScreeningSuccess:
    def test_post_screen_threats_explicit_target(self):
        """Test POST screening for ISS (NORAD 25544) against a bounded candidate pool."""
        payload = {
            "protected_norad_ids": [25544],
            "screening_threshold_km": 500.0,
            "screening_window_hours": 24.0,
            "max_threat_candidates": 10,
            "max_ranked_results": 10,
            "coarse_step_sec": 120.0,
        }
        resp = client.post("/threats/screen", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert "events" in data
        assert "summary" in data

        summary = data["summary"]
        assert summary["protected_count"] == 1
        assert summary["candidates_screened"] <= 10
        assert summary["pairs_evaluated"] <= 10
        assert (
            "not collision probabilities" in summary["disclaimer"].lower()
            or "heuristic priority" in summary["disclaimer"].lower()
        )

        # If events were found within 500 km, check their structure
        for ev in data["events"]:
            assert ev["protected_norad_id"] == 25544
            assert "protected_name" in ev
            assert "protected_classification" in ev
            assert "threat_norad_id" in ev
            assert "threat_name" in ev
            assert "threat_classification" in ev
            assert "threat_source_provenance" in ev
            assert 0.0 <= ev["risk_score"] <= 1.0
            assert ev["risk_severity"] in ("critical", "warning", "low")
            assert "factors" in ev["risk_explanation"]

    def test_get_screen_threats_query_adapter(self):
        """Test GET /threats/screen adapter with query parameters."""
        resp = client.get("/threats/screen?max_candidates=5&max_targets=1&screening_threshold_km=200")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "events" in data
        assert "summary" in data
        assert data["summary"]["protected_count"] == 1

    def test_post_default_body(self):
        """Test POST /threats/screen with empty body (defaults applied)."""
        resp = client.post("/threats/screen", json={"max_threat_candidates": 5, "max_protected_targets": 1})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "summary" in data
        assert data["summary"]["protected_count"] == 1


# ---------------------------------------------------------------------------
# Empty Results Handling
# ---------------------------------------------------------------------------

class TestThreatScreeningEmptyResults:
    def test_extremely_tight_threshold_returns_empty_list(self):
        """When distance threshold is tiny (e.g. 0.0001 km), 0 events should be returned gracefully."""
        payload = {
            "protected_norad_ids": [25544],
            "screening_threshold_km": 0.0001,
            "screening_window_hours": 12.0,
            "max_threat_candidates": 5,
            "coarse_step_sec": 300.0,
        }
        resp = client.post("/threats/screen", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["events"] == []
        assert data["summary"]["events_within_threshold"] == 0
        assert data["summary"]["pairs_evaluated"] <= 5


# ---------------------------------------------------------------------------
# Parameter Validation (422)
# ---------------------------------------------------------------------------

class TestThreatScreeningValidation:
    def test_negative_screening_threshold(self):
        resp = client.post("/threats/screen", json={"screening_threshold_km": -10.0})
        assert resp.status_code == 422

    def test_zero_window_hours(self):
        resp = client.post("/threats/screen", json={"screening_window_hours": 0.0})
        assert resp.status_code == 422

    def test_window_hours_exceeding_max(self):
        resp = client.post("/threats/screen", json={"screening_window_hours": 200.0})
        assert resp.status_code == 422

    def test_max_candidates_too_large(self):
        resp = client.post("/threats/screen", json={"max_threat_candidates": 300})
        assert resp.status_code == 422

    def test_invalid_stale_data_policy(self):
        resp = client.post("/threats/screen", json={"stale_data_policy": "discard"})
        assert resp.status_code == 422

    def test_invalid_stale_policy_in_get(self):
        resp = client.get("/threats/screen?stale_policy=discard")
        assert resp.status_code == 422

    def test_negative_protected_norad_id(self):
        resp = client.post("/threats/screen", json={"protected_norad_ids": [-5]})
        assert resp.status_code == 422

    def test_too_many_protected_norad_ids(self):
        ids = list(range(1, 55))
        resp = client.post("/threats/screen", json={"protected_norad_ids": ids})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Not Found & Error Handling
# ---------------------------------------------------------------------------

class TestThreatScreeningErrors:
    def test_unknown_protected_norad_id(self):
        """Unknown protected NORAD ID must return 404 with clear message."""
        payload = {
            "protected_norad_ids": [99999999],
            "max_threat_candidates": 5,
        }
        resp = client.post("/threats/screen", json=payload)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_missing_gp_dataset(self):
        """Missing GP dataset must return 503 Service Unavailable."""
        with patch.object(Path, "exists", return_value=False):
            resp = client.post("/threats/screen", json={"max_threat_candidates": 5})
            assert resp.status_code == 503
            assert "unavailable" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Freshness & Stale Data Warnings
# ---------------------------------------------------------------------------

class TestThreatScreeningDataFreshness:
    def test_stale_data_warning_in_screening_notes(self):
        """When max_epoch_age_days is tiny (e.g. 0.0001 days), objects are flagged stale."""
        payload = {
            "protected_norad_ids": [25544],
            "screening_threshold_km": 500.0,
            "screening_window_hours": 24.0,
            "max_threat_candidates": 5,
            "max_epoch_age_days": 0.00001,
            "stale_data_policy": "flag",
            "coarse_step_sec": 120.0,
        }
        resp = client.post("/threats/screen", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        for ev in data["events"]:
            # Stale objects should have STALE ORBITAL DATA warning in screening_notes
            assert any("STALE ORBITAL DATA" in note for note in ev["screening_notes"])

    def test_stale_data_exclude_policy(self):
        """When stale_data_policy is 'exclude', stale objects are omitted from screening."""
        payload = {
            "protected_norad_ids": [25544],
            "max_threat_candidates": 5,
            "max_epoch_age_days": 30.0,
            "stale_data_policy": "exclude",
        }
        resp = client.post("/threats/screen", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["summary"]["protected_count"] == 1
        for ev in data["events"]:
            assert not any("STALE ORBITAL DATA" in note for note in ev.get("screening_notes", []))

    def test_explicit_protected_id_stale_policy_exclude_with_tiny_epoch_returns_422(self):
        """Explicit protected NORAD ID that is stale + stale_policy=exclude returns 422, not 500."""
        payload = {
            "protected_norad_ids": [25544],
            "max_threat_candidates": 5,
            "max_epoch_age_days": 0.00001,  # forces 25544 to be stale
            "stale_data_policy": "exclude",
        }
        resp = client.post("/threats/screen", json=payload)
        assert resp.status_code == 422
        assert "stale" in resp.json()["detail"].lower()

    def test_default_sampling_all_stale_policy_exclude_returns_empty_summary(self):
        """When no protected IDs specified and all objects are stale under 'exclude', returns 200 with 0 candidates."""
        payload = {
            "max_threat_candidates": 5,
            "max_epoch_age_days": 0.00001,
            "stale_data_policy": "exclude",
        }
        resp = client.post("/threats/screen", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["summary"]["candidates_screened"] == 0
        assert data["summary"]["protected_count"] == 0
        assert data["events"] == []

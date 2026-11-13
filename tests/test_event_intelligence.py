"""Unit and integration tests for Event Intelligence (Layer 6 / Feature 2).

Tests:
  - EventClassifier rule-based categorization
  - EventStore SQLite CRUD, idempotency, and filtering
  - FastAPI /events endpoints
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.events.classifier import (
    ORBIT_DECAY,
    ORBIT_RAISE,
    STATION_KEEPING,
    UNKNOWN,
    EventClassifier,
)
from backend.events.event_store import EventStore
from backend.main import app


# ===========================================================================
# Classifier Unit Tests
# ===========================================================================

class TestEventClassifier:
    """Validate deterministic rule-based maneuver classification."""

    def setup_method(self):
        self.classifier = EventClassifier()

    def test_classify_orbit_raise(self):
        features = {
            "d_altitude_km": 3.5,
            "d_speed_km_s": 0.02,
        }
        classification, explanation = self.classifier.classify(features, anomaly_score=0.55)
        assert classification == ORBIT_RAISE
        assert "orbit-raising" in explanation.lower()

    def test_classify_orbit_decay(self):
        features = {
            "d_altitude_km": -2.5,
            "d_speed_km_s": -0.005,
        }
        classification, explanation = self.classifier.classify(features, anomaly_score=0.15)
        assert classification == ORBIT_DECAY
        assert "decay" in explanation.lower()

    def test_classify_station_keeping(self):
        features = {
            "d_altitude_km": 0.4,
            "d_speed_km_s": 0.012,
        }
        classification, explanation = self.classifier.classify(features, anomaly_score=0.45)
        assert classification == STATION_KEEPING
        assert "station-keeping" in explanation.lower()

    def test_classify_unknown(self):
        features = {
            "d_altitude_km": 0.1,
            "d_speed_km_s": 0.001,
        }
        classification, explanation = self.classifier.classify(features, anomaly_score=0.1)
        assert classification == UNKNOWN
        assert "insufficient evidence" in explanation.lower()


# ===========================================================================
# EventStore Unit Tests (Isolated SQLite Temp DB)
# ===========================================================================

class TestEventStore:
    """Validate SQLite persistence, idempotency, and querying."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        db_file = tmp_path / "test_events.db"
        self.store = EventStore(db_path=db_file)
        self.store.initialize()
        yield
        self.store.close()

    def test_upsert_and_retrieve_event(self):
        event = {
            "norad_id": 25544,
            "object_name": "ISS (ZARYA)",
            "event_type": "ANOMALY",
            "classification": ORBIT_RAISE,
            "classification_explanation": "Test orbit raise",
            "detected_at": "2026-11-13T12:00:00Z",
            "anomaly_score": 0.75,
        }
        event_id = self.store.upsert_event(event)
        assert isinstance(event_id, str)
        assert len(event_id) == 16

        fetched = self.store.get_event_by_id(event_id)
        assert fetched is not None
        assert fetched["norad_id"] == 25544
        assert fetched["object_name"] == "ISS (ZARYA)"
        assert fetched["classification"] == ORBIT_RAISE
        assert fetched["anomaly_score"] == 0.75

    def test_idempotency_duplicate_upsert(self):
        event = {
            "norad_id": 25544,
            "event_type": "CONJUNCTION",
            "detected_at": "2026-11-13T12:00:00Z",
        }
        id1 = self.store.upsert_event(event)
        id2 = self.store.upsert_event(event)
        assert id1 == id2
        assert self.store.count_events() == 1

    def test_filter_events_by_norad(self):
        self.store.upsert_event({"norad_id": 11111, "event_type": "ANOMALY", "detected_at": "2026-11-13T10:00:00Z"})
        self.store.upsert_event({"norad_id": 22222, "event_type": "ANOMALY", "detected_at": "2026-11-13T11:00:00Z"})

        filtered = self.store.get_events(norad_id=11111)
        assert len(filtered) == 1
        assert filtered[0]["norad_id"] == 11111

    def test_filter_events_by_type(self):
        self.store.upsert_event({"norad_id": 11111, "event_type": "ANOMALY", "detected_at": "2026-11-13T10:00:00Z"})
        self.store.upsert_event({"norad_id": 11111, "event_type": "THREAT", "detected_at": "2026-11-13T11:00:00Z"})

        threats = self.store.get_events(event_type="THREAT")
        assert len(threats) == 1
        assert threats[0]["event_type"] == "THREAT"


# ===========================================================================
# API Integration Tests
# ===========================================================================

client = TestClient(app)


def test_api_list_events():
    response = client.get("/events")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert "total" in data
    assert isinstance(data["events"], list)


def test_api_post_and_get_event():
    payload = {
        "norad_id": 99999,
        "object_name": "SYNTHETIC-SAT",
        "event_type": "CONJUNCTION",
        "classification": "UNKNOWN",
        "classification_explanation": "Test event",
        "detected_at": "2026-11-13T14:00:00Z",
        "miss_distance_km": 1.25,
        "rel_speed_km_s": 14.2,
    }
    post_res = client.post("/events", json=payload)
    assert post_res.status_code == 200
    created = post_res.json()
    assert created["norad_id"] == 99999
    assert created["miss_distance_km"] == 1.25

    # Retrieve by ID
    event_id = created["id"]
    get_res = client.get(f"/events/{event_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == event_id


def test_api_stats():
    res = client.get("/events/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "by_type" in data


"""
Event Intelligence — Pydantic schemas for the /events API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Response model — mirrors the SQLite events table
# ---------------------------------------------------------------------------

class EventResponse(BaseModel):
    """Full representation of a stored event record."""

    id: str
    norad_id: int
    object_name: Optional[str] = None
    event_type: str                        # ANOMALY | CONJUNCTION | THREAT
    classification: Optional[str] = None  # STATION_KEEPING | ORBIT_RAISE | ORBIT_DECAY | UNKNOWN
    classification_explanation: Optional[str] = None
    detected_at: str                       # ISO-8601 UTC
    orbital_epoch: Optional[str] = None
    anomaly_score: Optional[float] = None
    threat_score: Optional[float] = None
    tca: Optional[str] = None             # time of closest approach (conjunction/threat)
    miss_distance_km: Optional[float] = None
    rel_speed_km_s: Optional[float] = None
    data_source: Optional[str] = "CelesTrak GP CSV"
    created_at: str                        # ISO-8601 UTC


class EventListResponse(BaseModel):
    """Paginated list of events with metadata."""

    events: list[EventResponse]
    total: int
    disclaimer: str = (
        "Event classifications are rule-based heuristics, not certified "
        "operational assessments. Data sourced from CelesTrak GP CSV."
    )


# ---------------------------------------------------------------------------
# Request model — for POST /events
# ---------------------------------------------------------------------------

class LogEventRequest(BaseModel):
    """Payload for logging a new event into the persistent timeline."""

    norad_id: int = Field(..., description="NORAD catalog ID of the space object.")
    object_name: Optional[str] = Field(None, description="Human-readable object name.")
    event_type: str = Field(
        ...,
        description="Event category: 'ANOMALY', 'CONJUNCTION', or 'THREAT'.",
    )
    detected_at: Optional[str] = Field(
        None,
        description=(
            "ISO-8601 UTC timestamp of detection. "
            "Defaults to server time if omitted."
        ),
    )
    classification: Optional[str] = Field(
        None,
        description="Maneuver classification (ORBIT_RAISE, ORBIT_DECAY, STATION_KEEPING, UNKNOWN).",
    )
    classification_explanation: Optional[str] = Field(
        None,
        description="Human-readable explanation of the classification.",
    )
    anomaly_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="IsolationForest anomaly score [0, 1]."
    )
    threat_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="4-factor risk score [0, 1]."
    )
    tca: Optional[str] = Field(
        None, description="Time of closest approach (ISO-8601 UTC); for conjunction/threat events."
    )
    miss_distance_km: Optional[float] = Field(
        None, description="Miss distance at TCA in km."
    )
    rel_speed_km_s: Optional[float] = Field(
        None, description="Relative speed at TCA in km/s."
    )
    orbital_epoch: Optional[str] = Field(
        None, description="Epoch of the TLE/GP data used (ISO-8601 UTC)."
    )

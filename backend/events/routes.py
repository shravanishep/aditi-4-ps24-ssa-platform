"""FastAPI route definitions for Event Intelligence and Persistent Event Timeline.

Exposes endpoints for querying historical events, logging new events, and retrieving stats.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.events.event_store import EventStore, _now_utc_iso
from backend.events.schemas import EventListResponse, EventResponse, LogEventRequest

router = APIRouter()
_store = EventStore()


@router.get("", response_model=EventListResponse)
def list_events(
    norad_id: Optional[int] = Query(None, description="Filter by NORAD ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type (ANOMALY, CONJUNCTION, THREAT)"),
    classification: Optional[str] = Query(None, description="Filter by maneuver classification"),
    since: Optional[str] = Query(None, description="ISO-8601 lower bound on detected_at"),
    until: Optional[str] = Query(None, description="ISO-8601 upper bound on detected_at"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> EventListResponse:
    """List historical orbital events with optional filters."""
    _store.initialize()
    events_raw = _store.get_events(
        norad_id=norad_id,
        event_type=event_type,
        classification=classification,
        since=since,
        until=until,
        limit=limit,
    )
    items = [EventResponse(**ev) for ev in events_raw]
    total = _store.count_events()
    return EventListResponse(events=items, total=total)


@router.get("/stats")
def get_event_stats() -> dict:
    """Return summary statistics of stored events by category and classification."""
    _store.initialize()
    return _store.stats_by_type_and_classification()


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: str) -> EventResponse:
    """Retrieve details for a single event by ID."""
    _store.initialize()
    event = _store.get_event_by_id(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return EventResponse(**event)


@router.post("", response_model=EventResponse)
def create_event(req: LogEventRequest) -> EventResponse:
    """Log an event into the persistent timeline (idempotent; duplicates are ignored)."""
    _store.initialize()
    detected_at = req.detected_at or _now_utc_iso()
    
    event_dict = req.model_dump()
    event_dict["detected_at"] = detected_at

    event_id = _store.upsert_event(event_dict)
    event_record = _store.get_event_by_id(event_id)
    if event_record is None:
        raise HTTPException(status_code=500, detail="Failed to retrieve stored event")
    return EventResponse(**event_record)


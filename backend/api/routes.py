"""FastAPI route definitions for the ADITI SSA Platform API.

Each route is a thin adapter that:
  1. Validates request input via Pydantic schemas.
  2. Calls the appropriate Layer 1-3 function.
  3. Serialises the result back through a Pydantic response schema.

No orbital propagation, distance, or conjunction logic lives here.
"""

from __future__ import annotations

from datetime import timezone
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend.orbital.conjunction import find_closest_approach
from backend.orbital.gp_loader import get_satellite_by_norad, load_gp_data
from backend.orbital.sgp4_propagator import propagate_orbit

from .schemas import (
    CloseApproachResultResponse,
    ConjunctionAnalysisRequest,
    PropagatedOrbitStateResponse,
    SatelliteBasicInfo,
    SatelliteGPInfo,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Dataset path — resolved relative to the project root.
# ---------------------------------------------------------------------------
_GP_CSV = Path(__file__).resolve().parents[2] / "data" / "raw" / "active_satellites_gp.csv"


def _gp_row_to_info(row: pd.Series) -> SatelliteGPInfo:
    """Convert a GP CSV row to a SatelliteGPInfo response model."""
    return SatelliteGPInfo(
        norad_cat_id=int(row["NORAD_CAT_ID"]),
        object_name=str(row.get("OBJECT_NAME", "")).strip(),
        object_id=str(row.get("OBJECT_ID", "")).strip() or None,
        epoch=str(row["EPOCH"]),
        mean_motion=float(row["MEAN_MOTION"]),
        eccentricity=float(row["ECCENTRICITY"]),
        inclination=float(row["INCLINATION"]),
        ra_of_asc_node=float(row["RA_OF_ASC_NODE"]),
        arg_of_pericenter=float(row["ARG_OF_PERICENTER"]),
        mean_anomaly=float(row["MEAN_ANOMALY"]),
        bstar=float(row["BSTAR"]),
        mean_motion_dot=float(row["MEAN_MOTION_DOT"]),
        mean_motion_ddot=float(row["MEAN_MOTION_DDOT"]),
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", tags=["health"])
def health() -> dict:
    """Return a simple backend health response."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Satellites
# ---------------------------------------------------------------------------

@router.get("/satellites", response_model=list[SatelliteBasicInfo], tags=["satellites"])
def list_satellites(
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum number of satellites to return.")] = 100,
) -> list[SatelliteBasicInfo]:
    """Return a limited list of satellites from the GP dataset."""
    df = load_gp_data(_GP_CSV)
    subset = df.head(limit)
    return [
        SatelliteBasicInfo(
            norad_cat_id=int(row["NORAD_CAT_ID"]),
            object_name=str(row.get("OBJECT_NAME", "")).strip(),
        )
        for _, row in subset.iterrows()
    ]


@router.get("/satellites/{norad_id}", response_model=SatelliteGPInfo, tags=["satellites"])
def get_satellite(norad_id: int) -> SatelliteGPInfo:
    """Return the GP orbital information for the requested NORAD ID."""
    try:
        row = get_satellite_by_norad(norad_id, _GP_CSV)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _gp_row_to_info(row)


# ---------------------------------------------------------------------------
# Orbit propagation
# ---------------------------------------------------------------------------

@router.get(
    "/satellites/{norad_id}/orbit",
    response_model=PropagatedOrbitStateResponse,
    tags=["satellites"],
)
def get_orbit(
    norad_id: int,
    timestamp: Annotated[
        str,
        Query(description="UTC or offset-aware ISO-8601 timestamp (e.g. 2026-09-20T10:00:00Z)."),
    ],
) -> PropagatedOrbitStateResponse:
    """Propagate the satellite to the requested timestamp and return the orbital state."""
    from datetime import datetime

    # Parse and validate timestamp.
    # NB: In query strings, "+" is URL-decoded as a space by some clients,
    # so "2026-09-20T15:30:00+05:30" may arrive as "2026-09-20T15:30:00 05:30".
    # Restore the "+" to preserve timezone offsets before parsing.
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00").replace(" ", "+"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid timestamp format: {exc}",
        ) from exc

    if dt.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Timestamp must be timezone-aware "
                "(e.g. 2026-09-20T10:00:00Z or 2026-09-20T15:30:00+05:30)."
            ),
        )

    # Normalize to UTC
    dt_utc = dt.astimezone(timezone.utc)

    # Fetch GP row
    try:
        row = get_satellite_by_norad(norad_id, _GP_CSV)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Propagate via Layer 1
    try:
        state = propagate_orbit(row, dt_utc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PropagatedOrbitStateResponse(
        object_name=state.object_name,
        norad_cat_id=state.norad_cat_id,
        timestamp=state.timestamp,
        position_x_km=state.position_x_km,
        position_y_km=state.position_y_km,
        position_z_km=state.position_z_km,
        velocity_x_km_s=state.velocity_x_km_s,
        velocity_y_km_s=state.velocity_y_km_s,
        velocity_z_km_s=state.velocity_z_km_s,
        sgp4_error=state.sgp4_error,
        error_message=state.error_message,
    )


# ---------------------------------------------------------------------------
# Conjunction analysis
# ---------------------------------------------------------------------------

@router.post(
    "/conjunction/analyze",
    response_model=CloseApproachResultResponse,
    tags=["conjunction"],
)
def analyze_conjunction(body: ConjunctionAnalysisRequest) -> CloseApproachResultResponse:
    """Perform a close-approach analysis between two satellites using Layer 3.

    This returns an analytical prediction based on SGP4 propagation and
    public orbital data.  It is NOT a collision probability or
    operational collision-avoidance result.
    """
    # Normalize both timestamps to UTC
    start_utc = body.start_time.astimezone(timezone.utc)
    end_utc = body.end_time.astimezone(timezone.utc)

    # Fetch both GP rows; return 404 for unknown IDs
    try:
        row1 = get_satellite_by_norad(body.norad1, _GP_CSV)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Satellite 1 not found: {exc}",
        ) from exc

    try:
        row2 = get_satellite_by_norad(body.norad2, _GP_CSV)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Satellite 2 not found: {exc}",
        ) from exc

    # Delegate all conjunction math to Layer 3
    try:
        result = find_closest_approach(
            sat1_row=row1,
            sat2_row=row2,
            start_time=start_utc,
            end_time=end_utc,
            threshold_km=body.threshold_km,
            coarse_step_sec=body.coarse_step_sec,
            fine_step_sec=body.fine_step_sec,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return CloseApproachResultResponse(
        object1_norad_id=result.object1_norad_id,
        object2_norad_id=result.object2_norad_id,
        object1_name=result.object1_name,
        object2_name=result.object2_name,
        analysis_start_time=result.analysis_start_time,
        analysis_end_time=result.analysis_end_time,
        time_of_closest_approach=result.time_of_closest_approach,
        minimum_separation_km=result.minimum_separation_km,
        relative_speed_km_s=result.relative_speed_km_s,
        threshold_km=result.threshold_km,
        is_candidate_close_approach=result.is_candidate_close_approach,
        error_message=result.error_message,
    )

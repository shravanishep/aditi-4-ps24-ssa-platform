"""Pydantic request and response schemas for the Layer 4 API service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SatelliteBasicInfo(BaseModel):
    """Minimal satellite record returned by the list endpoint."""

    norad_cat_id: int
    object_name: str


class SatelliteGPInfo(SatelliteBasicInfo):
    """Full GP orbital fields returned by the individual satellite endpoint."""

    object_id: Optional[str] = None
    epoch: str
    mean_motion: float
    eccentricity: float
    inclination: float
    ra_of_asc_node: float
    arg_of_pericenter: float
    mean_anomaly: float
    bstar: float
    mean_motion_dot: float
    mean_motion_ddot: float


class PropagatedOrbitStateResponse(BaseModel):
    """Propagated orbital state returned by the orbit endpoint.

    All positions are in km (TEME frame), velocities in km/s.
    """

    object_name: str
    norad_cat_id: int
    timestamp: datetime
    position_x_km: float
    position_y_km: float
    position_z_km: float
    velocity_x_km_s: float
    velocity_y_km_s: float
    velocity_z_km_s: float
    sgp4_error: int
    error_message: str


class ConjunctionAnalysisRequest(BaseModel):
    """Request body for the conjunction analysis endpoint."""

    norad1: int = Field(..., description="NORAD catalog ID of the first satellite.")
    norad2: int = Field(..., description="NORAD catalog ID of the second satellite.")
    start_time: datetime = Field(
        ..., description="Analysis window start (must be timezone-aware ISO-8601)."
    )
    end_time: datetime = Field(
        ..., description="Analysis window end (must be timezone-aware ISO-8601)."
    )
    threshold_km: float = Field(
        ..., gt=0, description="Candidate close approach threshold in km."
    )
    coarse_step_sec: float = Field(
        60.0, gt=0, description="Coarse search step in seconds."
    )
    fine_step_sec: float = Field(
        1.0, gt=0, description="Fine search step in seconds."
    )

    @field_validator("start_time", "end_time", mode="after")
    @classmethod
    def require_timezone(cls, v: datetime) -> datetime:
        """Reject timezone-naive timestamps."""
        if v.tzinfo is None:
            raise ValueError(
                "Timestamps must be timezone-aware "
                "(e.g. 2026-09-20T10:00:00Z or 2026-09-20T15:30:00+05:30)."
            )
        return v


class CloseApproachResultResponse(BaseModel):
    """Structured conjunction analysis result.

    Distances in km, speeds in km/s, times as UTC ISO-8601 strings.
    This represents an analytical close-approach prediction based on
    SGP4 propagation and public orbital data.  It is NOT a collision
    probability or operational collision-avoidance output.
    """

    object1_norad_id: int
    object2_norad_id: int
    object1_name: str
    object2_name: str
    analysis_start_time: datetime
    analysis_end_time: datetime
    time_of_closest_approach: datetime
    minimum_separation_km: float
    relative_speed_km_s: float
    threshold_km: float
    is_candidate_close_approach: bool
    error_message: str

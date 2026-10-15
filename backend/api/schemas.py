"""Pydantic request and response schemas for the Layer 4 API service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

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


class TrajectoryPointResponse(BaseModel):
    """One SGP4-propagated state in a trajectory sequence.

    Position in km (TEME frame), velocity in km/s.
    """

    timestamp: datetime
    position_x_km: float
    position_y_km: float
    position_z_km: float
    velocity_x_km_s: float
    velocity_y_km_s: float
    velocity_z_km_s: float
    sgp4_error: int


class TrajectoryResponse(BaseModel):
    """Multi-point trajectory for one satellite.

    Positions in km (TEME frame), velocities in km/s.
    Points with sgp4_error != 0 are included so the caller
    can decide how to handle partial failures.
    """

    norad_cat_id: int
    object_name: str
    frame: str  # always "TEME" — Cesium transform required before display
    step_sec: float
    points: list[TrajectoryPointResponse]


# ---------------------------------------------------------------------------
# Layer 11 — Threat Prioritization Schemas
# ---------------------------------------------------------------------------

class ThreatScreeningRequest(BaseModel):
    """Request parameters for threat screening and prioritization."""

    protected_norad_ids: Optional[list[int]] = Field(
        default=None,
        description=(
            "Optional explicit list of protected NORAD IDs to screen (max 50). "
            "If omitted, the first max_protected_targets active satellites from the catalogue are screened."
        ),
    )
    protect_all_active: bool = Field(
        default=False,
        description="If True, screen active satellites from the catalogue against candidate threats.",
    )
    max_protected_targets: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of protected satellites to evaluate when protected_norad_ids is omitted.",
    )
    screening_threshold_km: float = Field(
        default=50.0,
        gt=0.0,
        le=1000.0,
        description="Close approach distance threshold in km (0 < threshold <= 1000).",
    )
    screening_window_hours: float = Field(
        default=48.0,
        gt=0.0,
        le=168.0,
        description="Forward-looking propagation window in hours (0 < hours <= 168).",
    )
    max_threat_candidates: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum number of candidate threat objects to screen against each target.",
    )
    max_ranked_results: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of ranked threat events to return.",
    )
    coarse_step_sec: float = Field(
        default=60.0,
        ge=10.0,
        le=3600.0,
        description="Coarse conjunction search step in seconds [10.0, 3600.0].",
    )
    fine_step_sec: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Fine conjunction search step in seconds [0.1, 60.0].",
    )
    max_epoch_age_days: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Optional maximum epoch age in days for stale orbital data detection.",
    )
    stale_data_policy: str = Field(
        default="flag",
        description="Data freshness policy: 'flag' (include with visible warning) or 'exclude' (omit stale objects).",
    )

    @field_validator("stale_data_policy")
    @classmethod
    def validate_policy(cls, v: str) -> str:
        """Validate stale data policy."""
        if v not in ("flag", "exclude"):
            raise ValueError("stale_data_policy must be either 'flag' or 'exclude'.")
        return v

    @field_validator("protected_norad_ids")
    @classmethod
    def validate_protected_ids(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        """Validate explicit protected NORAD IDs."""
        if v is not None:
            if len(v) > 50:
                raise ValueError("Cannot screen more than 50 protected NORAD IDs in a single request.")
            for nid in v:
                if nid <= 0:
                    raise ValueError(f"NORAD ID must be a positive integer, got {nid}.")
        return v


class ThreatEventResponse(BaseModel):
    """Structured threat event returned by the threat prioritization API.

    Distances in km, velocities in km/s, times in UTC.
    The risk_score is a heuristic ranking metric, NOT a collision probability (Pc).
    """

    protected_norad_id: int
    protected_name: str
    protected_classification: str
    threat_norad_id: int
    threat_name: str
    threat_classification: str
    threat_source_provenance: str
    time_of_closest_approach: datetime
    minimum_separation_km: float
    relative_speed_km_s: float
    hours_to_tca: float
    threat_anomaly_score: Optional[float] = None
    threat_anomaly_severity: str = "unavailable"
    risk_score: float
    risk_severity: str
    risk_explanation: dict[str, Any]
    screening_notes: list[str]


class ThreatScreeningSummary(BaseModel):
    """Summary metadata and operational constraints for a threat screening run."""

    protected_count: int
    candidates_screened: int
    pairs_evaluated: int
    events_within_threshold: int
    data_source_notes: list[str]
    config_summary: dict[str, Any]
    disclaimer: str


class ThreatScreeningResponse(BaseModel):
    """Structured response container for ranked threat screening events."""

    events: list[ThreatEventResponse]
    summary: ThreatScreeningSummary


class SourceFreshnessResponse(BaseModel):
    """Status metadata for an individual catalogue data source."""

    source_name: str
    url: str
    dest_path: str
    retrieved_at: Optional[str] = None
    success: bool
    error_message: Optional[str] = None
    bytes_downloaded: int = 0
    total_records: int = 0
    valid_records: int = 0
    rejected_records: int = 0
    oldest_epoch: Optional[str] = None
    newest_epoch: Optional[str] = None
    max_epoch_age_days: Optional[float] = None
    stale_records_count: int = 0
    classification_source: str = "unknown"


class CatalogStatusResponse(BaseModel):
    """Read-only catalogue and data refresh status response."""

    last_refresh_attempt: Optional[str] = None
    last_successful_refresh: Optional[str] = None
    refresh_status: str  # "success", "failed", "partial", "unrefreshed"
    total_objects: int
    active_satellites: int
    with_orbital_data: int
    stale_objects: int
    oldest_epoch: Optional[str] = None
    newest_epoch: Optional[str] = None
    max_epoch_age_days: Optional[float] = None
    sources: dict[str, SourceFreshnessResponse]
    warnings: list[str]
    data_source_notes: list[str]
    disclaimer: str
    orbit_regimes: dict[str, int] = Field(
        default_factory=dict,
        description="Count of objects by orbital regime (LEO, MEO, GEO, Other).",
    )
    classifications: dict[str, int] = Field(
        default_factory=dict,
        description="Count of objects by classification category.",
    )


class MultiPropagatedObjectState(BaseModel):
    """Propagated orbital state and metadata for a single space object at a point in time."""

    norad_cat_id: int
    object_name: str
    classification: str
    classification_source: str
    epoch: Optional[str] = None
    epoch_age_days: Optional[float] = None
    is_stale: bool = False
    position_x_km: float
    position_y_km: float
    position_z_km: float
    velocity_x_km_s: float
    velocity_y_km_s: float
    velocity_z_km_s: float
    altitude_km: float
    speed_km_s: float
    sgp4_error: int


class MultiPropagatedOrbitResponse(BaseModel):
    """Response containing bounded propagated states for multiple catalogued space objects."""

    timestamp: datetime
    total_matching: int
    propagated_count: int
    objects: list[MultiPropagatedObjectState]
    data_source_notes: list[str]
    disclaimer: str

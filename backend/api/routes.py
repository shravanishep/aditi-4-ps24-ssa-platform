"""FastAPI route definitions for the ADITI SSA Platform API.

Each route is a thin adapter that:
  1. Validates request input via Pydantic schemas.
  2. Calls the appropriate Layer 1-3 function.
  3. Serialises the result back through a Pydantic response schema.

No orbital propagation, distance, or conjunction logic lives here.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend.catalog import (
    CatalogConfig,
    GPSourceConfig,
    ObjectClassification,
    UnifiedCatalog,
    build_unified_catalog,
)
from backend.orbital.conjunction import find_closest_approach
from backend.orbital.gp_loader import get_satellite_by_norad, load_gp_data
from backend.orbital.sgp4_propagator import propagate_orbit
from ml.models.threat_config import ThreatConfig
from ml.models.threat_prioritization import screen_threats_from_catalog

from backend.refresh.metadata import RefreshMetadata

from .schemas import (
    CatalogStatusResponse,
    CloseApproachResultResponse,
    ConjunctionAnalysisRequest,
    MultiPropagatedObjectState,
    MultiPropagatedOrbitResponse,
    PropagatedOrbitStateResponse,
    SatelliteBasicInfo,
    SatelliteGPInfo,
    SourceFreshnessResponse,
    ThreatEventResponse,
    ThreatScreeningRequest,
    ThreatScreeningResponse,
    ThreatScreeningSummary,
    TrajectoryPointResponse,
    TrajectoryResponse,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Dataset paths — resolved relative to the project root.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_GP_CSV = _PROJECT_ROOT / "data" / "raw" / "active_satellites_gp.csv"
_SATCAT_CSV = _PROJECT_ROOT / "data" / "raw" / "satcat.csv"
_METADATA_PATH = _PROJECT_ROOT / "data" / "catalog_refresh_metadata.json"

_DEFAULT_CATALOG_CACHE: tuple[float, float, UnifiedCatalog] | None = None


def invalidate_catalog_cache() -> None:
    """Invalidate in-process cached UnifiedCatalog instance."""
    global _DEFAULT_CATALOG_CACHE
    _DEFAULT_CATALOG_CACHE = None


def _get_or_build_catalog(
    max_epoch_age_days: float | None = None,
    stale_data_policy: str = "flag",
) -> UnifiedCatalog:
    """Retrieve cached default UnifiedCatalog or build configured catalogue."""
    global _DEFAULT_CATALOG_CACHE

    if not _GP_CSV.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Orbital dataset unavailable: {_GP_CSV.name} not found.",
        )

    # If non-default freshness filtering is requested, build a fresh catalogue
    if max_epoch_age_days is not None or stale_data_policy != "flag":
        cfg = CatalogConfig(
            gp_sources=[
                GPSourceConfig(
                    source_name="active_satellites_gp",
                    path=_GP_CSV,
                    category_hint=ObjectClassification.ACTIVE_SATELLITE,
                    enabled=True,
                )
            ],
            satcat_path=_SATCAT_CSV if _SATCAT_CSV.exists() else None,
            allow_remote_fetch=False,
            max_epoch_age_days=max_epoch_age_days,
            stale_data_policy=stale_data_policy,
        )
        return build_unified_catalog(cfg)

    # Check modification timestamps of both GP data and SATCAT metadata files
    try:
        gp_mtime = _GP_CSV.stat().st_mtime if _GP_CSV.exists() else 0.0
    except OSError:
        gp_mtime = 0.0

    try:
        satcat_mtime = _SATCAT_CSV.stat().st_mtime if _SATCAT_CSV.exists() else 0.0
    except OSError:
        satcat_mtime = 0.0

    if _DEFAULT_CATALOG_CACHE is not None:
        cached_gp_mtime, cached_satcat_mtime, cached_cat = _DEFAULT_CATALOG_CACHE
        if cached_gp_mtime == gp_mtime and cached_satcat_mtime == satcat_mtime:
            return cached_cat

    cfg = CatalogConfig(
        gp_sources=[
            GPSourceConfig(
                source_name="active_satellites_gp",
                path=_GP_CSV,
                category_hint=ObjectClassification.ACTIVE_SATELLITE,
                enabled=True,
            )
        ],
        satcat_path=_SATCAT_CSV if _SATCAT_CSV.exists() else None,
        allow_remote_fetch=False,
        max_epoch_age_days=None,
        stale_data_policy="flag",
    )
    cat = build_unified_catalog(cfg)
    _DEFAULT_CATALOG_CACHE = (gp_mtime, satcat_mtime, cat)
    return cat


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


@router.get(
    "/satellites/multi-propagate",
    response_model=MultiPropagatedOrbitResponse,
    tags=["satellites"],
)
def multi_propagate_satellites(
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Max objects to propagate (bounded [1, 200])."),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Pagination offset into matching catalogue objects."),
    ] = 0,
    target_time: Annotated[
        str | None,
        Query(description="Target UTC ISO timestamp for SGP4 propagation. Defaults to now."),
    ] = None,
    category: Annotated[
        str | None,
        Query(description="Filter by classification, e.g. ACTIVE_SATELLITE, INACTIVE_SATELLITE."),
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Search substring in object name or NORAD ID."),
    ] = None,
    regime: Annotated[
        str | None,
        Query(description="Filter by orbital regime (LEO, MEO, GEO, OTHER)."),
    ] = None,
    norad_ids: Annotated[
        str | None,
        Query(description="Comma-separated explicit NORAD IDs to propagate."),
    ] = None,
) -> MultiPropagatedOrbitResponse:
    """Propagate a bounded set of catalogue objects to a specific UTC epoch for 3D multi-object visualization."""
    if target_time:
        try:
            target_dt = datetime.fromisoformat(target_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid target_time ISO format '{target_time}': {exc}",
            ) from exc
    else:
        target_dt = datetime.now(timezone.utc)

    catalog = _get_or_build_catalog()

    # Filter objects that have valid orbital records
    candidates = [
        o for o in catalog
        if o.has_orbital_data and o.orbital_record is not None
    ]

    # Filter by explicit NORAD IDs if requested
    if norad_ids:
        try:
            target_ids = {int(x.strip()) for x in norad_ids.split(",") if x.strip()}
            candidates = [o for o in candidates if o.norad_cat_id in target_ids]
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid comma-separated NORAD IDs in norad_ids query parameter: {exc}",
            ) from exc

    # Filter by classification if requested
    if category:
        cat_clean = category.strip().upper()
        candidates = [
            o for o in candidates
            if o.classification.value.upper() == cat_clean
            or o.classification.name.upper() == cat_clean
        ]

    # Filter by regime if requested
    if regime:
        reg_clean = regime.strip().upper()
        if reg_clean == "LEO":
            candidates = [
                o for o in candidates
                if o.orbital_record and float(o.orbital_record.get("MEAN_MOTION", 0.0)) >= 11.25
            ]
        elif reg_clean == "MEO":
            candidates = [
                o for o in candidates
                if o.orbital_record and 1.05 <= float(o.orbital_record.get("MEAN_MOTION", 0.0)) < 11.25
            ]
        elif reg_clean == "GEO":
            candidates = [
                o for o in candidates
                if o.orbital_record and 0.95 <= float(o.orbital_record.get("MEAN_MOTION", 0.0)) < 1.05
            ]
        elif reg_clean in ("OTHER", "HEO"):
            candidates = [
                o for o in candidates
                if o.orbital_record and float(o.orbital_record.get("MEAN_MOTION", 0.0)) < 0.95
            ]

    # Filter by search string if requested
    if search:
        s_clean = search.strip().upper()
        candidates = [
            o for o in candidates
            if s_clean in o.object_name.upper() or s_clean in str(o.norad_cat_id)
        ]

    total_matching = len(candidates)
    sliced_objs = candidates[offset : offset + limit]

    propagated_results: list[MultiPropagatedObjectState] = []
    for obj in sliced_objs:
        try:
            st = propagate_orbit(obj.orbital_record, target_dt)
            r_km = math.sqrt(st.position_x_km**2 + st.position_y_km**2 + st.position_z_km**2)
            alt_km = round(r_km - 6378.137, 2)
            v_kms = math.sqrt(st.velocity_x_km_s**2 + st.velocity_y_km_s**2 + st.velocity_z_km_s**2)
            speed_kms = round(v_kms, 4)

            propagated_results.append(
                MultiPropagatedObjectState(
                    norad_cat_id=obj.norad_cat_id,
                    object_name=obj.object_name,
                    classification=obj.classification.value,
                    classification_source=obj.classification_source,
                    epoch=obj.epoch.isoformat() if obj.epoch else None,
                    epoch_age_days=obj.epoch_age_days,
                    is_stale=obj.is_stale,
                    position_x_km=round(st.position_x_km, 4),
                    position_y_km=round(st.position_y_km, 4),
                    position_z_km=round(st.position_z_km, 4),
                    velocity_x_km_s=round(st.velocity_x_km_s, 6),
                    velocity_y_km_s=round(st.velocity_y_km_s, 6),
                    velocity_z_km_s=round(st.velocity_z_km_s, 6),
                    altitude_km=alt_km,
                    speed_km_s=speed_kms,
                    sgp4_error=st.sgp4_error,
                )
            )
        except Exception:
            # Skip propagation failures gracefully
            continue

    data_notes = [
        f"Catalogue contains {total_matching} matching objects with orbital data.",
        f"Propagated {len(propagated_results)} objects to {target_dt.isoformat()}.",
    ]
    if not _SATCAT_CSV.exists():
        data_notes.append("SATCAT metadata is not loaded; object classifications are based on source hints.")

    return MultiPropagatedOrbitResponse(
        timestamp=target_dt,
        total_matching=total_matching,
        propagated_count=len(propagated_results),
        objects=propagated_results,
        data_source_notes=data_notes,
        disclaimer=(
            "Positions are calculated via analytical SGP4 propagation from public orbital data. "
            "SGP4 error grows over time and positions are advisory for research visualization."
        ),
    )


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


def _parse_tz_timestamp(timestamp_str: str, field_name: str) -> datetime:
    """Parse and validate an ISO-8601 timestamp string ensuring timezone awareness."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00").replace(" ", "+"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field_name} timestamp format: {exc}",
        ) from exc

    if dt.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} must be timezone-aware "
                "(e.g. 2026-09-20T10:00:00Z or 2026-09-20T15:30:00+05:30)."
            ),
        )
    return dt


@router.get(
    "/satellites/{norad_id}/trajectory",
    response_model=TrajectoryResponse,
    tags=["satellites"],
)
def get_trajectory(
    norad_id: int,
    start: Annotated[
        str,
        Query(description="UTC or offset-aware ISO-8601 start timestamp."),
    ],
    end: Annotated[
        str,
        Query(description="UTC or offset-aware ISO-8601 end timestamp."),
    ],
    step_sec: Annotated[
        float,
        Query(ge=10.0, le=3600.0, description="Sampling step in seconds [10.0, 3600.0]."),
    ] = 60.0,
) -> TrajectoryResponse:
    """Sample an orbital trajectory sequence in the TEME frame using SGP4 propagation."""
    start_dt = _parse_tz_timestamp(start, "start")
    end_dt = _parse_tz_timestamp(end, "end")

    start_utc = start_dt.astimezone(timezone.utc)
    end_utc = end_dt.astimezone(timezone.utc)

    if end_utc <= start_utc:
        raise HTTPException(
            status_code=422,
            detail="end time must be strictly greater than start time.",
        )

    window_sec = (end_utc - start_utc).total_seconds()
    if window_sec > 86400.0:
        raise HTTPException(
            status_code=422,
            detail="Trajectory time window cannot exceed 24 hours (86400 seconds).",
        )

    try:
        row = get_satellite_by_norad(norad_id, _GP_CSV)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    points: list[TrajectoryPointResponse] = []
    current_t = start_utc
    step_delta = timedelta(seconds=step_sec)

    while current_t <= end_utc:
        state = propagate_orbit(row, current_t)
        points.append(
            TrajectoryPointResponse(
                timestamp=state.timestamp,
                position_x_km=state.position_x_km,
                position_y_km=state.position_y_km,
                position_z_km=state.position_z_km,
                velocity_x_km_s=state.velocity_x_km_s,
                velocity_y_km_s=state.velocity_y_km_s,
                velocity_z_km_s=state.velocity_z_km_s,
                sgp4_error=state.sgp4_error,
            )
        )
        current_t += step_delta

    return TrajectoryResponse(
        norad_cat_id=int(row["NORAD_CAT_ID"]),
        object_name=str(row.get("OBJECT_NAME", "")).strip(),
        frame="TEME",
        step_sec=step_sec,
        points=points,
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


# ---------------------------------------------------------------------------
# Threat Prioritization (Layer 11)
# ---------------------------------------------------------------------------

def _execute_threat_screening(
    request: ThreatScreeningRequest,
) -> ThreatScreeningResponse:
    """Execute threat screening pipeline using UnifiedCatalog and Layer 9 engine."""
    catalog = _get_or_build_catalog(
        max_epoch_age_days=request.max_epoch_age_days,
        stale_data_policy=request.stale_data_policy,
    )

    if len(catalog) == 0:
        return ThreatScreeningResponse(
            events=[],
            summary=ThreatScreeningSummary(
                protected_count=0,
                candidates_screened=0,
                pairs_evaluated=0,
                events_within_threshold=0,
                data_source_notes=["Catalogue contains 0 objects."],
                config_summary={},
                disclaimer="Catalogue contains no objects.",
            ),
        )

    # Protected targets selection
    if request.protected_norad_ids:
        # Check against available objects with orbital data (pre-stale-filter)
        catalog_orbital_ids = {o.norad_cat_id for o in catalog if o.has_orbital_data}
        missing = [nid for nid in request.protected_norad_ids if nid not in catalog_orbital_ids]
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Protected NORAD IDs not found with orbital data in catalogue: {missing}",
            )
        # When stale_data_policy="exclude", a protected target whose epoch is stale
        # will be absent from the gp_df that screen_threats operates on.
        # Detect this and return a clear 404 rather than an internal IndexError.
        if request.stale_data_policy == "exclude" and request.max_epoch_age_days is not None:
            exclude_stale_ids = {
                o.norad_cat_id for o in catalog
                if o.has_orbital_data and not o.is_stale
            }
            excluded_protected = [
                nid for nid in request.protected_norad_ids if nid not in exclude_stale_ids
            ]
            if excluded_protected:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Protected NORAD IDs {excluded_protected} have stale orbital data "
                        f"(epoch older than {request.max_epoch_age_days} days) and are excluded "
                        f"by stale_data_policy='exclude'. Use stale_data_policy='flag' to include "
                        f"them with a visible warning."
                    ),
                )
        protected_ids = sorted(request.protected_norad_ids)
    else:
        # Default: sample active satellites from catalogue up to max_protected_targets
        active_objs = catalog.get_active_satellites()
        if request.stale_data_policy == "exclude":
            active_objs = [o for o in active_objs if not o.is_stale]
        protected_ids = [
            o.norad_cat_id for o in active_objs if o.has_orbital_data
        ][: request.max_protected_targets]
        if not protected_ids:
            # Fallback to any objects with orbital data (respecting stale exclusion)
            fallback_objs = [
                o for o in catalog
                if o.has_orbital_data and (request.stale_data_policy != "exclude" or not o.is_stale)
            ]
            protected_ids = [
                o.norad_cat_id for o in fallback_objs
            ][: request.max_protected_targets]

        if not protected_ids:
            # No non-stale objects available to screen under exclude policy
            return ThreatScreeningResponse(
                events=[],
                summary=ThreatScreeningSummary(
                    protected_count=0,
                    candidates_screened=0,
                    pairs_evaluated=0,
                    events_within_threshold=0,
                    data_source_notes=[
                        f"No non-stale objects remain with orbital data under stale_data_policy='exclude' "
                        f"(max_epoch_age_days={request.max_epoch_age_days})."
                    ],
                    config_summary={
                        "stale_data_policy": request.stale_data_policy,
                        "max_epoch_age_days": request.max_epoch_age_days,
                    },
                    disclaimer=ThreatConfig().disclaimer,
                ),
            )

    try:
        threat_cfg = ThreatConfig(
            gp_csv_path=str(_GP_CSV),
            protected_norad_ids=protected_ids,
            protect_all_active=request.protect_all_active,
            screening_threshold_km=request.screening_threshold_km,
            screening_window_hours=request.screening_window_hours,
            coarse_step_sec=request.coarse_step_sec,
            fine_step_sec=request.fine_step_sec,
            max_threat_candidates=request.max_threat_candidates,
            max_ranked_results=request.max_ranked_results,
        )
        threat_cfg.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = screen_threats_from_catalog(
            catalog=catalog,
            config=threat_cfg,
            protected_ids=protected_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Threat screening calculation error: {exc}"
        ) from exc

    events = [
        ThreatEventResponse(
            protected_norad_id=e.protected_norad_id,
            protected_name=e.protected_name,
            protected_classification=e.protected_classification,
            threat_norad_id=e.threat_norad_id,
            threat_name=e.threat_name,
            threat_classification=e.threat_classification,
            threat_source_provenance=e.threat_source_provenance,
            time_of_closest_approach=e.time_of_closest_approach,
            minimum_separation_km=e.minimum_separation_km,
            relative_speed_km_s=e.relative_speed_km_s,
            hours_to_tca=e.hours_to_tca,
            threat_anomaly_score=e.threat_anomaly_score,
            threat_anomaly_severity=e.threat_anomaly_severity,
            risk_score=e.risk_score,
            risk_severity=e.risk_severity,
            risk_explanation=e.risk_explanation,
            screening_notes=e.screening_notes,
        )
        for e in result.events
    ]

    summary = ThreatScreeningSummary(
        protected_count=result.protected_count,
        candidates_screened=result.candidates_screened,
        pairs_evaluated=result.pairs_evaluated,
        events_within_threshold=result.events_within_threshold,
        data_source_notes=result.data_source_notes,
        config_summary=result.config_summary,
        disclaimer=threat_cfg.disclaimer,
    )

    return ThreatScreeningResponse(events=events, summary=summary)


@router.post(
    "/threats/screen",
    response_model=ThreatScreeningResponse,
    tags=["threats"],
)
def screen_threats_post(
    body: ThreatScreeningRequest | None = None,
) -> ThreatScreeningResponse:
    """Screen catalogued space objects for close approaches to protected satellites.

    Evaluates candidate threats using Layer 10 unified catalogue and Layer 9
    risk-prioritization heuristics.

    The returned threat score is a heuristic prioritization index for investigation,
    NOT a collision probability (Pc).
    """
    req = body if body is not None else ThreatScreeningRequest()
    return _execute_threat_screening(req)


@router.get(
    "/threats/screen",
    response_model=ThreatScreeningResponse,
    tags=["threats"],
)
def screen_threats_get(
    screening_threshold_km: Annotated[
        float,
        Query(gt=0.0, le=1000.0, description="Screening distance threshold in km."),
    ] = 50.0,
    screening_window_hours: Annotated[
        float,
        Query(gt=0.0, le=168.0, description="Propagation window in hours."),
    ] = 48.0,
    max_threat_candidates: Annotated[
        int,
        Query(ge=1, le=200, description="Max candidate threat objects to screen."),
    ] = 20,
    max_protected_targets: Annotated[
        int,
        Query(ge=1, le=50, description="Max protected satellites to screen."),
    ] = 5,
    max_ranked_results: Annotated[
        int,
        Query(ge=1, le=200, description="Max ranked threat events to return."),
    ] = 50,
    stale_data_policy: Annotated[
        str,
        Query(description="Stale data policy: 'flag' or 'exclude'."),
    ] = "flag",
    threshold_km: Annotated[float | None, Query(description="Alias for screening_threshold_km.")] = None,
    window_hours: Annotated[float | None, Query(description="Alias for screening_window_hours.")] = None,
    max_candidates: Annotated[int | None, Query(description="Alias for max_threat_candidates.")] = None,
    max_targets: Annotated[int | None, Query(description="Alias for max_protected_targets.")] = None,
    stale_policy: Annotated[str | None, Query(description="Alias for stale_data_policy.")] = None,
) -> ThreatScreeningResponse:
    """GET query-string adapter for threat screening."""
    effective_threshold = threshold_km if threshold_km is not None else screening_threshold_km
    effective_window = window_hours if window_hours is not None else screening_window_hours
    effective_candidates = max_candidates if max_candidates is not None else max_threat_candidates
    effective_targets = max_targets if max_targets is not None else max_protected_targets
    effective_policy = stale_policy if stale_policy is not None else stale_data_policy

    if effective_policy not in ("flag", "exclude"):
        raise HTTPException(
            status_code=422,
            detail="stale_data_policy must be 'flag' or 'exclude'.",
        )
    req = ThreatScreeningRequest(
        screening_threshold_km=effective_threshold,
        screening_window_hours=effective_window,
        max_threat_candidates=effective_candidates,
        max_protected_targets=effective_targets,
        max_ranked_results=max_ranked_results,
        stale_data_policy=effective_policy,
    )
    return _execute_threat_screening(req)


# ---------------------------------------------------------------------------
# Catalogue & Refresh Freshness Status (Layer 12)
# ---------------------------------------------------------------------------

@router.get(
    "/catalog/status",
    response_model=CatalogStatusResponse,
    tags=["catalog"],
)
def get_catalog_status() -> CatalogStatusResponse:
    """Retrieve current catalogue freshness and automated data refresh metadata.

    Read-only status endpoint. Does not trigger remote downloads or mutations.
    """
    refresh_meta = RefreshMetadata.load(_METADATA_PATH)
    catalog = _get_or_build_catalog()

    now = datetime.now(timezone.utc)
    total_objects = len(catalog)
    active_satellites = len(catalog.get_active_satellites())
    with_orbital = sum(1 for o in catalog if o.has_orbital_data)
    stale_count = sum(1 for o in catalog if o.is_stale)

    epochs = [o.epoch for o in catalog if o.epoch is not None]
    oldest_epoch_str = min(epochs).isoformat() if epochs else None
    newest_epoch_str = max(epochs).isoformat() if epochs else None
    max_epoch_age_days = (
        round(max((now - e).total_seconds() / 86400.0 for e in epochs), 2)
        if epochs
        else None
    )

    sources_map: dict[str, SourceFreshnessResponse] = {}
    if refresh_meta.sources:
        for name, src in refresh_meta.sources.items():
            sources_map[name] = SourceFreshnessResponse(
                source_name=src.source_name,
                url=src.url,
                dest_path=src.dest_path,
                retrieved_at=src.retrieved_at,
                success=src.success,
                error_message=src.error_message,
                bytes_downloaded=src.bytes_downloaded,
                total_records=src.total_records,
                valid_records=src.valid_records,
                rejected_records=src.rejected_records,
                oldest_epoch=src.oldest_epoch,
                newest_epoch=src.newest_epoch,
                max_epoch_age_days=src.max_epoch_age_days,
                stale_records_count=src.stale_records_count,
                classification_source=src.classification_source,
            )
    else:
        # Default baseline if refresh metadata file does not exist yet
        sources_map["active_satellites_gp"] = SourceFreshnessResponse(
            source_name="active_satellites_gp",
            url="https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=csv",
            dest_path=str(_GP_CSV),
            retrieved_at=None,
            success=True,
            bytes_downloaded=_GP_CSV.stat().st_size if _GP_CSV.exists() else 0,
            total_records=total_objects,
            valid_records=with_orbital,
            rejected_records=0,
            oldest_epoch=oldest_epoch_str,
            newest_epoch=newest_epoch_str,
            max_epoch_age_days=max_epoch_age_days,
            stale_records_count=stale_count,
            classification_source="source_group_hint",
        )

    warnings: list[str] = [
        "Data retrieval timestamp reflects file download time, NOT orbital element generation epoch."
    ]
    if max_epoch_age_days is not None and max_epoch_age_days > 14.0:
        warnings.append(
            f"Orbital elements have an epoch age of {max_epoch_age_days:.1f} days. "
            "Propagation accuracy degrades over time; predictions are advisory."
        )
    if refresh_meta.status == "failed":
        warnings.append(
            "Latest automated refresh attempt failed. Preserving last known valid catalogue snapshot."
        )

    data_notes = [
        "Catalogue currently contains active satellites from CelesTrak GP dataset.",
        "Classification is based on SATCAT metadata where available, or source group hints.",
    ]
    if not _SATCAT_CSV.exists():
        data_notes.append("SATCAT metadata file not present; classifications are based on source group hints.")

    regimes = {"LEO": 0, "MEO": 0, "GEO": 0, "Other": 0}
    classifications_map: dict[str, int] = {}
    for o in catalog:
        cls_val = o.classification.value
        classifications_map[cls_val] = classifications_map.get(cls_val, 0) + 1
        if o.orbital_record:
            try:
                mm = float(o.orbital_record.get("MEAN_MOTION", 0.0))
                if mm >= 11.25:
                    regimes["LEO"] += 1
                elif 1.05 <= mm < 11.25:
                    regimes["MEO"] += 1
                elif 0.95 <= mm < 1.05:
                    regimes["GEO"] += 1
                else:
                    regimes["Other"] += 1
            except (ValueError, TypeError):
                regimes["Other"] += 1

    return CatalogStatusResponse(
        last_refresh_attempt=refresh_meta.last_refresh_attempt,
        last_successful_refresh=refresh_meta.last_successful_refresh,
        refresh_status=refresh_meta.status,
        total_objects=total_objects,
        active_satellites=active_satellites,
        with_orbital_data=with_orbital,
        stale_objects=stale_count,
        oldest_epoch=oldest_epoch_str,
        newest_epoch=newest_epoch_str,
        max_epoch_age_days=max_epoch_age_days,
        sources=sources_map,
        warnings=warnings,
        data_source_notes=data_notes,
        disclaimer=(
            "Calculated threat scores and conjunction analyses are heuristic priority indices. "
            "They are NOT certified collision probabilities and must not be used for operational avoidance maneuvers."
        ),
        orbit_regimes=regimes,
        classifications=classifications_map,
    )

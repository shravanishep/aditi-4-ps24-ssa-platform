"""
ml.models.threat_prioritization — Layer 9 threat-prioritization engine.

This module identifies protected satellites, screens candidate threat objects
for close approaches using Layer 3 conjunction analysis, scores each event
using the Layer 9 risk-priority heuristic, and produces a ranked threat list.

Data-source design
------------------
- **Protected targets** are identified from the active-satellite GP dataset
  (``active_satellites_gp.csv``).  This file contains GP orbital elements for
  active catalogued satellites.
- **Threat candidates** are, by default, drawn from the *same* GP dataset.
  This means the system currently screens **active-vs-active** close
  approaches only.
- The GP dataset does **not** contain SATCAT metadata (OBJECT_TYPE,
  RCS_SIZE, COUNTRY_CODE, etc.).  It cannot be used to distinguish
  payloads from debris or rocket bodies.
- A separate GP-format file for debris, rocket bodies, and inactive
  objects can be configured via ``ThreatConfig.threat_gp_csv_path``.
  If that file is not present, this limitation is **explicitly reported**
  in the screening results metadata — it is never silently hidden.
- Raw datasets are never modified.

Layer 8 integration
-------------------
Anomaly scoring is applied **only** when:
  1. A fitted Layer 8 model exists at ``config.anomaly_model_path``.
  2. The threat object has a valid feature vector in the Layer 7 Parquet
     dataset for the relevant observation time.

If either condition is not met, the anomaly score is ``None`` and the
documented missing-data policy applies (zero contribution to risk score).
We do NOT fabricate TCA-time features or use unrelated historical rows as
though they represented the TCA state.

Computational limitations
-------------------------
Full pairwise screening is O(N²) in the number of objects.  For a
catalogue of 16,000 satellites, this requires ~128 million pair
evaluations, each involving SGP4 propagation over the screening window.
This is computationally infeasible for real-time operation on a single
machine.  The ``max_threat_candidates`` configuration parameter limits
the number of candidate objects screened per protected target.  Production
deployment would require spatial indexing, pre-filtering, or parallelism —
none of which is implemented here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backend.orbital.conjunction import find_closest_approach
from backend.orbital.gp_loader import load_gp_data, parse_epoch

from ml.models.threat_config import ThreatConfig
from ml.models.threat_scorer import classify_severity, compute_risk_score, explain_risk_score

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ThreatEvent — one screened close-approach event
# ---------------------------------------------------------------------------

@dataclass
class ThreatEvent:
    """A single close-approach event between a protected satellite and a
    candidate threat object.

    Attributes
    ----------
    protected_norad_id, protected_name:
        Identity of the protected (high-value) satellite.
    threat_norad_id, threat_name:
        Identity of the candidate threat object.
    time_of_closest_approach:
        UTC datetime of predicted closest approach.
    minimum_separation_km:
        Minimum predicted separation at TCA (km).
    relative_speed_km_s:
        Relative speed at TCA (km/s).
    hours_to_tca:
        Hours from the reference time to TCA.
    threat_anomaly_score:
        Layer 8 normalised anomaly score of the threat object.
        ``None`` if anomaly data is unavailable.
    threat_anomaly_severity:
        Layer 8 severity label (``"normal"``/``"warning"``/``"critical"``),
        or ``"unavailable"`` if no score.
    risk_score:
        Composite risk-priority index in [0.0, 1.0].
    risk_severity:
        ``"low"``/``"warning"``/``"critical"``.
    risk_explanation:
        Per-factor breakdown dictionary from ``explain_risk_score()``.
    screening_notes:
        Additional context (e.g. data-source limitations).
    """

    protected_norad_id: int
    protected_name: str
    threat_norad_id: int
    threat_name: str

    # Conjunction geometry (Layer 3)
    time_of_closest_approach: datetime
    minimum_separation_km: float
    relative_speed_km_s: float
    hours_to_tca: float

    # Layer 8 anomaly context
    threat_anomaly_score: float | None = None
    threat_anomaly_severity: str = "unavailable"

    # Computed risk
    risk_score: float = 0.0
    risk_severity: str = "low"
    risk_explanation: dict = field(default_factory=dict)

    # Metadata
    screening_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ScreeningResult — complete output of a threat-screening run
# ---------------------------------------------------------------------------

@dataclass
class ScreeningResult:
    """Complete output of a threat-screening run.

    Contains the ranked threat events, metadata about the screening
    process, and explicitly documented limitations.
    """

    events: list[ThreatEvent]
    protected_count: int
    candidates_screened: int
    pairs_evaluated: int
    events_within_threshold: int
    data_source_notes: list[str]
    config_summary: dict


# ---------------------------------------------------------------------------
# Protected target identification
# ---------------------------------------------------------------------------

def identify_protected_targets(
    gp_df: pd.DataFrame,
    config: ThreatConfig,
) -> list[int]:
    """Identify NORAD IDs of protected satellites.

    Parameters
    ----------
    gp_df:
        GP DataFrame loaded by ``gp_loader.load_gp_data()``.
    config:
        Validated ``ThreatConfig``.

    Returns
    -------
    list[int]
        Sorted list of valid protected NORAD IDs.

    Raises
    ------
    ValueError
        If any explicitly requested NORAD ID is missing from the GP dataset,
        or if no protected targets are identified.
    """
    available_ids = set(gp_df["NORAD_CAT_ID"].astype(int).unique())

    if config.protect_all_active:
        return sorted(available_ids)

    if not config.protected_norad_ids:
        raise ValueError(
            "No protected targets specified. Set 'protected_norad_ids' or "
            "'protect_all_active=True' in ThreatConfig."
        )

    missing = [nid for nid in config.protected_norad_ids if nid not in available_ids]
    if missing:
        raise ValueError(
            f"Protected NORAD IDs not found in GP dataset: {missing}. "
            f"Available NORAD IDs contain {len(available_ids)} objects."
        )

    return sorted(config.protected_norad_ids)


# ---------------------------------------------------------------------------
# Candidate threat object selection
# ---------------------------------------------------------------------------

def _select_threat_candidates(
    gp_df: pd.DataFrame,
    protected_ids: set[int],
    config: ThreatConfig,
) -> pd.DataFrame:
    """Select candidate threat objects from the GP dataset.

    If a separate threat GP dataset is configured and exists, load it.
    Otherwise fall back to the primary GP dataset, excluding protected
    targets from being screened against themselves.

    Parameters
    ----------
    gp_df:
        Primary GP DataFrame (active satellites).
    protected_ids:
        Set of protected NORAD IDs.
    config:
        Validated ``ThreatConfig``.

    Returns
    -------
    pd.DataFrame
        GP rows for candidate threat objects (up to max_threat_candidates).
    """
    if config.has_threat_data_source():
        threat_df = load_gp_data(config.get_threat_gp_csv_path())
        logger.info(
            "Loaded separate threat GP dataset with %d objects from %s",
            len(threat_df), config.threat_gp_csv_path,
        )
    else:
        # Fall back to active satellites — active-vs-active screening
        threat_df = gp_df

    # When screening active-vs-active with specific protected targets,
    # exclude those protected targets from the threat pool to avoid self-pairs.
    # When protect_all_active=True, all active satellites are candidates,
    # and self-pairs / duplicate pairs are handled during pair evaluation.
    if not config.has_threat_data_source() and not config.protect_all_active:
        threat_df = threat_df[
            ~threat_df["NORAD_CAT_ID"].astype(int).isin(protected_ids)
        ]

    # Limit to max_threat_candidates (sorted by NORAD ID for determinism)
    threat_df = threat_df.sort_values("NORAD_CAT_ID").head(config.max_threat_candidates)

    return threat_df


# ---------------------------------------------------------------------------
# Anomaly scoring
# ---------------------------------------------------------------------------

def _get_anomaly_score_for_object(
    norad_id: int,
    feature_df: pd.DataFrame | None,
    detector: Any | None,
) -> tuple[float | None, str]:
    """Attempt to retrieve a Layer 8 anomaly score for the threat object.

    This function uses the *most recent available* observation in the
    Layer 7 feature dataset for the given object.  It does NOT fabricate
    TCA-time features or use observations from unrelated satellites.

    Parameters
    ----------
    norad_id:
        NORAD catalogue ID of the threat object.
    feature_df:
        Layer 7 orbital features Parquet DataFrame, or None.
    detector:
        Fitted ``OrbitalAnomalyDetector``, or None.

    Returns
    -------
    tuple[float | None, str]
        (normalised_anomaly_score or None, severity label or "unavailable").
    """
    if detector is None or feature_df is None:
        return None, "unavailable"

    obj_rows = feature_df[feature_df["norad_cat_id"] == norad_id]
    if obj_rows.empty:
        return None, "unavailable"

    # Use the most recent observation (by t_offset_minutes) as the best
    # available representation of the object's current orbital behaviour.
    # This is NOT a TCA-time feature — it is the latest historical data.
    latest_row = obj_rows.sort_values("t_offset_minutes", ascending=False).head(1)

    try:
        scored = detector.predict(latest_row)
        score = scored["normalized_anomaly_score"].iloc[0]
        severity = scored["anomaly_severity"].iloc[0]
        if pd.isna(score):
            return None, "unavailable"
        return float(score), str(severity)
    except Exception:
        logger.warning(
            "Failed to score NORAD %d with Layer 8 detector; marking unavailable.",
            norad_id, exc_info=True,
        )
        return None, "unavailable"


# ---------------------------------------------------------------------------
# Conjunction screening
# ---------------------------------------------------------------------------

def screen_threats(
    gp_df: pd.DataFrame,
    protected_ids: list[int],
    config: ThreatConfig,
    detector: Any | None = None,
    feature_df: pd.DataFrame | None = None,
    reference_time: datetime | None = None,
) -> ScreeningResult:
    """Screen candidate objects for close approaches with protected targets.

    This function:
    1. Selects threat candidates from the GP dataset (or separate threat source).
    2. For each (protected, threat) pair, runs Layer 3 conjunction analysis.
    3. Filters for events within the screening threshold.
    4. Scores events using the Layer 9 risk-priority heuristic.
    5. Ranks events by descending risk score.

    Parameters
    ----------
    gp_df:
        Primary GP DataFrame.
    protected_ids:
        List of protected NORAD IDs.
    config:
        Validated ``ThreatConfig``.
    detector:
        Optional fitted ``OrbitalAnomalyDetector`` for anomaly scoring.
    feature_df:
        Optional Layer 7 Parquet DataFrame for anomaly feature lookup.
    reference_time:
        Reference UTC time for hours-to-TCA calculation.
        Defaults to ``datetime.now(timezone.utc)``.

    Returns
    -------
    ScreeningResult
        Ranked threat events and screening metadata.
    """
    config.validate()

    if reference_time is None:
        epochs = [
            parse_epoch(row["EPOCH"])
            for _, row in gp_df[gp_df["NORAD_CAT_ID"].isin(protected_ids)].iterrows()
        ]
        reference_time = max(epochs) if epochs else datetime.now(timezone.utc)

    # Common time window shared across all protected targets and candidates
    window_start = reference_time
    window_end = reference_time + timedelta(hours=config.screening_window_hours)

    protected_set = set(protected_ids)
    threat_df = _select_threat_candidates(gp_df, protected_set, config)

    # Build data-source limitation notes
    data_notes: list[str] = []
    if not config.has_threat_data_source():
        data_notes.append(
            "No separate debris/rocket-body GP dataset configured. "
            "Screening is limited to active-satellite-vs-active-satellite "
            "close approaches. To screen against debris and rocket bodies, "
            "provide a GP-format CSV via ThreatConfig.threat_gp_csv_path."
        )
    if "OBJECT_TYPE" not in gp_df.columns:
        data_notes.append(
            "GP dataset does not contain OBJECT_TYPE metadata (payload, "
            "rocket body, debris). Object type classification is unavailable."
        )

    events: list[ThreatEvent] = []
    pairs_evaluated = 0
    seen_pairs: set[tuple[int, int]] = set()

    for prot_id in protected_ids:
        prot_row = gp_df[gp_df["NORAD_CAT_ID"] == prot_id].iloc[0]
        prot_name = str(prot_row.get("OBJECT_NAME", "")).strip()

        for _, threat_row in threat_df.iterrows():
            threat_id = int(threat_row["NORAD_CAT_ID"])

            # Skip self-pair (should already be excluded, but defensive)
            if threat_id == prot_id:
                continue

            # Skip duplicate pair (order-independent)
            pair_key = (min(prot_id, threat_id), max(prot_id, threat_id))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            pairs_evaluated += 1

            try:
                result = find_closest_approach(
                    sat1_row=prot_row,
                    sat2_row=threat_row,
                    start_time=window_start,
                    end_time=window_end,
                    threshold_km=config.screening_threshold_km,
                    coarse_step_sec=config.coarse_step_sec,
                    fine_step_sec=config.fine_step_sec,
                )
            except (ValueError, Exception) as exc:
                logger.debug(
                    "Conjunction analysis failed for pair (%d, %d): %s",
                    prot_id, threat_id, exc,
                )
                continue

            if not result.is_candidate_close_approach:
                continue

            # Compute hours to TCA
            tca_dt = result.time_of_closest_approach
            hours_to_tca = max(0.0, (tca_dt - reference_time).total_seconds() / 3600.0)

            # Anomaly scoring (only if detector + features available)
            anom_score, anom_sev = _get_anomaly_score_for_object(
                threat_id, feature_df, detector,
            )

            # Build event notes
            event_notes: list[str] = []
            if anom_score is None:
                event_notes.append(
                    "Anomaly score unavailable for this object; "
                    "anomaly factor contributes zero to risk score."
                )

            # Compute risk score
            risk = compute_risk_score(
                min_separation_km=result.minimum_separation_km,
                relative_speed_km_s=result.relative_speed_km_s,
                hours_to_tca=hours_to_tca,
                anomaly_score=anom_score,
                config=config,
            )
            risk_sev = classify_severity(risk, config)
            explanation = explain_risk_score(
                min_separation_km=result.minimum_separation_km,
                relative_speed_km_s=result.relative_speed_km_s,
                hours_to_tca=hours_to_tca,
                anomaly_score=anom_score,
                config=config,
            )

            event = ThreatEvent(
                protected_norad_id=prot_id,
                protected_name=prot_name,
                threat_norad_id=threat_id,
                threat_name=str(threat_row.get("OBJECT_NAME", "")).strip(),
                time_of_closest_approach=tca_dt,
                minimum_separation_km=result.minimum_separation_km,
                relative_speed_km_s=result.relative_speed_km_s,
                hours_to_tca=hours_to_tca,
                threat_anomaly_score=anom_score,
                threat_anomaly_severity=anom_sev,
                risk_score=risk,
                risk_severity=risk_sev,
                risk_explanation=explanation,
                screening_notes=event_notes,
            )
            events.append(event)

    # Rank by risk score descending
    events.sort(key=lambda e: e.risk_score, reverse=True)
    ranked_events = events[: config.max_ranked_results]

    return ScreeningResult(
        events=ranked_events,
        protected_count=len(protected_ids),
        candidates_screened=len(threat_df),
        pairs_evaluated=pairs_evaluated,
        events_within_threshold=len(events),
        data_source_notes=data_notes,
        config_summary={
            "screening_threshold_km": config.screening_threshold_km,
            "screening_window_hours": config.screening_window_hours,
            "max_threat_candidates": config.max_threat_candidates,
            "weights": {
                "separation": config.weight_separation,
                "relative_velocity": config.weight_relative_velocity,
                "anomaly_score": config.weight_anomaly_score,
                "time_to_tca": config.weight_time_to_tca,
            },
            "anomaly_model_available": detector is not None,
            "threat_data_source": (
                config.threat_gp_csv_path
                if config.has_threat_data_source()
                else "active_satellites_gp.csv (active-only; no debris/RB data)"
            ),
            "disclaimer": config.disclaimer,
        },
    )

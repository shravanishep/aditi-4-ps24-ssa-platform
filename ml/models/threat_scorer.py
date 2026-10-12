"""
ml.models.threat_scorer — Risk-priority scoring for Layer 9 threat events.

This module computes a composite *heuristic risk-priority index* for each
close-approach event.  The score is a weighted linear combination of four
independently interpretable factors, each normalised to [0.0, 1.0].

**The risk-priority score is NOT a collision probability.**

Factor rationale
----------------
1. **Separation distance** (``f_sep``):
   Geometric screening indicator.  Smaller miss distance means the two
   objects pass closer in 3-D space, which is the primary geometric
   prerequisite for a collision.  Note that small miss distance alone does
   NOT imply high collision probability — that requires covariance data
   (which this system does not have).

2. **Relative velocity** (``f_vel``):
   Relates to potential encounter *consequences*, not probability.
   Higher relative speed at closest approach means greater kinetic energy
   in a potential collision, producing more debris.  This factor does NOT
   increase collision probability; head-on encounters have larger relative
   velocity but very short encounter duration.

3. **Time to TCA** (``f_tca``):
   Represents *urgency*.  Events with TCA sooner require faster response
   (manoeuvre planning, operator alerting).  A close approach days away
   allows more time for refined observations and decisions.

4. **Anomaly score** (``f_anom``):
   Supplementary *behavioural context* from Layer 8.  An elevated anomaly
   score suggests the threat object's recent orbital behaviour deviates
   from its own history (e.g. an unannounced manoeuvre or unexpected
   drag increase).  A high anomaly score does NOT by itself indicate a
   threat; it flags unusual behaviour worth investigating alongside
   conjunction geometry.  When anomaly data is unavailable, this factor
   contributes zero to the total score, and the missing-data state is
   explicitly marked.
"""

from __future__ import annotations

from typing import Any

from ml.models.threat_config import ThreatConfig


def compute_risk_score(
    min_separation_km: float,
    relative_speed_km_s: float,
    hours_to_tca: float,
    anomaly_score: float | None,
    config: ThreatConfig,
) -> float:
    """Compute a bounded risk-priority index in [0.0, 1.0].

    Parameters
    ----------
    min_separation_km:
        Minimum predicted separation at TCA (km).
    relative_speed_km_s:
        Relative speed between the two objects at TCA (km/s).
    hours_to_tca:
        Hours from the current reference time to TCA.
        Must be non-negative.
    anomaly_score:
        Layer 8 normalised anomaly score in [0, 1] for the threat object.
        ``None`` if anomaly data is unavailable.
    config:
        Validated ThreatConfig instance.

    Returns
    -------
    float
        Composite risk-priority index in [0.0, 1.0].
    """
    f_sep = _normalise_separation(min_separation_km, config.ref_max_separation_km)
    f_vel = _normalise_velocity(relative_speed_km_s, config.ref_max_rel_velocity_km_s)
    f_tca = _normalise_time_to_tca(hours_to_tca, config.ref_max_time_to_tca_hours)
    f_anom = _normalise_anomaly(anomaly_score)

    score = (
        config.weight_separation * f_sep
        + config.weight_relative_velocity * f_vel
        + config.weight_time_to_tca * f_tca
        + config.weight_anomaly_score * f_anom
    )
    return max(0.0, min(1.0, score))


def explain_risk_score(
    min_separation_km: float,
    relative_speed_km_s: float,
    hours_to_tca: float,
    anomaly_score: float | None,
    config: ThreatConfig,
) -> dict[str, Any]:
    """Return a fully explainable breakdown of the risk-priority score.

    Every factor is documented with its raw value, normalised value,
    weight, and weighted contribution.  The sum of contributions equals
    the total ``risk_score`` within floating-point tolerance.

    Returns
    -------
    dict
        Keys: ``risk_score``, ``risk_severity``, ``factors``,
        ``anomaly_data_available``, ``disclaimer``.
    """
    f_sep = _normalise_separation(min_separation_km, config.ref_max_separation_km)
    f_vel = _normalise_velocity(relative_speed_km_s, config.ref_max_rel_velocity_km_s)
    f_tca = _normalise_time_to_tca(hours_to_tca, config.ref_max_time_to_tca_hours)
    f_anom = _normalise_anomaly(anomaly_score)

    c_sep = config.weight_separation * f_sep
    c_vel = config.weight_relative_velocity * f_vel
    c_tca = config.weight_time_to_tca * f_tca
    c_anom = config.weight_anomaly_score * f_anom

    risk_score = max(0.0, min(1.0, c_sep + c_vel + c_tca + c_anom))
    risk_severity = classify_severity(risk_score, config)

    return {
        "risk_score": risk_score,
        "risk_severity": risk_severity,
        "anomaly_data_available": anomaly_score is not None,
        "factors": {
            "separation": {
                "description": "Geometric proximity indicator — closer miss distance raises priority.",
                "raw_value_km": min_separation_km,
                "normalised": round(f_sep, 6),
                "weight": config.weight_separation,
                "contribution": round(c_sep, 6),
            },
            "relative_velocity": {
                "description": (
                    "Encounter consequence indicator — higher relative speed "
                    "implies greater kinetic energy in a potential collision."
                ),
                "raw_value_km_s": relative_speed_km_s,
                "normalised": round(f_vel, 6),
                "weight": config.weight_relative_velocity,
                "contribution": round(c_vel, 6),
            },
            "time_to_tca": {
                "description": "Urgency indicator — sooner TCA means less time to respond.",
                "raw_value_hours": hours_to_tca,
                "normalised": round(f_tca, 6),
                "weight": config.weight_time_to_tca,
                "contribution": round(c_tca, 6),
            },
            "anomaly_score": {
                "description": (
                    "Supplementary behavioural context from Layer 8. "
                    "High score indicates unusual orbital behaviour, "
                    "NOT a direct threat indicator."
                ),
                "raw_value": anomaly_score if anomaly_score is not None else "unavailable",
                "normalised": round(f_anom, 6),
                "weight": config.weight_anomaly_score,
                "contribution": round(c_anom, 6),
            },
        },
        "disclaimer": config.disclaimer,
    }


def classify_severity(risk_score: float, config: ThreatConfig) -> str:
    """Map a risk-priority score to a severity label.

    Parameters
    ----------
    risk_score:
        Value in [0.0, 1.0].
    config:
        Validated ThreatConfig with severity thresholds.

    Returns
    -------
    str
        ``"critical"``, ``"warning"``, or ``"low"``.
    """
    if risk_score >= config.critical_risk_threshold:
        return "critical"
    if risk_score >= config.warning_risk_threshold:
        return "warning"
    return "low"


# ---------------------------------------------------------------------------
# Factor normalisation functions
# ---------------------------------------------------------------------------
# Each function maps a physical quantity into [0.0, 1.0] such that higher
# values correspond to higher priority.


def _normalise_separation(min_sep_km: float, ref_max_km: float) -> float:
    """Inverse normalisation: closer → higher factor value.

    f = 1.0 − clamp(min_sep / ref_max, 0, 1)
    """
    if ref_max_km <= 0:
        return 0.0
    ratio = max(0.0, min(min_sep_km / ref_max_km, 1.0))
    return 1.0 - ratio


def _normalise_velocity(rel_speed_km_s: float, ref_max_km_s: float) -> float:
    """Direct normalisation: faster → higher factor value.

    f = clamp(rel_speed / ref_max, 0, 1)
    """
    if ref_max_km_s <= 0:
        return 0.0
    return max(0.0, min(rel_speed_km_s / ref_max_km_s, 1.0))


def _normalise_time_to_tca(hours: float, ref_max_hours: float) -> float:
    """Inverse normalisation: sooner → higher factor value.

    f = 1.0 − clamp(hours / ref_max, 0, 1)
    """
    if ref_max_hours <= 0:
        return 0.0
    ratio = max(0.0, min(hours / ref_max_hours, 1.0))
    return 1.0 - ratio


def _normalise_anomaly(anomaly_score: float | None) -> float:
    """Pass-through for available scores; 0.0 when unavailable.

    Layer 8's ``normalized_anomaly_score`` is already in [0, 1].
    When the anomaly model is not fitted, the detector is unavailable,
    or valid feature inputs cannot be generated for the threat object
    at TCA, ``anomaly_score`` is ``None`` and this factor contributes
    zero.  This is the documented *neutral/missing-data policy*: absence
    of anomaly data does not inflate or deflate the risk score.
    """
    if anomaly_score is None:
        return 0.0
    return max(0.0, min(float(anomaly_score), 1.0))

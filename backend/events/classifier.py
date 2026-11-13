"""
Event Intelligence — Maneuver Classifier.

IMPORTANT DISCLAIMER:
    All classifications produced by EventClassifier are RULE-BASED HEURISTICS.
    They are NOT trained machine-learning predictions, NOT statistically calibrated,
    and NOT certified for operational space-traffic management use.
    Treat all outputs as indicative only.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Classification labels (string constants used as return values)
# ---------------------------------------------------------------------------
ORBIT_RAISE = "ORBIT_RAISE"
ORBIT_DECAY = "ORBIT_DECAY"
STATION_KEEPING = "STATION_KEEPING"
UNKNOWN = "UNKNOWN"

_CONFIDENCE_NOTE = "Rule-based heuristic; not statistically calibrated."


class EventClassifier:
    """
    Rule-based maneuver classifier using orbital feature trends.

    Uses the following extracted features (must be present in ``features`` dict):
    - ``d_altitude_km``  : change in altitude over the observation window (km)
    - ``d_speed_km_s``   : change in speed over the observation window (km/s)
    - ``specific_energy``: (optional) specific orbital energy – used for context

    Rules are applied in priority order; the first matching rule wins.
    All rules are deterministic thresholds – there is no probabilistic
    model behind this classifier.
    """

    # ------------------------------------------------------------------
    # Threshold constants (documented so reviewers can audit them)
    # ------------------------------------------------------------------
    _RAISE_D_ALT_KM = 2.0       # Minimum altitude increase for ORBIT_RAISE (km)
    _RAISE_D_SPD_KM_S = 0.01    # Minimum speed increase for ORBIT_RAISE (km/s)
    _RAISE_ANOMALY_MIN = 0.4    # Anomaly score lower bound for ORBIT_RAISE

    _DECAY_D_ALT_KM = -1.0      # Maximum (most-negative) altitude change for ORBIT_DECAY (km)
    _DECAY_ANOMALY_MAX = 0.3    # Anomaly score upper bound for ORBIT_DECAY

    _SK_ANOMALY_MIN = 0.3       # Minimum anomaly score for STATION_KEEPING
    _SK_D_ALT_KM_ABS = 2.0     # Maximum |altitude change| for STATION_KEEPING (km)
    _SK_D_SPD_KM_S = 0.005     # Minimum speed change for STATION_KEEPING (km/s)

    def classify(self, features: dict, anomaly_score: float) -> tuple[str, str]:
        """
        Classify a potential maneuver from orbital feature deltas.

        Parameters
        ----------
        features : dict
            Must contain at minimum ``d_altitude_km`` and ``d_speed_km_s``.
            May optionally contain ``specific_energy`` for context.
        anomaly_score : float
            Anomaly score in [0, 1] produced by the IsolationForest wrapper.

        Returns
        -------
        (classification, explanation) : tuple[str, str]
            classification — one of ORBIT_RAISE, ORBIT_DECAY, STATION_KEEPING, UNKNOWN
            explanation    — human-readable string with an appended confidence note.

        Notes
        -----
        Rules are heuristic thresholds derived from domain knowledge, NOT trained
        from labelled data.  Confidence note: "Rule-based heuristic; not
        statistically calibrated."
        """
        d_alt = float(features.get("d_altitude_km", 0.0))
        d_spd = float(features.get("d_speed_km_s", 0.0))

        # --- Rule 1: ORBIT_RAISE ----------------------------------------
        if (
            d_alt > self._RAISE_D_ALT_KM
            and d_spd > self._RAISE_D_SPD_KM_S
            and anomaly_score > self._RAISE_ANOMALY_MIN
        ):
            return (
                ORBIT_RAISE,
                (
                    "Altitude increasing with speed increase; consistent with "
                    "orbit-raising maneuver. " + _CONFIDENCE_NOTE
                ),
            )

        # --- Rule 2: ORBIT_DECAY ----------------------------------------
        if d_alt < self._DECAY_D_ALT_KM and anomaly_score < self._DECAY_ANOMALY_MAX:
            return (
                ORBIT_DECAY,
                (
                    "Gradual altitude decrease; consistent with atmospheric "
                    "drag-induced decay. " + _CONFIDENCE_NOTE
                ),
            )

        # --- Rule 3: STATION_KEEPING ------------------------------------
        if (
            anomaly_score > self._SK_ANOMALY_MIN
            and abs(d_alt) < self._SK_D_ALT_KM_ABS
            and d_spd > self._SK_D_SPD_KM_S
        ):
            return (
                STATION_KEEPING,
                (
                    "Small velocity change with minimal altitude drift; consistent "
                    "with station-keeping. " + _CONFIDENCE_NOTE
                ),
            )

        # --- Fallback: UNKNOWN ------------------------------------------
        return (
            UNKNOWN,
            "Insufficient evidence to classify maneuver type. " + _CONFIDENCE_NOTE,
        )

"""
ml.models.threat_config — Configuration for Layer 9 threat prioritization.

All tuneable parameters for protected-target identification, conjunction
screening, risk scoring, and ranking are centralised here.

Design notes
------------
- All weights, thresholds, and reference values are explicit.
- ``validate()`` enforces consistency (weights sum to 1.0, bounds positive,
  thresholds ordered) so that downstream scoring logic can assume valid config.
- The risk-priority index is a heuristic ranking tool, NOT a collision
  probability.  This constraint is encoded in the config-level disclaimer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ThreatConfig:
    """Configuration dataclass for the Layer 9 threat prioritization system.

    Attributes
    ----------
    gp_csv_path:
        Path to the GP CSV file containing orbital elements for the objects
        to consider.  The current dataset (``active_satellites_gp.csv``)
        contains *active* satellites only.  Debris, rocket bodies, and
        inactive objects require a separate GP-format source; if unavailable,
        the screening is limited to active-vs-active close approaches and
        this limitation is reported.
    protected_norad_ids:
        Explicit list of NORAD IDs to treat as protected targets (high-value
        assets).  If empty *and* ``protect_all_active`` is False, no
        screening is performed.
    protect_all_active:
        If True, every object in the GP dataset is treated as a potential
        protected target.
    threat_gp_csv_path:
        Optional path to a *separate* GP CSV containing potential threat
        objects (debris, rocket bodies, inactive satellites).  If ``None``,
        threat candidates are drawn from the same GP dataset as protected
        targets (active-vs-active only), and the data-source limitation is
        flagged in output metadata.
    screening_threshold_km:
        Close-approach distance threshold for Layer 3 conjunction analysis.
    screening_window_hours:
        Forward-looking propagation window from each object's GP epoch.
    coarse_step_sec:
        Layer 3 coarse search step size (seconds).
    fine_step_sec:
        Layer 3 fine search step size (seconds).
    max_threat_candidates:
        Maximum number of candidate objects to screen against each protected
        target.  Limits computational cost for large catalogues.
    weight_separation:
        Scoring weight for separation distance factor.
    weight_relative_velocity:
        Scoring weight for relative velocity factor.
    weight_anomaly_score:
        Scoring weight for Layer 8 anomaly score factor.
    weight_time_to_tca:
        Scoring weight for time-to-TCA urgency factor.
    ref_max_separation_km:
        Reference maximum for separation factor normalisation.
    ref_max_rel_velocity_km_s:
        Reference maximum for relative velocity normalisation.
    ref_max_time_to_tca_hours:
        Reference maximum for time-to-TCA normalisation.
    critical_risk_threshold:
        Score at or above which risk severity is "critical".
    warning_risk_threshold:
        Score at or above which risk severity is "warning".
    max_ranked_results:
        Maximum number of events in the ranked output.
    anomaly_model_path:
        Path to fitted Layer 8 model joblib.  Set to ``None`` to skip
        anomaly scoring entirely.
    """

    # --- Data sources ---
    gp_csv_path: str = "data/raw/active_satellites_gp.csv"
    threat_gp_csv_path: str | None = None  # No debris/RB data available yet

    # --- Protected target selection ---
    protected_norad_ids: list[int] = field(default_factory=list)
    protect_all_active: bool = False

    # --- Conjunction screening ---
    screening_threshold_km: float = 50.0
    screening_window_hours: float = 72.0
    coarse_step_sec: float = 60.0
    fine_step_sec: float = 1.0
    max_threat_candidates: int = 200

    # --- Risk score weights ---
    # Must sum to 1.0 (enforced by validate()).
    # Rationale for each factor is documented in threat_scorer.py.
    weight_separation: float = 0.40
    weight_relative_velocity: float = 0.25
    weight_anomaly_score: float = 0.20
    weight_time_to_tca: float = 0.15

    # --- Normalisation reference values ---
    ref_max_separation_km: float = 50.0
    ref_max_rel_velocity_km_s: float = 15.0
    ref_max_time_to_tca_hours: float = 72.0

    # --- Severity classification ---
    critical_risk_threshold: float = 0.80
    warning_risk_threshold: float = 0.50

    # --- Output ---
    max_ranked_results: int = 50

    # --- Layer 8 integration ---
    anomaly_model_path: str | None = "models/isolation_forest.joblib"

    # --- Disclaimer (immutable) ---
    disclaimer: str = (
        "Risk scores are heuristic priority indices based on SGP4-propagated "
        "geometry and unsupervised anomaly scores. They are NOT collision "
        "probabilities and must not be used for operational collision-avoidance "
        "decisions."
    )

    def validate(self) -> None:
        """Validate configuration consistency.

        Raises
        ------
        ValueError
            If any constraint is violated.
        """
        # Weight constraints
        weights = [
            self.weight_separation,
            self.weight_relative_velocity,
            self.weight_anomaly_score,
            self.weight_time_to_tca,
        ]
        for i, w in enumerate(weights):
            if w < 0.0:
                raise ValueError(f"Scoring weight at index {i} is negative: {w}")
        weight_sum = sum(weights)
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(
                f"Scoring weights must sum to 1.0; got {weight_sum:.6f}. "
                f"Weights: {weights}"
            )

        # Positive reference values
        if self.ref_max_separation_km <= 0:
            raise ValueError("ref_max_separation_km must be positive.")
        if self.ref_max_rel_velocity_km_s <= 0:
            raise ValueError("ref_max_rel_velocity_km_s must be positive.")
        if self.ref_max_time_to_tca_hours <= 0:
            raise ValueError("ref_max_time_to_tca_hours must be positive.")

        # Threshold ordering
        if not (0.0 <= self.warning_risk_threshold <= self.critical_risk_threshold <= 1.0):
            raise ValueError(
                "Severity thresholds must satisfy "
                "0 <= warning_risk_threshold <= critical_risk_threshold <= 1."
            )

        # Screening parameters
        if self.screening_threshold_km <= 0:
            raise ValueError("screening_threshold_km must be positive.")
        if self.screening_window_hours <= 0:
            raise ValueError("screening_window_hours must be positive.")
        if self.coarse_step_sec <= 0:
            raise ValueError("coarse_step_sec must be positive.")
        if self.fine_step_sec <= 0:
            raise ValueError("fine_step_sec must be positive.")
        if self.fine_step_sec > self.coarse_step_sec:
            raise ValueError("fine_step_sec must not exceed coarse_step_sec.")
        if self.max_threat_candidates <= 0:
            raise ValueError("max_threat_candidates must be positive.")
        if self.max_ranked_results <= 0:
            raise ValueError("max_ranked_results must be positive.")

    def get_gp_csv_path(self) -> Path:
        return Path(self.gp_csv_path)

    def get_threat_gp_csv_path(self) -> Path | None:
        if self.threat_gp_csv_path is None:
            return None
        return Path(self.threat_gp_csv_path)

    def has_threat_data_source(self) -> bool:
        """Return True if a separate threat-object GP dataset is configured and exists."""
        p = self.get_threat_gp_csv_path()
        return p is not None and p.exists()

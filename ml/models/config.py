"""
ml.models.config — Configuration dataclasses for Layer 8 anomaly detection.

Defines the feature list, model parameters, and path defaults for training
and evaluating the Isolation Forest anomaly detector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Feature selection for behavioural anomaly detection
# ---------------------------------------------------------------------------
# The primary anomaly detector uses ONLY dynamic state magnitudes/kinematics
# and temporal difference features (12 features in total).
#
# Static GP orbital elements (semi_major_axis_km, inclination_deg, etc.)
# are intentionally excluded from model input so that baseline orbital regime
# differences (e.g. LEO vs MEO vs GEO) are not flagged as "behavioural anomalies".
# ---------------------------------------------------------------------------

BEHAVIOURAL_FEATURES: list[str] = [
    # Dynamic state magnitudes & kinematics (7)
    "orbital_radius_km",
    "altitude_km",
    "speed_km_s",
    "radial_vel_km_s",
    "cross_track_vel_km_s",
    "angular_momentum_km2_s",
    "specific_energy_km2_s2",
    # Temporal difference features (5)
    "d_altitude_km",
    "d_orbital_radius_km",
    "d_speed_km_s",
    "d_specific_energy_km2_s2",
    "d_angular_momentum_km2_s",
]


@dataclass
class AnomalyModelConfig:
    """Configuration dataclass for the Isolation Forest anomaly detector."""

    # Data paths
    parquet_path: str = "data/processed/orbital_features.parquet"
    model_output_path: str = "models/isolation_forest.joblib"
    metadata_output_path: str = "models/isolation_forest_metadata.json"

    # Selected model features
    features: list[str] = field(default_factory=lambda: list(BEHAVIOURAL_FEATURES))

    # Isolation Forest hyperparameters
    n_estimators: int = 200
    max_samples: str | int = "auto"
    contamination: float = 0.02  # Initial calibration estimate for decision boundary
    random_state: int = 42
    bootstrap: bool = False

    # Score normalization & severity thresholds
    decision_threshold: float = 0.65  # Explicit threshold on normalized_anomaly_score calibrated on validation split
    warning_threshold: float = 0.65
    critical_threshold: float = 0.85

    def get_parquet_path(self) -> Path:
        return Path(self.parquet_path)

    def get_model_path(self) -> Path:
        return Path(self.model_output_path)

    def get_metadata_path(self) -> Path:
        return Path(self.metadata_output_path)

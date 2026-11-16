"""
ml.models.temporal_detector — Temporal-only Isolation Forest anomaly detector.

Implements Approach B (Phase 6):
Uses ONLY the 5 temporal difference features:
  - d_altitude_km
  - d_speed_km_s
  - d_specific_energy_km2_s2
  - d_angular_momentum_km2_s
  - d_orbital_radius_km

The objective is to eliminate dependence on absolute orbital speed and altitude
(which differ by regime) while detecting sudden, uncharacteristic dynamical shifts.

Design rules
------------
1. Strictly limited to temporal difference features (no absolute state vectors or GP elements).
2. Uses backward finite differences computed within each satellite's chronological sequence.
3. Imputes initial observation NaNs with 0.0 (baseline steady-state assumption).
4. Persists to 'models/isolation_forest_v2_temporal.joblib'.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd

from ml.models.anomaly_detector import OrbitalAnomalyDetector
from ml.models.config import AnomalyModelConfig, TEMPORAL_FEATURES


class TemporalAnomalyDetector:
    """Isolation Forest anomaly detector using strictly temporal difference features."""

    def __init__(
        self,
        features: Sequence[str] | None = None,
        n_estimators: int = 200,
        contamination: float = 0.02,
        random_state: int = 42,
        decision_threshold: float = 0.65,
        warning_threshold: float = 0.65,
        critical_threshold: float = 0.85,
    ) -> None:
        self.features: list[str] = list(features or TEMPORAL_FEATURES)

        # Enforce strict temporal-only feature constraint
        for f in self.features:
            if not f.startswith("d_"):
                raise ValueError(
                    f"TemporalAnomalyDetector requires temporal difference features starting with 'd_', got: {f}"
                )

        self.config = AnomalyModelConfig(
            features=list(self.features),
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=random_state,
            decision_threshold=decision_threshold,
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
            model_output_path="models/isolation_forest_v2_temporal.joblib",
            metadata_output_path="models/isolation_forest_v2_temporal_metadata.json",
        )
        self.detector = OrbitalAnomalyDetector(config=self.config)

    @property
    def is_fitted(self) -> bool:
        return self.detector.is_fitted

    @property
    def raw_score_mean(self) -> float:
        return self.detector.raw_score_mean

    @property
    def raw_score_std(self) -> float:
        return self.detector.raw_score_std

    def fit(self, df: pd.DataFrame) -> TemporalAnomalyDetector:
        """Fit the detector on training DataFrame using only temporal features."""
        self.detector.fit(df)
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict anomaly metrics using temporal features only."""
        return self.detector.predict(df)

    def save(self, file_path: str = "models/isolation_forest_v2_temporal.joblib") -> Path:
        """Serialize detector to joblib file."""
        return self.detector.save(file_path)

    @classmethod
    def load(cls, file_path: str = "models/isolation_forest_v2_temporal.joblib") -> TemporalAnomalyDetector:
        """Load fitted detector from joblib file."""
        instance = cls()
        instance.detector = OrbitalAnomalyDetector.load(file_path)
        instance.config = instance.detector.config
        instance.features = instance.detector.features
        return instance

"""
ml.models.hybrid_detector — Hybrid Regime-Temporal Anomaly Detector.

Combines:
1. RegimeSpecificAnomalyDetector: Captures steady-state kinematic envelope per regime
   (altitude, speed, specific energy, angular momentum) and detects sustained orbital degradation.
2. TemporalAnomalyDetector: Captures sudden differential shocks (velocity impulses, delta-v maneuvers)
   across short time baselines.

Score Fusion:
Computes:
    s_regime   = normalized anomaly score from regime-specific detector in [0.0, 1.0]
    s_temporal = normalized anomaly score from temporal detector in [0.0, 1.0]
    s_hybrid   = max(s_regime, s_temporal) or calibrated probabilistic disjunction:
                 1.0 - (1.0 - s_regime) * (1.0 - s_temporal)

This eliminates the blind spot of temporal-only models (which miss sustained orbit drops)
while retaining sensitivity to transient impulsive maneuvers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd

from ml.models.regime_detector import RegimeSpecificAnomalyDetector
from ml.models.temporal_detector import TemporalAnomalyDetector


class HybridAnomalyDetector:
    """Ensemble detector fusing regime-specific kinematics with temporal dynamics."""

    def __init__(
        self,
        regime_detector: RegimeSpecificAnomalyDetector | None = None,
        temporal_detector: TemporalAnomalyDetector | None = None,
        fusion_method: str = "max",  # 'max', 'soft_or', or 'weighted'
        alpha_regime: float = 0.6,
        decision_threshold: float = 0.65,
        warning_threshold: float = 0.65,
        critical_threshold: float = 0.85,
    ) -> None:
        self.regime_detector = regime_detector or RegimeSpecificAnomalyDetector()
        self.temporal_detector = temporal_detector or TemporalAnomalyDetector()
        self.fusion_method = fusion_method
        self.alpha = alpha_regime
        self.decision_threshold = decision_threshold
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.is_fitted: bool = False

    def fit(self, df: pd.DataFrame) -> HybridAnomalyDetector:
        """Fit both constituent detectors on the training dataset."""
        self.regime_detector.fit(df)
        self.temporal_detector.fit(df)
        self.is_fitted = True
        return self

    def _fuse_scores(self, s_regime: np.ndarray, s_temporal: np.ndarray) -> np.ndarray:
        """Fuse normalized scores from both detectors into a single hybrid score."""
        s_r = np.clip(s_regime, 0.0, 1.0)
        s_t = np.clip(s_temporal, 0.0, 1.0)

        if self.fusion_method == "max":
            fused = np.maximum(s_r, s_t)
        elif self.fusion_method == "soft_or":
            fused = 1.0 - (1.0 - s_r) * (1.0 - s_t)
        elif self.fusion_method == "weighted":
            fused = self.alpha * s_r + (1.0 - self.alpha) * s_t
        else:
            raise ValueError(f"Unknown fusion method: {self.fusion_method}")

        return np.clip(fused, 0.0, 1.0)

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict anomaly metrics by fusing regime and temporal detection streams."""
        if not self.is_fitted:
            raise RuntimeError("HybridAnomalyDetector is not fitted yet.")

        # Compute predictions from both streams
        pred_regime = self.regime_detector.predict(df)
        pred_temporal = self.temporal_detector.predict(df)

        result_df = df.copy()

        s_r = pred_regime["normalized_anomaly_score"].fillna(0.0).to_numpy()
        s_t = pred_temporal["normalized_anomaly_score"].fillna(0.0).to_numpy()

        s_hybrid = self._fuse_scores(s_r, s_t)
        is_anomaly = s_hybrid >= self.decision_threshold

        severities = []
        for s in s_hybrid:
            if s >= self.critical_threshold:
                severities.append("critical")
            elif s >= self.warning_threshold:
                severities.append("warning")
            else:
                severities.append("normal")

        result_df["decision_score_raw"] = pred_regime["decision_score_raw"]
        result_df["normalized_anomaly_score"] = s_hybrid.astype("float32")
        result_df["regime_score"] = s_r.astype("float32")
        result_df["temporal_score"] = s_t.astype("float32")
        result_df["is_anomaly"] = is_anomaly
        result_df["anomaly_severity"] = severities
        result_df["regime_model_used"] = pred_regime.get("regime_model_used", "hybrid")

        return result_df

    def save(
        self,
        base_dir: str = "models",
        prefix: str = "isolation_forest_v3_hybrid",
    ) -> dict[str, Path]:
        """Save both sub-models and hybrid bundle."""
        if not self.is_fitted:
            raise RuntimeError("Cannot save unfitted detector.")

        dir_path = Path(base_dir)
        dir_path.mkdir(parents=True, exist_ok=True)

        reg_prefix = str(dir_path / f"{prefix}_regime")
        saved_reg_paths = self.regime_detector.save(reg_prefix)

        temp_path = dir_path / f"{prefix}_temporal.joblib"
        self.temporal_detector.save(str(temp_path))

        meta_path = dir_path / f"{prefix}_manifest.json"
        manifest = {
            "fusion_method": self.fusion_method,
            "alpha": self.alpha,
            "decision_threshold": self.decision_threshold,
            "regime_models": {k: str(p) for k, p in saved_reg_paths.items()},
            "temporal_model": str(temp_path),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return {"manifest": meta_path, "temporal": temp_path, **saved_reg_paths}

    @classmethod
    def load(
        cls,
        manifest_path: str = "models/isolation_forest_v3_hybrid_manifest.json",
    ) -> HybridAnomalyDetector:
        """Load hybrid detector from manifest."""
        path = Path(manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        regime_prefix = str(Path(manifest["regime_models"]["LEO"]).parent / "isolation_forest_v3_hybrid_regime")
        reg_detector = RegimeSpecificAnomalyDetector.load(regime_prefix)
        temp_detector = TemporalAnomalyDetector.load(manifest["temporal_model"])

        instance = cls(
            regime_detector=reg_detector,
            temporal_detector=temp_detector,
            fusion_method=manifest.get("fusion_method", "max"),
            alpha_regime=manifest.get("alpha", 0.6),
            decision_threshold=manifest.get("decision_threshold", 0.65),
        )
        instance.is_fitted = True
        return instance

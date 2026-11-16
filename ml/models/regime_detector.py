"""
ml.models.regime_detector — Regime-specific Isolation Forest anomaly detector.

Implements Approach A (Phase 6):
Trains independent Isolation Forest models for each orbital regime (LEO, MEO, GEO, HEO)
to eliminate regime-mixing bias where higher-altitude regimes (e.g. MEO, GEO, HEO) are
misclassified as anomalous due to natural orbital speed and altitude differences from LEO.

Design rules
------------
1. Strict separation: each regime model is fitted ONLY on training observations of that regime.
2. No silent fallback: if a satellite belongs to a regime without a trained model, an explicit
   RegimeModelNotFoundError is raised. It NEVER silently routes to a different regime.
3. Safe sample checking: requires a configurable minimum sample count and satellite count.
4. Independent persistence: each regime model is saved as a separate joblib artifact,
   enabling modular deployment and independent retraining.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd

from ml.models.anomaly_detector import OrbitalAnomalyDetector
from ml.models.config import BEHAVIOURAL_FEATURES, AnomalyModelConfig
from ml.pipeline.regime_sampler import classify_regime


class RegimeModelNotFoundError(KeyError):
    """Raised when prediction is requested for an orbital regime with no trained model."""


class InsufficientRegimeDataError(ValueError):
    """Raised when a regime does not meet minimum sample or satellite requirements."""


SUPPORTED_REGIMES: tuple[str, ...] = ("LEO", "MEO", "GEO", "HEO")


class RegimeSpecificAnomalyDetector:
    """Ensemble of regime-specific Isolation Forest detectors."""

    def __init__(
        self,
        features: Sequence[str] | None = None,
        min_samples_per_regime: int = 50,
        min_satellites_per_regime: int = 2,
        n_estimators: int = 200,
        contamination: float = 0.02,
        random_state: int = 42,
        decision_threshold: float = 0.65,
        warning_threshold: float = 0.65,
        critical_threshold: float = 0.85,
    ) -> None:
        self.features: list[str] = list(features or BEHAVIOURAL_FEATURES)
        self.min_samples: int = min_samples_per_regime
        self.min_satellites: int = min_satellites_per_regime
        self.n_estimators: int = n_estimators
        self.contamination: float = contamination
        self.random_state: int = random_state
        self.decision_threshold: float = decision_threshold
        self.warning_threshold: float = warning_threshold
        self.critical_threshold: float = critical_threshold

        self.regime_models: dict[str, OrbitalAnomalyDetector] = {}
        self.regime_stats: dict[str, dict[str, Any]] = {}
        self.is_fitted: bool = False

    def _ensure_regime_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure 'regime' column exists, deriving from mean motion if necessary."""
        if "regime" in df.columns:
            return df

        if "mean_motion_rev_day" in df.columns:
            out = df.copy()
            out["regime"] = out["mean_motion_rev_day"].apply(classify_regime)
            return out
        elif "MEAN_MOTION" in df.columns:
            out = df.copy()
            out["regime"] = out["MEAN_MOTION"].apply(classify_regime)
            return out
        else:
            raise ValueError(
                "Input DataFrame must contain 'regime', 'mean_motion_rev_day', or 'MEAN_MOTION'."
            )

    def fit(self, df: pd.DataFrame) -> RegimeSpecificAnomalyDetector:
        """Fit independent Isolation Forest models for each available regime.

        Parameters
        ----------
        df : pd.DataFrame
            Training DataFrame containing valid observations (sgp4_error == 0)
            and a 'regime' or 'mean_motion_rev_day' column.
        """
        data = self._ensure_regime_column(df)

        # Filter out SGP4 errors if present
        if "sgp4_error" in data.columns:
            valid_df = data[data["sgp4_error"] == 0]
        else:
            valid_df = data

        self.regime_models.clear()
        self.regime_stats.clear()

        for regime in SUPPORTED_REGIMES:
            reg_sub = valid_df[valid_df["regime"] == regime]
            n_rows = len(reg_sub)
            n_sats = reg_sub["norad_cat_id"].nunique() if "norad_cat_id" in reg_sub.columns else 1

            if n_rows < self.min_samples or n_sats < self.min_satellites:
                self.regime_stats[regime] = {
                    "status": "insufficient_data",
                    "rows": n_rows,
                    "satellites": n_sats,
                    "min_samples_required": self.min_samples,
                    "min_satellites_required": self.min_satellites,
                }
                continue

            # Configure and fit regime-specific detector
            reg_cfg = AnomalyModelConfig(
                features=list(self.features),
                n_estimators=self.n_estimators,
                contamination=self.contamination,
                random_state=self.random_state,
                decision_threshold=self.decision_threshold,
                warning_threshold=self.warning_threshold,
                critical_threshold=self.critical_threshold,
            )
            detector = OrbitalAnomalyDetector(config=reg_cfg)
            detector.fit(reg_sub)

            self.regime_models[regime] = detector
            self.regime_stats[regime] = {
                "status": "trained",
                "rows": n_rows,
                "satellites": n_sats,
                "raw_score_mean": detector.raw_score_mean,
                "raw_score_std": detector.raw_score_std,
            }

        if not self.regime_models:
            raise RuntimeError("No regime models could be trained. Check input data.")

        self.is_fitted = True
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict anomaly metrics by routing each observation to its regime model.

        Parameters
        ----------
        df : pd.DataFrame
            Input DataFrame with Layer 7 feature columns.

        Returns
        -------
        pd.DataFrame
            Copy of input DataFrame with added prediction columns:
            decision_score_raw, normalized_anomaly_score, is_anomaly, anomaly_severity,
            and regime_model_used.

        Raises
        ------
        RegimeModelNotFoundError
            If any observation belongs to a regime with no trained model.
        """
        if not self.is_fitted:
            raise RuntimeError("RegimeSpecificAnomalyDetector is not fitted. Call fit() first.")

        data = self._ensure_regime_column(df)
        result_df = data.copy()

        # Check for un-modeled regimes in input
        present_regimes = set(result_df["regime"].dropna().unique())
        missing_models = present_regimes - set(self.regime_models.keys())
        if missing_models:
            raise RegimeModelNotFoundError(
                f"No trained model for regime(s): {sorted(missing_models)}. "
                f"Available trained regimes: {sorted(self.regime_models.keys())}. "
                "Refusing silent fallback to unrelated regime models."
            )

        # Initialize output columns
        result_df["decision_score_raw"] = np.nan
        result_df["normalized_anomaly_score"] = np.nan
        result_df["is_anomaly"] = False
        result_df["anomaly_severity"] = "normal"
        result_df["regime_model_used"] = "none"

        # Predict per regime
        for regime, model in self.regime_models.items():
            mask = result_df["regime"] == regime
            if not mask.any():
                continue

            sub_df = result_df.loc[mask]
            scored_sub = model.predict(sub_df)

            result_df.loc[mask, "decision_score_raw"] = scored_sub["decision_score_raw"]
            result_df.loc[mask, "normalized_anomaly_score"] = scored_sub["normalized_anomaly_score"]
            result_df.loc[mask, "is_anomaly"] = scored_sub["is_anomaly"]
            result_df.loc[mask, "anomaly_severity"] = scored_sub["anomaly_severity"]
            result_df.loc[mask, "regime_model_used"] = regime

        return result_df

    def save(self, base_path_prefix: str = "models/isolation_forest_v2_regime") -> dict[str, Path]:
        """Save each trained regime model to a separate joblib file.

        Parameters
        ----------
        base_path_prefix : str
            Prefix for saved files, e.g. 'models/isolation_forest_v2_regime'
            produces 'models/isolation_forest_v2_regime_leo.joblib', etc.

        Returns
        -------
        dict[str, Path]
            Mapping of regime -> saved Path.
        """
        if not self.is_fitted:
            raise RuntimeError("Cannot save unfitted detector.")

        saved_paths: dict[str, Path] = {}
        prefix = Path(base_path_prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)

        for regime, model in self.regime_models.items():
            reg_file = prefix.parent / f"{prefix.name}_{regime.lower()}.joblib"
            model.save(str(reg_file))
            saved_paths[regime] = reg_file

        return saved_paths

    @classmethod
    def load(
        cls,
        base_path_prefix: str = "models/isolation_forest_v2_regime",
        expected_regimes: Sequence[str] = SUPPORTED_REGIMES,
    ) -> RegimeSpecificAnomalyDetector:
        """Load regime models from separate joblib files."""
        prefix = Path(base_path_prefix)
        detector = cls()
        detector.regime_models.clear()

        for regime in expected_regimes:
            reg_file = prefix.parent / f"{prefix.name}_{regime.lower()}.joblib"
            if reg_file.exists():
                model = OrbitalAnomalyDetector.load(str(reg_file))
                detector.regime_models[regime] = model
                detector.regime_stats[regime] = {
                    "status": "loaded",
                    "path": str(reg_file),
                    "raw_score_mean": model.raw_score_mean,
                    "raw_score_std": model.raw_score_std,
                }

        if not detector.regime_models:
            raise FileNotFoundError(
                f"No regime model files found with prefix: '{base_path_prefix}'"
            )

        detector.is_fitted = True
        return detector

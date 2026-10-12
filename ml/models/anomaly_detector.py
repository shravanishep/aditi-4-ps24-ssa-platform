"""
ml.models.anomaly_detector — Isolation Forest orbital anomaly detector.

This module provides the OrbitalAnomalyDetector class, which wraps scikit-learn's
IsolationForest to detect unusual orbital behaviour using Layer 7 features.

Design notes
------------
- Features: Uses 12 dynamic/temporal behavioural features (e.g. altitude, speed,
  specific energy, angular momentum, and their fixed-interval differences).
  Static GP elements (inclination, eccentricity, etc.) are excluded so that basic
  orbital regime differences (LEO vs MEO vs GEO) are not flagged as anomalies.
- Preprocessing: Uses physical values directly without scaling. Isolation Forest
  tree splits are invariant to monotonic feature transformations.
- Scoring: Computes raw decision scores and converts them into a normalized_anomaly_score
  in [0.0, 1.0], where higher values indicate higher degree of anomaly.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ml.models.config import BEHAVIOURAL_FEATURES, AnomalyModelConfig


class OrbitalAnomalyDetector:
    """Unsupervised Isolation Forest detector for satellite orbital behaviour anomalies."""

    def __init__(self, config: AnomalyModelConfig | None = None) -> None:
        self.config = config or AnomalyModelConfig()
        self.features: list[str] = list(self.config.features)

        self.model = IsolationForest(
            n_estimators=self.config.n_estimators,
            max_samples=self.config.max_samples,
            contamination=self.config.contamination,
            random_state=self.config.random_state,
            bootstrap=self.config.bootstrap,
        )
        self.is_fitted: bool = False
        self.raw_score_mean: float = 0.0
        self.raw_score_std: float = 1.0

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract and clean the feature matrix from an orbital DataFrame.

        Parameters
        ----------
        df:
            DataFrame containing Layer 7 dataset columns.

        Returns
        -------
        pd.DataFrame:
            Cleaned 12-feature matrix with NaNs imputed for initial observations.
        """
        # Validate required feature columns
        missing = [c for c in self.features if c not in df.columns]
        if missing:
            raise ValueError(f"DataFrame missing required feature columns: {missing}")

        X = df[self.features].copy()

        # Impute NaNs in temporal difference features (d_*) for initial satellite observations
        d_cols = [c for c in self.features if c.startswith("d_")]
        for col in d_cols:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)

        return X

    def fit(self, df: pd.DataFrame) -> OrbitalAnomalyDetector:
        """Fit the Isolation Forest model on training DataFrame.

        Parameters
        ----------
        df:
            Training DataFrame containing valid observations (sgp4_error == 0).

        Returns
        -------
        OrbitalAnomalyDetector:
            Self (fitted).
        """
        # Filter out SGP4 error rows if present
        if "sgp4_error" in df.columns:
            valid_df = df[df["sgp4_error"] == 0]
        else:
            valid_df = df

        X = self.prepare_features(valid_df)
        self.model.fit(X.to_numpy())
        self.is_fitted = True

        # Store baseline decision score distribution for score normalization
        raw_scores = self.model.score_samples(X.to_numpy())
        self.raw_score_mean = float(np.mean(raw_scores))
        self.raw_score_std = float(np.std(raw_scores)) if np.std(raw_scores) > 1e-9 else 1.0

        return self

    def _normalize_scores(self, raw_scores: np.ndarray) -> np.ndarray:
        """Map raw Isolation Forest scores into normalized_anomaly_score in [0.0, 1.0].

        Raw scores from sklearn score_samples:
          - High positive values (~ +0.1 to +0.5) => Normal observations (deep in tree)
          - Low/negative values (~ -0.1 to -0.5) => Anomalies (isolated near root)

        We apply a logistic transformation centered on the model threshold.
        Higher normalized_anomaly_score means higher degree of anomaly.
        """
        # Use z-score distance from mean, inverted so lower raw score => higher anomaly score
        z = (self.raw_score_mean - raw_scores) / self.raw_score_std
        # Logistic sigmoid mapping z -> [0.0, 1.0]
        normalized = 1.0 / (1.0 + np.exp(-z))
        return np.clip(normalized, 0.0, 1.0)

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict anomaly metrics for an input DataFrame.

        Returns a copy of input DataFrame with added prediction columns:
          - decision_score_raw (float32)
          - normalized_anomaly_score (float32)
          - is_anomaly (bool)
          - anomaly_severity (string: "normal", "warning", "critical")

        Parameters
        ----------
        df:
            Input DataFrame with Layer 7 feature columns.

        Returns
        -------
        pd.DataFrame:
            DataFrame with predictions attached.
        """
        if not self.is_fitted:
            raise RuntimeError("OrbitalAnomalyDetector is not fitted yet. Call fit() first.")

        result_df = df.copy()

        # Handle SGP4 error rows: valid vs error mask
        if "sgp4_error" in df.columns:
            valid_mask = df["sgp4_error"] == 0
        else:
            valid_mask = pd.Series(True, index=df.index)

        # Initialize output columns
        result_df["decision_score_raw"] = np.nan
        result_df["normalized_anomaly_score"] = np.nan
        result_df["is_anomaly"] = False
        result_df["anomaly_severity"] = "normal"

        if not valid_mask.any():
            return result_df

        valid_sub_df = df[valid_mask]
        X = self.prepare_features(valid_sub_df)

        raw_scores = self.model.score_samples(X.to_numpy())
        norm_scores = self._normalize_scores(raw_scores)

        # Binary prediction using explicit decision threshold on normalized_anomaly_score
        is_anomaly = norm_scores >= self.config.decision_threshold

        # Determine severity levels
        severities = []
        for norm_s in norm_scores:
            if norm_s >= self.config.critical_threshold:
                severities.append("critical")
            elif norm_s >= self.config.warning_threshold:
                severities.append("warning")
            else:
                severities.append("normal")

        # Assign back to valid rows
        result_df.loc[valid_mask, "decision_score_raw"] = raw_scores.astype("float32")
        result_df.loc[valid_mask, "normalized_anomaly_score"] = norm_scores.astype("float32")
        result_df.loc[valid_mask, "is_anomaly"] = is_anomaly
        result_df.loc[valid_mask, "anomaly_severity"] = severities

        return result_df

    def save(self, file_path: str | None = None) -> Path:
        """Serialize fitted detector to joblib file."""
        if not self.is_fitted:
            raise RuntimeError("Cannot save unfitted model.")

        path = Path(file_path or self.config.model_output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "config": self.config,
            "features": self.features,
            "model": self.model,
            "is_fitted": self.is_fitted,
            "raw_score_mean": self.raw_score_mean,
            "raw_score_std": self.raw_score_std,
        }
        joblib.dump(state, path)
        return path

    @classmethod
    def load(cls, file_path: str) -> OrbitalAnomalyDetector:
        """Load fitted detector from joblib file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        state: dict[str, Any] = joblib.load(path)
        detector = cls(config=state["config"])
        detector.features = state["features"]
        detector.model = state["model"]
        detector.is_fitted = state["is_fitted"]
        detector.raw_score_mean = state["raw_score_mean"]
        detector.raw_score_std = state["raw_score_std"]
        return detector

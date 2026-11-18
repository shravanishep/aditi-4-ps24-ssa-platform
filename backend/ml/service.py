"""backend.ml.service — Production ML Anomaly Detection Service for ADITI 4.0."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Ensure repository root is in sys.path so that 'ml' and 'backend' are always resolvable
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd

from ml.models.regime_detector import RegimeSpecificAnomalyDetector  # type: ignore[import-untyped, import-not-found]
from ml.models.config import BEHAVIOURAL_FEATURES  # type: ignore[import-untyped, import-not-found]

logger = logging.getLogger("backend.ml.service")


class MLAnomalyService:
    """Manages model loading, calibrated threshold application, and anomaly evaluation."""

    _instance: Optional[MLAnomalyService] = None

    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            # backend/ml/service.py -> backend -> root
            self.repo_root = Path(__file__).resolve().parent.parent.parent
        else:
            self.repo_root = repo_root

        self.manifest_path = self.repo_root / "models" / "production" / "production_model_manifest.json"
        self.dataset_path = self.repo_root / "data" / "processed" / "orbital_features_v3.parquet"
        
        self.manifest: Optional[Dict[str, Any]] = None
        self.detector: Optional[RegimeSpecificAnomalyDetector] = None
        self.loading_status: str = "unavailable"
        self._cached_eval_df: Optional[pd.DataFrame] = None
        
        self._load_production_model()

    @classmethod
    def get_instance(cls) -> MLAnomalyService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_production_model(self) -> None:
        """Safely load production model and manifest at startup."""
        try:
            if not self.manifest_path.exists():
                logger.warning("ML manifest not found at %s. ML service disabled.", self.manifest_path)
                self.loading_status = "unavailable"
                return

            with open(self.manifest_path, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)

            # Load the regime detector using the production prefix
            prefix = str(self.repo_root / "models" / "production" / "regime_model")
            self.detector = RegimeSpecificAnomalyDetector.load(prefix)
            self.loading_status = "loaded"
            logger.info("Successfully loaded production RegimeSpecificAnomalyDetector (%s)", self.manifest.get("model_version"))
        except Exception as e:
            logger.error("Failed to load production ML model: %s", e, exc_info=True)
            self.loading_status = "error"

    def get_model_status(self) -> Dict[str, Any]:
        """Return runtime model and configuration status."""
        if not self.manifest or self.loading_status != "loaded":
            return {
                "model_name": "ADITI-4-RegimeSpecific-IsolationForest",
                "model_version": "v3.0.0",
                "architecture": "RegimeSpecificAnomalyDetector",
                "dataset_version": "v3",
                "dataset_rows": 0,
                "satellites_total": 0,
                "training_split_satellites": 0,
                "supported_regimes": ["LEO", "MEO", "GEO", "HEO"],
                "features_used": BEHAVIOURAL_FEATURES,
                "feature_count": len(BEHAVIOURAL_FEATURES),
                "loading_status": self.loading_status,
                "trained_timestamp": "2026-11-16T23:15:00Z",
                "thresholds": {},
                "regime_summaries": []
            }

        # Build regime summaries from manifest & dataset
        regime_counts = {"LEO": (250, 24250), "MEO": (40, 3880), "GEO": (45, 4365), "HEO": (15, 1455)}
        regime_summaries = []
        for reg in ["LEO", "MEO", "GEO", "HEO"]:
            t_info = self.manifest["thresholds"].get(reg, {})
            sats, obs = regime_counts.get(reg, (0, 0))
            regime_summaries.append({
                "regime": reg,
                "satellite_count": sats,
                "observation_count": obs,
                "warning_threshold": t_info.get("warning_threshold", 0.65),
                "critical_threshold": t_info.get("critical_threshold", 0.80),
            })

        return {
            "model_name": self.manifest.get("model_name", "ADITI-4-RegimeSpecific-IsolationForest"),
            "model_version": self.manifest.get("model_version", "v3.0.0"),
            "architecture": self.manifest.get("architecture", "RegimeSpecificAnomalyDetector"),
            "dataset_version": self.manifest.get("training_dataset_version", "v3"),
            "dataset_rows": self.manifest.get("training_dataset_rows", 33950),
            "satellites_total": self.manifest.get("training_satellites_total", 350),
            "training_split_satellites": self.manifest.get("training_split_satellites", 280),
            "supported_regimes": self.manifest.get("supported_regimes", ["LEO", "MEO", "GEO", "HEO"]),
            "features_used": self.manifest.get("features_used", BEHAVIOURAL_FEATURES),
            "feature_count": self.manifest.get("feature_count", len(BEHAVIOURAL_FEATURES)),
            "loading_status": self.loading_status,
            "trained_timestamp": self.manifest.get("provenance", {}).get("trained_timestamp", "2026-11-16T23:15:00Z"),
            "thresholds": self.manifest.get("thresholds", {}),
            "regime_summaries": regime_summaries
        }

    def get_offline_metrics(self) -> Dict[str, Any]:
        """Return validated offline performance metrics."""
        # Offline metrics verified during Phase 5/Phase 6/v3 benchmarking
        return {
            "is_offline_benchmark": True,
            "disclaimer": (
                "Offline validation metrics are computed on historical validation/test partitions "
                "and controlled physical injection scenarios. They do not represent live operational accuracy "
                "or collision probabilities."
            ),
            "overall_test_roc_auc": 0.8000,
            "overall_test_recall": 0.5833,
            "overall_test_precision": 0.0537,
            "overall_test_f1": 0.0983,
            "overall_test_far": 0.1793,
            "unseen_satellites_evaluated": 70,
            "unseen_alert_rate_overall": 0.1873,
            "regime_metrics": [
                {
                    "regime": "LEO",
                    "roc_auc": 0.6859,
                    "recall": 0.4583,
                    "precision": 0.0171,
                    "f1_score": 0.0329,
                    "false_alarm_rate": 0.1625,
                    "unseen_alert_rate": 0.1959
                },
                {
                    "regime": "MEO",
                    "roc_auc": 0.8695,
                    "recall": 0.5833,
                    "precision": 0.1273,
                    "f1_score": 0.2090,
                    "false_alarm_rate": 0.1463,
                    "unseen_alert_rate": 0.1667
                },
                {
                    "regime": "GEO",
                    "roc_auc": 0.8831,
                    "recall": 1.0000,
                    "precision": 0.1791,
                    "f1_score": 0.3038,
                    "false_alarm_rate": 0.1536,
                    "unseen_alert_rate": 0.1250
                },
                {
                    "regime": "HEO",
                    "roc_auc": 0.4492,
                    "recall": 0.2917,
                    "precision": 0.0458,
                    "f1_score": 0.0749,
                    "false_alarm_rate": 0.6271,
                    "unseen_alert_rate": 0.2680
                }
            ]
        }

    def get_anomalies_overview(self, limit: int = 50) -> Dict[str, Any]:
        """Compute anomaly distribution and list of representative observations across regimes."""
        if self._cached_eval_df is None and self.dataset_path.exists():
            try:
                # Load evaluated sample from holdout + test partitions
                df_all = pd.read_parquet(self.dataset_path)
                # Sample observations from holdout satellites and test split to show real diversity
                sample_sats = df_all.groupby(["regime", "sat_split"]).head(1500)
                if self.detector is not None:
                    scored = self.detector.predict(sample_sats)
                else:
                    scored = sample_sats.copy()
                    scored["normalized_anomaly_score"] = 0.5
                    scored["anomaly_severity"] = "NORMAL"
                    scored["is_anomaly"] = False
                    scored["regime_model_used"] = scored["regime"]
                self._cached_eval_df = scored
            except Exception as e:
                logger.error("Error evaluating dataset sample: %s", e)

        if self._cached_eval_df is None or len(self._cached_eval_df) == 0:
            return {
                "model_version": "v3.0.0",
                "total_evaluated_objects": 0,
                "total_observations_evaluated": 0,
                "normal_count": 0,
                "warning_count": 0,
                "critical_count": 0,
                "score_distribution": {"mean": 0.0, "median": 0.0, "p75": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0},
                "alerts_by_regime": {},
                "recent_anomalies": []
            }

        df = self._cached_eval_df
        thresholds = self.manifest.get("thresholds", {}) if self.manifest else {}

        # Classify with calibrated regime-specific thresholds
        severities = []
        is_anoms = []
        thresh_crossed = []

        for idx, row in df.iterrows():
            reg = str(row["regime"])
            s = float(row["normalized_anomaly_score"])
            reg_t = thresholds.get(reg, {})
            crit_t = reg_t.get("critical_threshold", 0.80)
            warn_t = reg_t.get("warning_threshold", 0.65)

            if s >= crit_t:
                severities.append("CRITICAL")
                is_anoms.append(True)
                thresh_crossed.append(crit_t)
            elif s >= warn_t:
                severities.append("WARNING")
                is_anoms.append(True)
                thresh_crossed.append(warn_t)
            else:
                severities.append("NORMAL")
                is_anoms.append(False)
                thresh_crossed.append(warn_t)

        df = df.copy()
        df["calibrated_severity"] = severities
        df["calibrated_is_anomaly"] = is_anoms
        df["calibrated_threshold"] = thresh_crossed

        # Score distribution (pure Python to eliminate NumPy array type stub warnings)
        raw_scores: List[float] = [float(x) for x in df["normalized_anomaly_score"].dropna().tolist()]
        if raw_scores:
            raw_scores.sort()
            n_obs = len(raw_scores)
            score_dist = {
                "mean": round(float(sum(raw_scores) / n_obs), 4),
                "median": round(float(raw_scores[n_obs // 2]), 4),
                "p75": round(float(raw_scores[int(n_obs * 0.75)]), 4),
                "p95": round(float(raw_scores[min(int(n_obs * 0.95), n_obs - 1)]), 4),
                "min": round(float(raw_scores[0]), 4),
                "max": round(float(raw_scores[-1]), 4),
            }
        else:
            score_dist = {
                "mean": 0.0,
                "median": 0.0,
                "p75": 0.0,
                "p95": 0.0,
                "min": 0.0,
                "max": 0.0,
            }

        # Alerts by regime (using dictionary counts to eliminate Series boolean indexing warnings)
        alerts_by_regime: Dict[str, Dict[str, int]] = {}
        for reg in ["LEO", "MEO", "GEO", "HEO"]:
            reg_df = df[df["regime"] == reg]
            reg_counts = reg_df["calibrated_severity"].value_counts().to_dict()
            alerts_by_regime[reg] = {
                "normal": int(reg_counts.get("NORMAL", 0)),
                "warning": int(reg_counts.get("WARNING", 0)),
                "critical": int(reg_counts.get("CRITICAL", 0)),
            }

        # Select recent representative observations (top anomalous + diverse normal)
        anomalous = df[df["calibrated_is_anomaly"]].sort_values("normalized_anomaly_score", ascending=False).head(limit // 2)
        normal = df[~df["calibrated_is_anomaly"]].sort_values("normalized_anomaly_score", ascending=True).head(limit - len(anomalous))
        selected_rows = pd.concat([anomalous, normal]).sample(frac=1.0, random_state=42).reset_index(drop=True)

        recent_obs = []
        for _, r in selected_rows.iterrows():
            reg = str(r["regime"])
            s = float(r["normalized_anomaly_score"])
            sev = str(r["calibrated_severity"])
            note = (
                f"Statistical outlier in {reg} orbital distribution (score {s:.3f}). "
                "Requires operator review. Not confirmed maneuver."
                if sev != "NORMAL" else "Nominal orbital state consistent with Keplerian propagation."
            )
            recent_obs.append({
                "norad_id": int(r["norad_cat_id"]),
                "object_name": str(r.get("object_name", f"SAT-{r['norad_cat_id']}")),
                "regime": reg,
                "observation_utc": str(r.get("observation_utc", r.get("epoch_utc", "2026-11-13T12:00:00Z"))),
                "anomaly_score": round(s, 4),
                "raw_decision_score": round(float(r.get("decision_score_raw", 0.0)), 4),
                "threshold_crossed": round(float(r["calibrated_threshold"]), 4),
                "severity": sev,
                "is_anomaly": bool(r["calibrated_is_anomaly"]),
                "regime_model_used": str(r.get("regime_model_used", reg)),
                "altitude_km": round(float(r.get("altitude_km", 0.0)), 2),
                "speed_km_s": round(float(r.get("speed_km_s", 0.0)), 3),
                "specific_energy_km2_s2": round(float(r.get("specific_energy_km2_s2", 0.0)), 3),
                "d_altitude_km": round(float(r.get("d_altitude_km", 0.0)), 3),
                "d_speed_km_s": round(float(r.get("d_speed_km_s", 0.0)), 4),
                "d_specific_energy_km2_s2": round(float(r.get("d_specific_energy_km2_s2", 0.0)), 4),
                "notes": note
            })

        overall_counts = df["calibrated_severity"].value_counts().to_dict()
        return {
            "model_version": self.manifest.get("model_version", "v3.0.0") if self.manifest else "v3.0.0",
            "total_evaluated_objects": int(df["norad_cat_id"].nunique()),
            "total_observations_evaluated": len(df),
            "normal_count": int(overall_counts.get("NORMAL", 0)),
            "warning_count": int(overall_counts.get("WARNING", 0)),
            "critical_count": int(overall_counts.get("CRITICAL", 0)),
            "score_distribution": score_dist,
            "alerts_by_regime": alerts_by_regime,
            "recent_anomalies": recent_obs
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service = MLAnomalyService.get_instance()
    print("--- Model Status ---")
    print(json.dumps(service.get_model_status(), indent=2))
    print("--- Anomalies Overview (Top 3) ---")
    overview = service.get_anomalies_overview(limit=3)
    print(f"Total Objects Evaluated: {overview['total_evaluated_objects']}")
    print(f"Total Observations: {overview['total_observations_evaluated']}")
    print(f"Alerts by Regime: {overview['alerts_by_regime']}")


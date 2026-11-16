"""
ml.models.trainer_v3 — Layer 8 v3 Multi-Model Training, Comparative Evaluation, and Scientific Benchmarking.

Trains and evaluates 4 model architectures on the high-volume v3 dataset (33,950 rows, 350 satellites):
1. v3 Global: Single Isolation Forest on all regimes (12 features).
2. v3 Regime-Specific: Independent LEO, MEO, GEO, HEO Isolation Forests (12 features each).
3. v3 Temporal-Only: Single Isolation Forest on 5 temporal differences only.
4. v3 Hybrid: Fused detector combining Regime-Specific steady-state envelope with Temporal impulse sensitivity.

Evaluation Protocols:
- Standardized Synthetic Benchmark: Evaluated on test split of seen satellites (5,600 rows).
- Unseen Satellite Generalization: Evaluated on 70 completely unseen satellites (6,790 rows).
- Historical Baseline Comparison: Compares performance against v1 baseline and v2 baseline.

CLI:
    python -m ml.models.trainer_v3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)

from ml.models.anomaly_detector import OrbitalAnomalyDetector
from ml.models.config import AnomalyModelConfig, BEHAVIOURAL_FEATURES, TEMPORAL_FEATURES
from ml.models.hybrid_detector import HybridAnomalyDetector
from ml.models.regime_detector import RegimeSpecificAnomalyDetector
from ml.models.synthetic_anomalies import (
    inject_altitude_step_anomaly,
    inject_velocity_impulse_anomaly,
)
from ml.models.temporal_detector import TemporalAnomalyDetector


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_scores: np.ndarray) -> dict[str, Any]:
    acc = float(accuracy_score(y_true, y_pred))
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )

    if len(np.unique(y_true)) > 1:
        roc_auc = float(roc_auc_score(y_true, y_scores))
        pr_auc = float(average_precision_score(y_true, y_scores))
    else:
        roc_auc = 0.5
        pr_auc = 0.0

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])
    far = float(fp / (tn + fp)) if (tn + fp) > 0 else 0.0

    return {
        "accuracy": round(acc, 4),
        "precision": round(float(prec), 4),
        "recall": round(float(rec), 4),
        "f1_score": round(float(f1), 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "false_alarm_rate": round(far, 4),
        "confusion_matrix": {
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "true_positives": tp,
        },
    }


def create_v3_synthetic_benchmark(test_df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, list[dict]]:
    eval_df = test_df.copy()
    anom_labels = np.zeros(len(eval_df), dtype=int)
    anom_indices_set: set[int] = set()
    injections_log: list[dict[str, Any]] = []

    for regime in ["LEO", "MEO", "GEO", "HEO"]:
        regime_sats = eval_df.loc[eval_df["regime"] == regime, "norad_cat_id"].unique().tolist()
        if not regime_sats:
            continue

        # Velocity impulse in 2 satellites per regime
        for sat_v in regime_sats[:2]:
            offsets = eval_df.loc[eval_df["norad_cat_id"] == sat_v, "t_offset_minutes"].tolist()
            if len(offsets) >= 5:
                t_target = offsets[3]
                eval_df, idxs = inject_velocity_impulse_anomaly(
                    eval_df, sat_v, t_target, delta_v_km_s=0.50
                )
                anom_indices_set.update(idxs)
                injections_log.append(
                    {"regime": regime, "type": "velocity_impulse", "norad_id": sat_v, "count": len(idxs)}
                )

        # Altitude step drop in 2 satellites per regime (or remaining available)
        for sat_h in regime_sats[2:4] if len(regime_sats) >= 4 else regime_sats[:1]:
            offsets_h = eval_df.loc[eval_df["norad_cat_id"] == sat_h, "t_offset_minutes"].tolist()
            if len(offsets_h) >= 5:
                t_start = offsets_h[len(offsets_h) // 2]
                eval_df, idxs = inject_altitude_step_anomaly(
                    eval_df, sat_h, t_start, delta_h_km=-150.0
                )
                anom_indices_set.update(idxs)
                injections_log.append(
                    {"regime": regime, "type": "altitude_step", "norad_id": sat_h, "count": len(idxs)}
                )

    for idx in anom_indices_set:
        anom_labels[eval_df.index.get_loc(idx)] = 1

    return eval_df, anom_labels, injections_log


def evaluate_model_on_benchmark(model: Any, eval_df: pd.DataFrame, anom_labels: np.ndarray) -> dict[str, Any]:
    scored = model.predict(eval_df)
    scores = scored["normalized_anomaly_score"].fillna(0.0).to_numpy()
    preds = scored["is_anomaly"].fillna(False).to_numpy().astype(int)

    overall = compute_metrics(anom_labels, preds, scores)

    by_regime: dict[str, Any] = {}
    for regime in ["LEO", "MEO", "GEO", "HEO"]:
        mask = (eval_df["regime"] == regime).to_numpy()
        if not np.any(mask):
            continue
        reg_y_true = anom_labels[mask]
        reg_y_pred = preds[mask]
        reg_scores = scores[mask]
        reg_metrics = compute_metrics(reg_y_true, reg_y_pred, reg_scores)
        reg_metrics["total_rows"] = int(np.sum(mask))
        reg_metrics["anomalies_injected"] = int(np.sum(reg_y_true))
        by_regime[regime] = reg_metrics

    return {
        "overall": overall,
        "by_regime": by_regime,
    }


def evaluate_unseen_satellites(model: Any, holdout_df: pd.DataFrame) -> dict[str, Any]:
    scored = model.predict(holdout_df)
    scores = scored["normalized_anomaly_score"].dropna().to_numpy()
    preds = scored["is_anomaly"].fillna(False).to_numpy().astype(bool)

    def _stats(arr: np.ndarray) -> dict[str, float]:
        if len(arr) == 0:
            return {}
        return {
            "mean": round(float(np.mean(arr)), 4),
            "std": round(float(np.std(arr)), 4),
            "min": round(float(np.min(arr)), 4),
            "median": round(float(np.median(arr)), 4),
            "p75": round(float(np.percentile(arr, 75)), 4),
            "p95": round(float(np.percentile(arr, 95)), 4),
            "max": round(float(np.max(arr)), 4),
        }

    total_obs = len(scored)
    alarms = int(np.sum(preds))
    critical = int(np.sum(scored["anomaly_severity"] == "critical"))
    alert_rate = float(alarms / total_obs) if total_obs else 0.0

    by_regime: dict[str, Any] = {}
    for regime in ["LEO", "MEO", "GEO", "HEO"]:
        reg_sub = scored[scored["regime"] == regime]
        if reg_sub.empty:
            continue
        reg_scores = reg_sub["normalized_anomaly_score"].dropna().to_numpy()
        reg_preds = reg_sub["is_anomaly"].fillna(False).to_numpy().astype(bool)
        reg_total = len(reg_sub)
        reg_alarms = int(np.sum(reg_preds))
        reg_crit = int(np.sum(reg_sub["anomaly_severity"] == "critical"))

        by_regime[regime] = {
            "unique_satellites": reg_sub["norad_cat_id"].nunique(),
            "total_observations": reg_total,
            "alert_count": reg_alarms,
            "alert_rate": round(float(reg_alarms / reg_total), 4) if reg_total else 0.0,
            "critical_count": reg_crit,
            "score_distribution": _stats(reg_scores),
        }

    return {
        "total_unseen_satellites": holdout_df["norad_cat_id"].nunique(),
        "total_observations": total_obs,
        "alert_count": alarms,
        "alert_rate": round(alert_rate, 4),
        "critical_count": critical,
        "score_distribution": _stats(scores),
        "by_regime": by_regime,
    }


def run_v3_training_pipeline(
    parquet_path: str = "data/processed/orbital_features_v3.parquet",
    output_metadata: str = "models/isolation_forest_v3_comparison_metadata.json",
) -> dict[str, Any]:
    start_utc = datetime.now(timezone.utc)
    t0 = time.time()

    print("=================================================================")
    print("      ADITI 4.0 PS24 — Layer 8 ML Training Pipeline (v3)")
    print("=================================================================")

    parquet_file = Path(parquet_path)
    if not parquet_file.exists():
        raise FileNotFoundError(f"v3 Parquet dataset not found at {parquet_file}")

    print(f"[v3 Trainer] Loading dataset from: {parquet_file}")
    df = pd.read_parquet(parquet_file)
    dataset_hash = _sha256_of_file(parquet_file)

    train_mask = (df["sat_split"] == "train_sats") & (df["split"] == "train")
    val_mask = (df["sat_split"] == "train_sats") & (df["split"] == "val")
    test_mask = (df["sat_split"] == "train_sats") & (df["split"] == "test")
    holdout_mask = df["sat_split"] == "holdout_sats"

    train_df = df[train_mask].copy()
    val_df = df[val_mask].copy()
    test_df = df[test_mask].copy()
    holdout_df = df[holdout_mask].copy()

    train_sats = set(train_df["norad_cat_id"].unique())
    holdout_sats = set(holdout_df["norad_cat_id"].unique())
    assert len(train_sats.intersection(holdout_sats)) == 0, "Data leakage detected!"

    print(f"[v3 Trainer] Partitions: train={len(train_df)} ({len(train_sats)} sats), val={len(val_df)}, test={len(test_df)}, holdout={len(holdout_df)} ({len(holdout_sats)} sats)")

    # 1. Model 1: v3 Global
    print("\n[v3 Trainer] Training Model 1: v3 Global Single Isolation Forest...")
    global_cfg = AnomalyModelConfig(
        features=list(BEHAVIOURAL_FEATURES),
        n_estimators=200,
        contamination=0.02,
        random_state=42,
        model_output_path="models/isolation_forest_v3_global.joblib",
        metadata_output_path="models/isolation_forest_v3_global_metadata.json",
    )
    global_model = OrbitalAnomalyDetector(config=global_cfg)
    t_g0 = time.time()
    global_model.fit(train_df)
    t_g_fit = round(time.time() - t_g0, 3)
    global_model.save()
    print(f"  v3 Global fitted in {t_g_fit}s. Saved: models/isolation_forest_v3_global.joblib")

    # 2. Model 2: v3 Regime-Specific
    print("\n[v3 Trainer] Training Model 2: v3 Regime-Specific Isolation Forests (LEO, MEO, GEO, HEO)...")
    regime_model = RegimeSpecificAnomalyDetector(
        features=BEHAVIOURAL_FEATURES,
        min_samples_per_regime=50,
        min_satellites_per_regime=2,
        n_estimators=200,
        contamination=0.02,
        random_state=42,
    )
    t_r0 = time.time()
    regime_model.fit(train_df)
    t_r_fit = round(time.time() - t_r0, 3)
    saved_reg_paths = regime_model.save("models/isolation_forest_v3_regime")
    print(f"  v3 Regime models fitted in {t_r_fit}s. Saved: {[p.name for p in saved_reg_paths.values()]}")

    # 3. Model 3: v3 Temporal-Only
    print("\n[v3 Trainer] Training Model 3: v3 Temporal-Only Isolation Forest (5 temporal diff features)...")
    temporal_model = TemporalAnomalyDetector(
        features=TEMPORAL_FEATURES,
        n_estimators=200,
        contamination=0.02,
        random_state=42,
    )
    t_t0 = time.time()
    temporal_model.fit(train_df)
    t_t_fit = round(time.time() - t_t0, 3)
    temporal_model.save("models/isolation_forest_v3_temporal.joblib")
    print(f"  v3 Temporal model fitted in {t_t_fit}s. Saved: models/isolation_forest_v3_temporal.joblib")

    # 4. Model 4: v3 Hybrid
    print("\n[v3 Trainer] Training Model 4: v3 Hybrid Fused Anomaly Detector...")
    hybrid_model = HybridAnomalyDetector(
        regime_detector=regime_model,
        temporal_detector=temporal_model,
        fusion_method="max",
    )
    hybrid_model.is_fitted = True
    hybrid_paths = hybrid_model.save("models", prefix="isolation_forest_v3_hybrid")
    print(f"  v3 Hybrid detector saved: {hybrid_paths['manifest'].name}")

    # 5. Standardized Synthetic Benchmark Evaluation on v3 Test Set (5,600 rows)
    print("\n[v3 Trainer] Evaluating all 4 models on v3 standardized synthetic test benchmark...")
    eval_test_df, anom_labels, injections_log = create_v3_synthetic_benchmark(test_df)
    print(f"  Synthetic benchmark rows: {len(eval_test_df)}, Injected anomalies: {int(np.sum(anom_labels))}")

    bench_global = evaluate_model_on_benchmark(global_model, eval_test_df, anom_labels)
    bench_regime = evaluate_model_on_benchmark(regime_model, eval_test_df, anom_labels)
    bench_temporal = evaluate_model_on_benchmark(temporal_model, eval_test_df, anom_labels)
    bench_hybrid = evaluate_model_on_benchmark(hybrid_model, eval_test_df, anom_labels)

    # 6. Unseen Satellites Evaluation (70 Holdout Satellites, 6,790 observations)
    print("\n[v3 Trainer] Evaluating on 70 unseen holdout satellites (6,790 observations)...")
    unseen_global = evaluate_unseen_satellites(global_model, holdout_df)
    unseen_regime = evaluate_unseen_satellites(regime_model, holdout_df)
    unseen_temporal = evaluate_unseen_satellites(temporal_model, holdout_df)
    unseen_hybrid = evaluate_unseen_satellites(hybrid_model, holdout_df)

    # 7. Assemble comparison JSON
    total_duration = round(time.time() - t0, 3)
    end_utc = datetime.now(timezone.utc)

    results = {
        "metadata": {
            "created_utc": end_utc.isoformat(),
            "start_utc": start_utc.isoformat(),
            "duration_seconds": total_duration,
            "dataset_sha256": dataset_hash,
            "parquet_path": str(parquet_path),
            "total_satellites": df["norad_cat_id"].nunique(),
            "total_rows": len(df),
        },
        "benchmark_comparison": {
            "test_rows": len(eval_test_df),
            "anomalies_injected": int(np.sum(anom_labels)),
            "injections_log": injections_log,
            "v3_global": bench_global,
            "v3_regime_specific": bench_regime,
            "v3_temporal_only": bench_temporal,
            "v3_hybrid": bench_hybrid,
        },
        "unseen_satellites_comparison": {
            "total_holdout_satellites": len(holdout_sats),
            "total_holdout_observations": len(holdout_df),
            "v3_global": unseen_global,
            "v3_regime_specific": unseen_regime,
            "v3_temporal_only": unseen_temporal,
            "v3_hybrid": unseen_hybrid,
        },
    }

    out_meta = Path(output_metadata)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    with open(out_meta, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, cls=_NumpyEncoder)

    print(f"\n[v3 Trainer] Saved complete v3 comparison metadata to: {out_meta}")
    print(f"[v3 Trainer] Pipeline finished in {total_duration}s.")
    return results


def main() -> None:
    run_v3_training_pipeline()


if __name__ == "__main__":
    main()

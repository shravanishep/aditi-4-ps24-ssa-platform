"""
ml.models.trainer — Layer 8 Isolation Forest training & evaluation pipeline.

Orchestrates loading the Layer 7 feature dataset, fitting the OrbitalAnomalyDetector
on the 'train' split, evaluating baseline score distributions on 'val'/'test' splits,
running physically consistent synthetic anomaly benchmarks (ROC-AUC, PR-AUC, Precision,
Recall), and saving the model joblib and metadata JSON.

CLI entrypoint:
    python -m ml.models.trainer
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_fscore_support, roc_auc_score

from ml.models.anomaly_detector import OrbitalAnomalyDetector
from ml.models.config import BEHAVIOURAL_FEATURES, AnomalyModelConfig
from ml.models.synthetic_anomalies import inject_altitude_step_anomaly, inject_velocity_impulse_anomaly


def run_training_pipeline(config: AnomalyModelConfig | None = None) -> tuple[OrbitalAnomalyDetector, dict]:
    """Execute the complete Layer 8 model training and evaluation pipeline.

    Parameters
    ----------
    config:
        Model configuration instance (defaults to AnomalyModelConfig()).

    Returns
    -------
    tuple[OrbitalAnomalyDetector, dict]:
        (Fitted detector instance, Execution metadata dictionary).
    """
    config = config or AnomalyModelConfig()
    start_time = datetime.now(timezone.utc)

    parquet_path = config.get_parquet_path()
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Layer 7 Parquet dataset not found at '{parquet_path}'. "
            "Run 'python -m ml.pipeline.dataset_builder' first."
        )

    print(f"[Layer 8] Loading feature dataset from: {parquet_path}")
    df = pd.read_parquet(parquet_path)

    # Validate split column presence
    if "split" not in df.columns:
        raise ValueError("Input Parquet dataset missing required 'split' column.")

    train_df = df[df["split"] == "train"]
    val_df = df[df["split"] == "val"]
    test_df = df[df["split"] == "test"]

    print(f"[Layer 8] Dataset splits loaded:")
    print(f"  Train : {len(train_df)} rows")
    print(f"  Val   : {len(val_df)} rows")
    print(f"  Test  : {len(test_df)} rows")

    # 1. Fit detector on train split
    print(f"[Layer 8] Training Isolation Forest model on 12 behavioural features...")
    detector = OrbitalAnomalyDetector(config)
    detector.fit(train_df)

    # 2. Score baseline validation and test splits
    scored_train = detector.predict(train_df)
    scored_val = detector.predict(val_df)
    scored_test = detector.predict(test_df)

    val_norm_scores = scored_val["normalized_anomaly_score"].dropna().to_numpy()
    test_norm_scores = scored_test["normalized_anomaly_score"].dropna().to_numpy()

    val_stats = {
        "mean": float(np.mean(val_norm_scores)),
        "std": float(np.std(val_norm_scores)),
        "p95": float(np.percentile(val_norm_scores, 95)),
        "p99": float(np.percentile(val_norm_scores, 99)),
    }

    test_stats = {
        "mean": float(np.mean(test_norm_scores)),
        "std": float(np.std(test_norm_scores)),
        "p95": float(np.percentile(test_norm_scores, 95)),
        "p99": float(np.percentile(test_norm_scores, 99)),
    }

    print(f"[Layer 8] Baseline score statistics:")
    print(f"  Val  -> mean: {val_stats['mean']:.4f}, p95: {val_stats['p95']:.4f}, p99: {val_stats['p99']:.4f}")
    print(f"  Test -> mean: {test_stats['mean']:.4f}, p95: {test_stats['p95']:.4f}, p99: {test_stats['p99']:.4f}")

    # 3. Synthetic Anomaly Benchmark Evaluation
    print(f"[Layer 8] Running physically consistent synthetic anomaly benchmark...")
    synthetic_eval = _evaluate_synthetic_benchmark(detector, test_df)

    print(f"  ROC-AUC   : {synthetic_eval['roc_auc']:.4f}")
    print(f"  PR-AUC    : {synthetic_eval['pr_auc']:.4f}")
    print(f"  Precision : {synthetic_eval['precision']:.4f}")
    print(f"  Recall    : {synthetic_eval['recall']:.4f}")
    print(f"  F1 Score  : {synthetic_eval['f1_score']:.4f}")

    # 4. Save fitted model artifact
    model_path = detector.save()
    print(f"[Layer 8] Saved model to: {model_path}")

    # 5. Build and save metadata JSON
    end_time = datetime.now(timezone.utc)
    dataset_sha256 = hashlib.sha256(parquet_path.read_bytes()).hexdigest()

    metadata = {
        "build_info": {
            "created_utc": end_time.isoformat(),
            "duration_seconds": round((end_time - start_time).total_seconds(), 3),
            "layer": "Layer 8 — Orbital Behaviour Anomaly Detection",
            "platform": "ADITI 4.0 PS24 SSA Platform",
        },
        "model_info": {
            "model_type": "IsolationForest",
            "model_version": "1.0.0",
            "features": config.features,
            "n_features": len(config.features),
            "n_estimators": config.n_estimators,
            "max_samples": config.max_samples,
            "contamination_param": config.contamination,
            "random_state": config.random_state,
            "decision_thresholds": {
                "decision_threshold": config.decision_threshold,
                "warning": config.warning_threshold,
                "critical": config.critical_threshold,
            },
        },
        "dataset_info": {
            "parquet_path": str(parquet_path),
            "dataset_hash": dataset_sha256,
            "train_rows": len(train_df),
            "val_rows": len(val_df),
            "test_rows": len(test_df),
        },
        "baseline_score_stats": {
            "val": val_stats,
            "test": test_stats,
        },
        "synthetic_benchmark": synthetic_eval,
        "notes": [
            "Features strictly limited to 12 dynamic state magnitudes and temporal differences.",
            "Static orbital elements are excluded from detector input to prevent regime-based false positives.",
            "No scaling applied; physical values passed directly to Isolation Forest.",
            "Synthetic anomaly evaluation enforces 100% physical feature consistency.",
        ],
    }

    metadata_path = config.get_metadata_path()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"[Layer 8] Saved metadata to: {metadata_path}")
    return detector, metadata


def _evaluate_synthetic_benchmark(detector: OrbitalAnomalyDetector, test_df: pd.DataFrame) -> dict:
    """Evaluate detector on a synthetic test set containing physically consistent anomalies.

    Parameters
    ----------
    detector:
        Fitted OrbitalAnomalyDetector instance.
    test_df:
        Clean baseline test set DataFrame.

    Returns
    -------
    dict:
        Evaluation metrics dictionary (roc_auc, pr_auc, precision, recall, f1_score).
    """
    if test_df.empty:
        return {"roc_auc": 0.0, "pr_auc": 0.0, "precision": 0.0, "recall": 0.0, "f1_score": 0.0}

    norad_ids = test_df["norad_cat_id"].unique().tolist()
    if not norad_ids:
        return {"roc_auc": 0.0, "pr_auc": 0.0, "precision": 0.0, "recall": 0.0, "f1_score": 0.0}

    eval_df = test_df.copy()
    anom_labels = np.zeros(len(eval_df), dtype=int)
    anom_indices_set = set()

    # Inject velocity impulses into first 2 satellites
    for target_id in norad_ids[:2]:
        target_offsets = eval_df[eval_df["norad_cat_id"] == target_id]["t_offset_minutes"].tolist()
        if len(target_offsets) >= 5:
            # Inject prograde impulse at index 3
            t_target = target_offsets[3]
            eval_df, indices = inject_velocity_impulse_anomaly(eval_df, target_id, t_target, delta_v_km_s=0.50)
            anom_indices_set.update(indices)

    # Inject altitude drop step into next satellite if available
    if len(norad_ids) >= 3:
        target_id = norad_ids[2]
        target_offsets = eval_df[eval_df["norad_cat_id"] == target_id]["t_offset_minutes"].tolist()
        if len(target_offsets) >= 5:
            t_start = target_offsets[len(target_offsets) // 2]
            eval_df, indices = inject_altitude_step_anomaly(eval_df, target_id, t_start, delta_h_km=-150.0)
            anom_indices_set.update(indices)

    for idx in anom_indices_set:
        anom_labels[eval_df.index.get_loc(idx)] = 1

    # Score perturbed evaluation DataFrame
    scored_eval = detector.predict(eval_df)
    scores = scored_eval["normalized_anomaly_score"].fillna(0.0).to_numpy()
    preds = scored_eval["is_anomaly"].fillna(False).to_numpy().astype(int)

    # Calculate empirical performance metrics
    if len(np.unique(anom_labels)) > 1:
        roc_auc = float(roc_auc_score(anom_labels, scores))
        pr_auc = float(average_precision_score(anom_labels, scores))
    else:
        roc_auc = 0.5
        pr_auc = 0.0

    precision, recall, f1, _ = precision_recall_fscore_support(anom_labels, preds, average="binary", zero_division=0)
    cm = confusion_matrix(anom_labels, preds)
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

    fp_mask = (anom_labels == 0) & (preds == 1)
    fp_satellites = {int(k): int(v) for k, v in eval_df.loc[fp_mask, "norad_cat_id"].value_counts().items()}

    return {
        "total_test_rows": len(test_df),
        "synthetic_anomalies_injected": int(np.sum(anom_labels)),
        "decision_threshold": detector.config.decision_threshold,
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1_score": round(float(f1), 4),
        "confusion_matrix": {
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "true_positives": tp,
        },
        "false_positives_by_satellite": fp_satellites,
    }


if __name__ == "__main__":
    run_training_pipeline()

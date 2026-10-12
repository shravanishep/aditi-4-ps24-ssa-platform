"""
tests/test_model_trainer.py — Integration tests for Layer 8 training pipeline.

Verifies end-to-end training execution, metadata creation, and synthetic benchmark output.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ml.models.config import AnomalyModelConfig
from ml.models.trainer import run_training_pipeline


def test_full_training_pipeline():
    """run_training_pipeline must fit detector, run evaluation, and produce joblib + metadata JSON."""
    parquet_path = "data/processed/orbital_features.parquet"
    if not Path(parquet_path).exists():
        pytest.skip(f"Dataset Parquet file not found at '{parquet_path}'.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        model_path = Path(tmp_dir) / "test_iforest.joblib"
        metadata_path = Path(tmp_dir) / "test_iforest_metadata.json"

        config = AnomalyModelConfig(
            parquet_path=parquet_path,
            model_output_path=str(model_path),
            metadata_output_path=str(metadata_path),
            n_estimators=50,  # Fast test execution
            random_state=42,
        )

        detector, metadata = run_training_pipeline(config)

        assert detector.is_fitted
        assert model_path.exists()
        assert metadata_path.exists()

        # Check metadata content
        with open(metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        assert "build_info" in meta
        assert "model_info" in meta
        assert "synthetic_benchmark" in meta
        assert meta["model_info"]["n_features"] == 12
        assert "roc_auc" in meta["synthetic_benchmark"]
        assert "pr_auc" in meta["synthetic_benchmark"]

"""
tests/test_dataset_builder.py — Integration tests for the Layer 7 pipeline.

These tests run the full dataset builder against a small fixture
(3 satellites, 2-hour window, 30-minute step = 5 observations per satellite)
to keep the test suite fast (< 3 seconds).

The GP CSV used is the real data/raw/active_satellites_gp.csv, selecting
the first 3 satellites by NORAD_CAT_ID for determinism.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from ml.pipeline.config import PipelineConfig
from ml.pipeline.dataset_builder import build_dataset, write_outputs
from ml.pipeline.feature_engineering import EXPECTED_COLUMNS, FEATURE_SCHEMA
from ml.pipeline.validation import DatasetValidationError

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Fixture — small pipeline config for fast tests
# ---------------------------------------------------------------------------

_GP_CSV = "data/raw/active_satellites_gp.csv"

# 2-hour window, 30-min step => 5 observations per satellite (0, 30, 60, 90, 120 min offset)
_FIXTURE_CONFIG = PipelineConfig(
    gp_csv_path=_GP_CSV,
    output_parquet_path="data/processed/_test_orbital_features.parquet",
    output_metadata_path="data/processed/_test_orbital_features_metadata.json",
    window_hours=2.0,
    step_minutes=30.0,
    max_satellites=3,
    max_sgp4_error_pct=100.0,  # No warnings in tests
    train_frac=0.60,
    val_frac=0.20,
)

_EXPECTED_STEPS = _FIXTURE_CONFIG.n_steps()  # 5
_EXPECTED_MAX_ROWS = 3 * _EXPECTED_STEPS     # 15


@pytest.fixture(scope="module")
def fixture_df() -> pd.DataFrame:
    """Build the small fixture dataset once for all tests in this module."""
    return build_dataset(_FIXTURE_CONFIG)


@pytest.fixture(scope="module")
def fixture_output_paths(fixture_df, tmp_path_factory):
    """Write the fixture dataset to a temp directory and return the paths."""
    tmp = tmp_path_factory.mktemp("layer7_outputs")
    parquet_path = tmp / "orbital_features.parquet"
    metadata_path = tmp / "orbital_features_metadata.json"

    cfg = PipelineConfig(
        gp_csv_path=_GP_CSV,
        output_parquet_path=str(parquet_path),
        output_metadata_path=str(metadata_path),
        window_hours=2.0,
        step_minutes=30.0,
        max_satellites=3,
        max_sgp4_error_pct=100.0,
        train_frac=0.60,
        val_frac=0.20,
    )
    write_outputs(
        fixture_df,
        cfg,
        Path(_GP_CSV),
        datetime.now(tz=timezone.utc),
    )
    return parquet_path, metadata_path


# ---------------------------------------------------------------------------
# Test: output schema
# ---------------------------------------------------------------------------


class TestOutputSchema:

    def test_all_columns_present(self, fixture_df):
        """All expected columns must be present in the output."""
        missing = [c for c in EXPECTED_COLUMNS if c not in fixture_df.columns]
        assert missing == [], f"Missing columns: {missing}"

    def test_column_count_matches_expected(self, fixture_df):
        """The dataset must have exactly len(EXPECTED_COLUMNS) (40) columns."""
        assert len(fixture_df.columns) == len(EXPECTED_COLUMNS), (
            f"Expected {len(EXPECTED_COLUMNS)} columns, got {len(fixture_df.columns)}: {list(fixture_df.columns)}"
        )

    def test_float32_columns_are_float(self, fixture_df):
        """All float32-schema columns must have numeric dtype."""
        float_cols = [c for c, t in FEATURE_SCHEMA.items() if t == "float32"]
        for col in float_cols:
            assert pd.api.types.is_float_dtype(fixture_df[col]), (
                f"Column '{col}' should be float dtype, got {fixture_df[col].dtype}"
            )

    def test_column_order_matches_schema(self, fixture_df):
        """Column order in output must match EXPECTED_COLUMNS."""
        assert list(fixture_df.columns) == EXPECTED_COLUMNS


# ---------------------------------------------------------------------------
# Test: row count
# ---------------------------------------------------------------------------


class TestRowCount:

    def test_row_count_within_expected(self, fixture_df):
        """Row count should equal n_satellites * n_steps (or less if some skipped)."""
        n_rows = len(fixture_df)
        assert n_rows <= _EXPECTED_MAX_ROWS, (
            f"Got {n_rows} rows, expected at most {_EXPECTED_MAX_ROWS}."
        )
        # Must have at least 1 satellite worth of data
        assert n_rows >= _EXPECTED_STEPS, (
            f"Got only {n_rows} rows — fewer than one satellite's worth ({_EXPECTED_STEPS})."
        )

    def test_n_steps_per_satellite(self, fixture_df):
        """Each satellite must have exactly n_steps rows."""
        for norad_id, group in fixture_df.groupby("norad_cat_id"):
            assert len(group) == _EXPECTED_STEPS, (
                f"NORAD {norad_id}: expected {_EXPECTED_STEPS} rows, got {len(group)}."
            )


# ---------------------------------------------------------------------------
# Test: no duplicate observations
# ---------------------------------------------------------------------------


class TestNoDuplicates:

    def test_no_duplicate_observation_keys(self, fixture_df):
        """(norad_cat_id, observation_utc) must be unique across the dataset."""
        dupes = fixture_df.duplicated(subset=["norad_cat_id", "observation_utc"])
        assert not dupes.any(), f"Found {dupes.sum()} duplicate (norad_cat_id, observation_utc) pairs."


# ---------------------------------------------------------------------------
# Test: split assignment
# ---------------------------------------------------------------------------


class TestSplitAssignment:

    def test_split_values_valid(self, fixture_df):
        """split column must contain only train, val, test."""
        valid = {"train", "val", "test"}
        actual = set(fixture_df["split"].unique())
        assert actual <= valid, f"Invalid split values: {actual - valid}"

    def test_split_all_three_present(self, fixture_df):
        """All three split labels should be present with n_steps=5."""
        # 5 rows: train=3, val=1, test=1 (int(5*0.6)=3, int(5*0.8)=4)
        splits = set(fixture_df["split"].unique())
        assert "train" in splits
        assert "val" in splits
        assert "test" in splits

    def test_no_leakage_in_split(self, fixture_df):
        """Within each satellite: all train t_offsets < val, val < test."""
        for norad_id, group in fixture_df.groupby("norad_cat_id"):
            train = group.loc[group["split"] == "train", "t_offset_minutes"]
            val = group.loc[group["split"] == "val", "t_offset_minutes"]
            test = group.loc[group["split"] == "test", "t_offset_minutes"]
            if len(train) > 0 and len(val) > 0:
                assert train.max() < val.min(), (
                    f"NORAD {norad_id}: train max {train.max()} >= val min {val.min()}"
                )
            if len(val) > 0 and len(test) > 0:
                assert val.max() < test.min(), (
                    f"NORAD {norad_id}: val max {val.max()} >= test min {test.min()}"
                )


# ---------------------------------------------------------------------------
# Test: temporal ordering and t_offset monotonicity
# ---------------------------------------------------------------------------


class TestTemporalOrdering:

    def test_t_offset_monotonic_per_satellite(self, fixture_df):
        """t_offset_minutes must be non-decreasing within each satellite."""
        for norad_id, group in fixture_df.groupby("norad_cat_id"):
            offsets = group["t_offset_minutes"].values
            assert (offsets[1:] >= offsets[:-1]).all(), (
                f"NORAD {norad_id}: t_offset_minutes is not monotonic."
            )

    def test_first_row_has_nan_d_features(self, fixture_df):
        """The first (earliest) row per satellite must have NaN d_* values."""
        for norad_id, group in fixture_df.groupby("norad_cat_id"):
            first = group.sort_values("t_offset_minutes").iloc[0]
            assert math.isnan(first["dt_minutes"]), f"NORAD {norad_id}: dt_minutes should be NaN"
            assert math.isnan(first["d_altitude_km"]), f"NORAD {norad_id}: d_altitude_km should be NaN"


# ---------------------------------------------------------------------------
# Test: max_satellites cap
# ---------------------------------------------------------------------------


class TestMaxSatellitesCap:

    def test_max_satellites_cap(self):
        """max_satellites=3 must produce exactly 3 unique NORAD IDs."""
        cfg = PipelineConfig(
            gp_csv_path=_GP_CSV,
            max_satellites=3,
            window_hours=1.0,
            step_minutes=30.0,
            max_sgp4_error_pct=100.0,
        )
        df = build_dataset(cfg)
        assert df["norad_cat_id"].nunique() == 3, (
            f"Expected 3 unique NORAD IDs, got {df['norad_cat_id'].nunique()}."
        )


# ---------------------------------------------------------------------------
# Test: metadata written correctly
# ---------------------------------------------------------------------------


class TestMetadataOutput:

    def test_metadata_file_exists(self, fixture_output_paths):
        _, metadata_path = fixture_output_paths
        assert metadata_path.exists(), "Metadata JSON file was not created."

    def test_metadata_required_keys(self, fixture_output_paths):
        _, metadata_path = fixture_output_paths
        with open(metadata_path, "r") as f:
            meta = json.load(f)
        required_keys = {"build_info", "input", "config", "output", "schema", "notes"}
        assert required_keys <= set(meta.keys()), (
            f"Metadata missing keys: {required_keys - set(meta.keys())}"
        )

    def test_metadata_schema_has_all_columns(self, fixture_output_paths):
        _, metadata_path = fixture_output_paths
        with open(metadata_path, "r") as f:
            meta = json.load(f)
        assert set(meta["schema"].keys()) == set(EXPECTED_COLUMNS), (
            "Metadata schema does not match EXPECTED_COLUMNS."
        )

    def test_metadata_row_count_matches(self, fixture_df, fixture_output_paths):
        _, metadata_path = fixture_output_paths
        with open(metadata_path, "r") as f:
            meta = json.load(f)
        assert meta["output"]["total_rows"] == len(fixture_df)

    def test_metadata_gp_csv_hash_present(self, fixture_output_paths):
        _, metadata_path = fixture_output_paths
        with open(metadata_path, "r") as f:
            meta = json.load(f)
        assert "gp_csv_sha256" in meta["input"]
        assert len(meta["input"]["gp_csv_sha256"]) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# Test: reproducibility (DataFrame level, not byte level)
# ---------------------------------------------------------------------------


class TestReproducibility:

    def test_deterministic_values(self):
        """Two runs with the same config produce identical DataFrame values."""
        cfg = PipelineConfig(
            gp_csv_path=_GP_CSV,
            max_satellites=3,
            window_hours=1.0,
            step_minutes=30.0,
            max_sgp4_error_pct=100.0,
        )
        df1 = build_dataset(cfg)
        df2 = build_dataset(cfg)

        # Same columns
        assert list(df1.columns) == list(df2.columns)

        # Same row count and order
        assert len(df1) == len(df2)

        # Same NORAD IDs and t_offset_minutes (identity and temporal coordinates)
        pd.testing.assert_series_equal(
            df1["norad_cat_id"].reset_index(drop=True),
            df2["norad_cat_id"].reset_index(drop=True),
        )
        pd.testing.assert_series_equal(
            df1["t_offset_minutes"].reset_index(drop=True),
            df2["t_offset_minutes"].reset_index(drop=True),
            check_exact=False,
            atol=1e-6,
        )

        # Same numeric feature values for valid rows
        numeric_cols = [
            c for c, t in FEATURE_SCHEMA.items()
            if t == "float32" and c not in ("dt_minutes",)
        ]
        valid_mask1 = df1["sgp4_error"] == 0
        valid_mask2 = df2["sgp4_error"] == 0
        for col in numeric_cols:
            if col in df1.columns:
                pd.testing.assert_series_equal(
                    df1.loc[valid_mask1, col].reset_index(drop=True),
                    df2.loc[valid_mask2, col].reset_index(drop=True),
                    check_exact=False,
                    atol=1e-5,
                    check_names=False,
                )


# ---------------------------------------------------------------------------
# Test: Parquet output readable
# ---------------------------------------------------------------------------


class TestParquetOutput:

    def test_parquet_file_readable(self, fixture_output_paths):
        """Written Parquet file must be readable and match the fixture DataFrame."""
        parquet_path, _ = fixture_output_paths
        loaded = pd.read_parquet(parquet_path)
        assert len(loaded) > 0
        assert set(EXPECTED_COLUMNS) <= set(loaded.columns)

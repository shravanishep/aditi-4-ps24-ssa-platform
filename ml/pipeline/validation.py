"""
ml.pipeline.validation — Dataset quality validation for the Layer 7 pipeline.

This module runs a set of structural and semantic checks against the
completed feature DataFrame before it is written to Parquet.

Checks are either hard failures (raise DatasetValidationError) or
warnings emitted to stderr.  See check_dataset() for the full list.
"""

from __future__ import annotations

import sys
import warnings

import pandas as pd

from .feature_engineering import (
    EXPECTED_COLUMNS,
    PROPAGATED_FEATURE_COLUMNS,
    FEATURE_SCHEMA,
)

# Columns that must contain only the three allowed split labels
_VALID_SPLITS = {"train", "val", "test"}


class DatasetValidationError(ValueError):
    """Raised when the dataset fails a hard validation check."""


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_schema(df: pd.DataFrame) -> None:
    """Verify all expected columns are present."""
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise DatasetValidationError(
            f"Dataset is missing expected columns: {missing}"
        )


def _check_numeric_dtypes(df: pd.DataFrame) -> None:
    """Verify float32 columns contain numeric dtypes (not object)."""
    float_cols = [c for c, t in FEATURE_SCHEMA.items() if t == "float32"]
    bad = [c for c in float_cols if c in df.columns and not pd.api.types.is_float_dtype(df[c])]
    if bad:
        raise DatasetValidationError(
            f"The following columns should be float32 but have non-float dtype: {bad}"
        )


def _check_no_duplicates(df: pd.DataFrame) -> None:
    """Verify no duplicate (norad_cat_id, observation_utc) pairs exist."""
    dupes = df.duplicated(subset=["norad_cat_id", "observation_utc"])
    n_dupes = int(dupes.sum())
    if n_dupes > 0:
        raise DatasetValidationError(
            f"Dataset contains {n_dupes} duplicate (norad_cat_id, observation_utc) pairs."
        )


def _check_valid_rows_no_nan(df: pd.DataFrame) -> None:
    """Verify sgp4_error==0 rows have no NaN in propagated feature columns."""
    valid_mask = df["sgp4_error"] == 0
    valid_df = df.loc[valid_mask, PROPAGATED_FEATURE_COLUMNS]
    nan_counts = valid_df.isnull().sum()
    bad_cols = nan_counts[nan_counts > 0]
    if not bad_cols.empty:
        raise DatasetValidationError(
            f"sgp4_error==0 rows contain unexpected NaN in propagated columns: "
            f"{bad_cols.to_dict()}"
        )


def _check_error_rows_all_nan(df: pd.DataFrame) -> None:
    """Verify sgp4_error!=0 rows have NaN in all propagated feature columns."""
    error_mask = df["sgp4_error"] != 0
    error_df = df.loc[error_mask, PROPAGATED_FEATURE_COLUMNS]
    if len(error_df) == 0:
        return
    # All propagated feature values must be NaN on error rows
    not_nan = error_df.notna().any(axis=1)
    n_bad = int(not_nan.sum())
    if n_bad > 0:
        raise DatasetValidationError(
            f"{n_bad} sgp4_error!=0 rows have non-NaN propagated feature values."
        )


def _check_altitude_physical(df: pd.DataFrame) -> None:
    """Verify altitude_km > -R_earth for all valid rows (below Earth centre is impossible)."""
    valid_mask = (df["sgp4_error"] == 0) & df["altitude_km"].notna()
    # Below Earth's centre (> 6371 km below surface) is physically impossible
    impossible = df.loc[valid_mask, "altitude_km"] < -6371.0
    n_bad = int(impossible.sum())
    if n_bad > 0:
        raise DatasetValidationError(
            f"{n_bad} valid rows have altitude_km < -6371.0 (below Earth centre)."
        )


def _check_speed_positive(df: pd.DataFrame) -> None:
    """Verify speed_km_s > 0 for all valid rows."""
    valid_mask = (df["sgp4_error"] == 0) & df["speed_km_s"].notna()
    bad = df.loc[valid_mask, "speed_km_s"] <= 0.0
    n_bad = int(bad.sum())
    if n_bad > 0:
        raise DatasetValidationError(
            f"{n_bad} valid rows have speed_km_s <= 0."
        )


def _check_split_values(df: pd.DataFrame) -> None:
    """Verify the split column contains only 'train', 'val', 'test'."""
    unique_splits = set(df["split"].dropna().unique())
    invalid = unique_splits - _VALID_SPLITS
    if invalid:
        raise DatasetValidationError(
            f"split column contains invalid values: {invalid}"
        )


def _check_sgp4_error_pct(df: pd.DataFrame, max_pct: float) -> None:
    """Warn (not raise) when SGP4 error percentage exceeds the threshold."""
    n_total = len(df)
    if n_total == 0:
        return
    n_errors = int((df["sgp4_error"] != 0).sum())
    error_pct = 100.0 * n_errors / n_total
    if error_pct > max_pct:
        warnings.warn(
            f"SGP4 error rate is {error_pct:.2f}% ({n_errors}/{n_total} rows), "
            f"which exceeds the configured threshold of {max_pct:.1f}%. "
            "Review the GP data or consider removing degraded satellites.",
            UserWarning,
            stacklevel=3,
        )


def _check_t_offset_monotonic(df: pd.DataFrame) -> None:
    """Verify t_offset_minutes is non-decreasing within each satellite."""
    for norad_id, group in df.groupby("norad_cat_id", sort=False):
        offsets = group["t_offset_minutes"].values
        if not (offsets[1:] >= offsets[:-1]).all():
            raise DatasetValidationError(
                f"t_offset_minutes is not monotonically non-decreasing for "
                f"NORAD_CAT_ID {norad_id}."
            )


def _check_row_count(
    df: pd.DataFrame,
    expected_n_satellites: int,
    n_steps: int,
) -> None:
    """Warn when row count differs from expected n_satellites * n_steps."""
    expected_rows = expected_n_satellites * n_steps
    actual_rows = len(df)
    if actual_rows != expected_rows:
        warnings.warn(
            f"Expected {expected_rows} rows ({expected_n_satellites} satellites x "
            f"{n_steps} steps) but got {actual_rows}. "
            "Some satellites may have been skipped due to GP validation errors.",
            UserWarning,
            stacklevel=3,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check_dataset(
    df: pd.DataFrame,
    max_sgp4_error_pct: float = 5.0,
    expected_n_satellites: int | None = None,
    n_steps: int | None = None,
) -> None:
    """Run all validation checks against the complete feature dataset.

    Hard failures raise DatasetValidationError.
    Soft failures emit UserWarning to stderr.

    Parameters
    ----------
    df:
        The complete feature DataFrame to validate.
    max_sgp4_error_pct:
        Warning threshold for the proportion of SGP4 error rows (%).
    expected_n_satellites:
        Number of satellites that were attempted (for row count warning).
    n_steps:
        Expected observations per satellite (for row count warning).
    """
    _check_schema(df)
    _check_numeric_dtypes(df)
    _check_no_duplicates(df)
    _check_valid_rows_no_nan(df)
    _check_error_rows_all_nan(df)
    _check_altitude_physical(df)
    _check_speed_positive(df)
    _check_split_values(df)
    _check_t_offset_monotonic(df)
    _check_sgp4_error_pct(df, max_sgp4_error_pct)

    if expected_n_satellites is not None and n_steps is not None:
        _check_row_count(df, expected_n_satellites, n_steps)

"""
ml.pipeline.dataset_builder — Layer 7 orbital feature dataset builder.

This module orchestrates the full pipeline:

  1. Load GP orbital elements from the CelesTrak CSV.
  2. Select satellites (sorted by NORAD_CAT_ID, deterministic).
  3. For each satellite, propagate at N evenly-spaced timestamps centred
     on the GP epoch (24h window, 15-minute step -> 97 obs/satellite).
  4. Compute static, propagated, and temporal difference features.
  5. Assign per-satellite chronological train/val/test split labels.
  6. Run dataset validation.
  7. Write the ML-ready Parquet file and JSON metadata sidecar.

Usage
-----
As a module (from project root)::

    python -m ml.pipeline.dataset_builder \\
        --gp-csv data/raw/active_satellites_gp.csv \\
        --output data/processed/orbital_features.parquet \\
        --window-hours 24 \\
        --step-minutes 15 \\
        --max-satellites 200

Reproducibility
---------------
Given the same GP CSV file and the same PipelineConfig, this builder
produces a dataset with identical satellite selection, timestamps,
feature values, row ordering, and schema.  The metadata JSON includes a
SHA-256 hash of the GP CSV so the provenance of any dataset artefact can
be verified.

Note: Parquet file bytes may vary across pyarrow versions or platforms
due to internal encoding differences.  Reproducibility is guaranteed at
the DataFrame level (schema, values, row order), not at the byte level.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sgp4.conveniences import check_satrec

from backend.orbital.gp_loader import load_gp_data, parse_epoch
from backend.orbital.sgp4_propagator import propagate_orbit

from .config import PipelineConfig
from .feature_engineering import (
    EXPECTED_COLUMNS,
    FEATURE_SCHEMA,
    PROPAGATED_FEATURE_COLUMNS,
    add_temporal_diff_features,
    assign_split,
    compute_propagated_features,
    compute_static_features,
)
from .validation import check_dataset


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sha256_of_file(path: Path) -> str:
    """Return the hex SHA-256 digest of the given file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_timestamps(
    epoch: datetime,
    window_hours: float,
    step_minutes: float,
) -> list[tuple[float, datetime]]:
    """Generate (t_offset_minutes, utc_timestamp) pairs for one satellite.

    The window is centred on the GP epoch:
        t_start = epoch - window_hours/2
        t_end   = epoch + window_hours/2

    The centred window is a practical choice that limits the propagation
    distance from the element-set epoch, which reduces accumulation of
    SGP4 numerical error.  It does not imply a formal accuracy guarantee,
    as SGP4 accuracy depends on many factors beyond propagation interval.

    Parameters
    ----------
    epoch:
        The GP element set epoch (UTC, timezone-aware).
    window_hours:
        Total window length in hours.
    step_minutes:
        Sampling interval in minutes.

    Returns
    -------
    list of (t_offset_minutes, utc_datetime) tuples
    """
    half_window_minutes = window_hours * 30.0  # half window in minutes
    n_steps = int(window_hours * 60.0 / step_minutes) + 1
    result = []
    for step in range(n_steps):
        t_offset_min = step * step_minutes - half_window_minutes
        t = epoch + timedelta(minutes=t_offset_min)
        result.append((t_offset_min, t))
    return result


def _build_satellite_rows(
    gp_row: pd.Series,
    config: PipelineConfig,
) -> list[dict] | None:
    """Build all observation rows for one satellite.

    Returns None if the satellite should be skipped (e.g. check_satrec fails).
    Returns a list of row dicts (one per timestamp) otherwise.
    """
    norad_id = int(gp_row["NORAD_CAT_ID"])
    object_name = str(gp_row.get("OBJECT_NAME", "")).strip()

    # Parse the GP epoch
    try:
        epoch_dt = parse_epoch(gp_row["EPOCH"])
    except ValueError as exc:
        print(
            f"  [SKIP] NORAD {norad_id}: cannot parse epoch — {exc}",
            file=sys.stderr,
        )
        return None

    # Generate (t_offset_minutes, utc_datetime) pairs
    timestamps = _build_timestamps(
        epoch_dt,
        config.window_hours,
        config.step_minutes,
    )

    # Compute static features (same for every row of this satellite)
    try:
        static_feats = compute_static_features(gp_row)
    except Exception as exc:
        print(
            f"  [SKIP] NORAD {norad_id}: static feature computation failed — {exc}",
            file=sys.stderr,
        )
        return None

    rows = []
    for t_offset_min, t_utc in timestamps:
        # Propagate via Layer 1 (unmodified)
        state = propagate_orbit(gp_row, t_utc)

        # Compute propagated/derived features
        prop_feats = compute_propagated_features(state)

        row = {
            # Identity
            "norad_cat_id": norad_id,
            "object_name": object_name,
            "epoch_utc": epoch_dt,
            "observation_utc": t_utc,
            "t_offset_minutes": t_offset_min,
            "sgp4_error": state.sgp4_error,
            "sgp4_error_message": state.error_message,
            # Static features
            **static_feats,
            # Propagated + derived features
            **prop_feats,
        }
        rows.append(row)

    return rows


def _apply_schema_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Cast all columns to their defined storage types for Parquet output.

    Float32 downcasting happens here — not during orbital calculations.
    The intermediate DataFrame retains full float64 precision throughout
    the build process; this cast is the final step before writing.
    """
    df = df.copy()

    for col, dtype in FEATURE_SCHEMA.items():
        if col not in df.columns:
            continue

        if dtype == "int32":
            df[col] = df[col].astype("int32")
        elif dtype == "int8":
            df[col] = df[col].astype("int8")
        elif dtype == "float32":
            df[col] = df[col].astype("float32")
        elif dtype == "string":
            df[col] = df[col].astype(pd.StringDtype())
        elif dtype == "datetime64[ns, UTC]":
            if not isinstance(df[col].dtype, pd.DatetimeTZDtype):
                df[col] = pd.to_datetime(df[col], utc=True)
            elif str(df[col].dtype) != "datetime64[ns, UTC]":
                df[col] = df[col].dt.tz_convert("UTC")

    return df


def build_dataset(config: PipelineConfig) -> pd.DataFrame:
    """Run the full feature engineering pipeline and return the feature DataFrame.

    This is the main entry point for programmatic use (e.g., in tests).
    For CLI use, call main() instead.

    Parameters
    ----------
    config:
        PipelineConfig instance controlling all pipeline parameters.

    Returns
    -------
    pd.DataFrame
        The complete ML-ready feature DataFrame (not yet written to disk).
    """
    gp_csv_path = Path(config.gp_csv_path)

    # -------------------------------------------------------------------------
    # 1. Load GP data
    # -------------------------------------------------------------------------
    print(f"[Layer 7] Loading GP data from: {gp_csv_path}")
    gp_df = load_gp_data(gp_csv_path)

    # Sort by NORAD_CAT_ID for deterministic satellite selection
    gp_df = gp_df.sort_values("NORAD_CAT_ID").reset_index(drop=True)

    # Apply max_satellites cap
    if config.max_satellites is not None:
        gp_df = gp_df.head(config.max_satellites)

    n_attempted = len(gp_df)
    n_steps = config.n_steps()
    print(
        f"[Layer 7] Satellites: {n_attempted} | "
        f"Steps/satellite: {n_steps} | "
        f"Window: {config.window_hours}h | Step: {config.step_minutes}min"
    )

    # -------------------------------------------------------------------------
    # 2. Build rows for each satellite
    # -------------------------------------------------------------------------
    all_rows: list[dict] = []
    n_skipped = 0

    for idx, (_, gp_row) in enumerate(gp_df.iterrows()):
        norad_id = int(gp_row["NORAD_CAT_ID"])
        if (idx + 1) % 50 == 0 or (idx + 1) == n_attempted:
            print(f"  Processed {idx + 1}/{n_attempted} satellites ...", flush=True)

        sat_rows = _build_satellite_rows(gp_row, config)
        if sat_rows is None:
            n_skipped += 1
            continue
        all_rows.extend(sat_rows)

    n_satellites_built = n_attempted - n_skipped
    print(
        f"[Layer 7] Built {len(all_rows)} rows from {n_satellites_built} satellites "
        f"({n_skipped} skipped)."
    )

    if not all_rows:
        raise RuntimeError("No rows were produced. Check the GP data and configuration.")

    # -------------------------------------------------------------------------
    # 3. Assemble DataFrame
    # -------------------------------------------------------------------------
    df = pd.DataFrame(all_rows)

    # Ensure column order matches EXPECTED_COLUMNS (temporal diff columns not yet present)
    # Temporal diff features are added per-satellite next.

    # -------------------------------------------------------------------------
    # 4. Add temporal difference features per satellite and assign split
    # -------------------------------------------------------------------------
    satellite_dfs: list[pd.DataFrame] = []

    for norad_id, sat_df in df.groupby("norad_cat_id", sort=True):
        # Sort by t_offset_minutes (should already be sorted, but ensure it)
        sat_df = sat_df.sort_values("t_offset_minutes").reset_index(drop=True)

        # Add temporal difference features
        sat_df = add_temporal_diff_features(sat_df)

        # Assign chronological train/val/test split
        sat_df = assign_split(sat_df, config.train_frac, config.val_frac)

        satellite_dfs.append(sat_df)

    df = pd.concat(satellite_dfs, ignore_index=True)

    # -------------------------------------------------------------------------
    # 5. Enforce column order and apply storage dtypes
    # -------------------------------------------------------------------------
    # Reorder columns to match schema
    df = df[EXPECTED_COLUMNS]

    # Apply float32 and other storage type casts (only at this final step)
    df = _apply_schema_dtypes(df)

    # -------------------------------------------------------------------------
    # 6. Validate
    # -------------------------------------------------------------------------
    print("[Layer 7] Running dataset validation ...")
    check_dataset(
        df,
        max_sgp4_error_pct=config.max_sgp4_error_pct,
        expected_n_satellites=n_satellites_built,
        n_steps=n_steps,
    )
    print("[Layer 7] Validation passed.")

    return df


def write_outputs(
    df: pd.DataFrame,
    config: PipelineConfig,
    gp_csv_path: Path,
    build_start_utc: datetime,
) -> None:
    """Write the feature DataFrame to Parquet and emit the metadata JSON sidecar.

    Parameters
    ----------
    df:
        The validated feature DataFrame.
    config:
        Pipeline configuration (embedded verbatim in metadata).
    gp_csv_path:
        Resolved path to the GP CSV (for hash computation).
    build_start_utc:
        UTC datetime when the build started (for metadata provenance).
    """
    parquet_path = Path(config.output_parquet_path)
    metadata_path = Path(config.output_metadata_path)

    # Create output directory if needed
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- Write Parquet ----
    df.to_parquet(parquet_path, engine="pyarrow", index=False)
    print(f"[Layer 7] Parquet written: {parquet_path} ({parquet_path.stat().st_size / 1024:.1f} KB)")

    # ---- Compute summary statistics ----
    n_total = len(df)
    n_errors = int((df["sgp4_error"] != 0).sum())
    unique_norads = int(df["norad_cat_id"].nunique())
    split_counts = df["split"].value_counts().to_dict()

    # ---- Build metadata ----
    gp_sha256 = _sha256_of_file(gp_csv_path)

    metadata = {
        "build_info": {
            "build_start_utc": build_start_utc.isoformat(),
            "build_end_utc": datetime.now(tz=timezone.utc).isoformat(),
            "layer": "Layer 7 — ML Feature Engineering and Dataset Pipeline",
            "platform": "ADITI 4.0 PS24 SSA Platform",
        },
        "input": {
            "gp_csv_path": str(gp_csv_path.resolve()),
            "gp_csv_sha256": gp_sha256,
            "gp_csv_size_bytes": gp_csv_path.stat().st_size,
        },
        "config": config.to_dict(),
        "output": {
            "parquet_path": str(parquet_path.resolve()),
            "total_rows": n_total,
            "unique_satellites": unique_norads,
            "n_columns": len(df.columns),
            "sgp4_error_rows": n_errors,
            "sgp4_error_pct": round(100.0 * n_errors / n_total, 4) if n_total > 0 else 0.0,
            "split_counts": {k: int(v) for k, v in split_counts.items()},
        },
        "schema": {
            col: dtype for col, dtype in FEATURE_SCHEMA.items()
        },
        "summary_statistics": {
            col: {
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "mean": float(df[col].mean()),
                "null_count": int(df[col].isnull().sum()),
            }
            for col in [
                "altitude_km",
                "orbital_radius_km",
                "speed_km_s",
                "inclination_deg",
                "eccentricity",
                "perigee_km",
                "apogee_km",
            ]
            if col in df.columns
        },
        "notes": [
            "Temporal difference features (d_*) are fixed-interval absolute differences.",
            "They are NOT rates-per-unit-time. Divide by dt_minutes to obtain rates.",
            "The first observation of each satellite has NaN for all d_* and dt_minutes.",
            "SGP4 error rows retain NaN for all propagated and derived features.",
            "The 24-hour window centred on each GP epoch is a practical choice to limit "
            "propagation distance from the element-set epoch; it does not imply a universal "
            "SGP4 accuracy guarantee.",
            "Data leakage prevention is achieved by per-satellite chronological "
            "train/val/test splitting (no shuffling) and backward-only finite differences.",
            "No synthetic anomalies are present in this dataset. All data is from SGP4 "
            "propagation of public CelesTrak GP orbital elements.",
        ],
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"[Layer 7] Metadata written: {metadata_path}")


def main(args: list[str] | None = None) -> None:
    """CLI entry point for the dataset builder."""
    parser = argparse.ArgumentParser(
        description="Build the Layer 7 ML-ready orbital feature dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--gp-csv",
        default="data/raw/active_satellites_gp.csv",
        help="Path to the CelesTrak GP CSV file.",
    )
    parser.add_argument(
        "--output",
        default="data/processed/orbital_features.parquet",
        help="Destination path for the output Parquet file.",
    )
    parser.add_argument(
        "--metadata",
        default="data/processed/orbital_features_metadata.json",
        help="Destination path for the metadata JSON sidecar.",
    )
    parser.add_argument(
        "--window-hours",
        type=float,
        default=24.0,
        help="Total propagation window length in hours (centred on GP epoch).",
    )
    parser.add_argument(
        "--step-minutes",
        type=float,
        default=15.0,
        help="Sampling interval in minutes.",
    )
    parser.add_argument(
        "--max-satellites",
        type=int,
        default=200,
        help="Maximum satellites to process (sorted by NORAD ID). 0 = all.",
    )
    parser.add_argument(
        "--max-error-pct",
        type=float,
        default=5.0,
        help="SGP4 error percentage warning threshold.",
    )

    parsed = parser.parse_args(args)

    max_sats = parsed.max_satellites if parsed.max_satellites > 0 else None

    config = PipelineConfig(
        gp_csv_path=parsed.gp_csv,
        output_parquet_path=parsed.output,
        output_metadata_path=parsed.metadata,
        window_hours=parsed.window_hours,
        step_minutes=parsed.step_minutes,
        max_satellites=max_sats,
        max_sgp4_error_pct=parsed.max_error_pct,
    )

    build_start = datetime.now(tz=timezone.utc)

    # Run build
    df = build_dataset(config)

    # Write outputs
    write_outputs(df, config, Path(config.gp_csv_path), build_start)

    # Print summary
    n_errors = int((df["sgp4_error"] != 0).sum())
    print(
        f"\n[Layer 7] Done.\n"
        f"  Rows        : {len(df)}\n"
        f"  Columns     : {len(df.columns)}\n"
        f"  Satellites  : {df['norad_cat_id'].nunique()}\n"
        f"  SGP4 errors : {n_errors} ({100.0 * n_errors / len(df):.2f}%)\n"
        f"  Output      : {config.output_parquet_path}\n"
        f"  Metadata    : {config.output_metadata_path}"
    )


if __name__ == "__main__":
    main()

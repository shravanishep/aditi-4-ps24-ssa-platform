"""
ml.pipeline.dataset_builder_v2 — Expanded orbital feature dataset builder (v2).

This module supersedes the v1 builder for ML improvement experiments.
It adds:
  1. Stratified regime-diverse satellite selection (LEO/MEO/GEO/HEO).
  2. Two evaluation strategies:
       A. Chronological: per-satellite train/val/test by time offset.
       B. Unseen-satellite: satellite-level train/holdout split for
          generalization evaluation on satellites never seen during training.
  3. Versioned output paths that do NOT overwrite v1 artefacts.
  4. Richer metadata including per-regime counts, satellite ID lists,
     and data-leakage prevention notes.

CLI usage (from project root)
------------------------------
    python -m ml.pipeline.dataset_builder_v2 \\
        --max-leo 150 \\
        --max-meo 20 \\
        --max-geo 20 \\
        --max-heo 10 \\
        --window-hours 24 \\
        --step-minutes 15

Outputs (versioned, do not overwrite v1)
-----------------------------------------
    data/processed/orbital_features_v2.parquet
    data/processed/orbital_features_v2_metadata.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
from .regime_sampler import RegimeSamplerConfig, select_regime_diverse_satellites
from .validation import check_dataset


# ---------------------------------------------------------------------------
# Versioned output paths (do NOT shadow v1)
# ---------------------------------------------------------------------------
_DEFAULT_OUTPUT_PARQUET = "data/processed/orbital_features_v2.parquet"
_DEFAULT_OUTPUT_METADATA = "data/processed/orbital_features_v2_metadata.json"


# ---------------------------------------------------------------------------
# Internal helpers (identical logic to v1 builder)
# ---------------------------------------------------------------------------

def _sha256_of_file(path: Path) -> str:
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
    half_window_minutes = window_hours * 30.0
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
    """Build all observation rows for one satellite. Returns None if satellite should be skipped."""
    norad_id = int(gp_row["NORAD_CAT_ID"])
    object_name = str(gp_row.get("OBJECT_NAME", "")).strip()

    try:
        epoch_dt = parse_epoch(gp_row["EPOCH"])
    except ValueError as exc:
        print(f"  [SKIP] NORAD {norad_id}: cannot parse epoch — {exc}", file=sys.stderr)
        return None

    timestamps = _build_timestamps(epoch_dt, config.window_hours, config.step_minutes)

    try:
        static_feats = compute_static_features(gp_row)
    except Exception as exc:
        print(f"  [SKIP] NORAD {norad_id}: static feature computation failed — {exc}", file=sys.stderr)
        return None

    rows = []
    for t_offset_min, t_utc in timestamps:
        state = propagate_orbit(gp_row, t_utc)
        prop_feats = compute_propagated_features(state)

        row = {
            "norad_cat_id": norad_id,
            "object_name": object_name,
            "epoch_utc": epoch_dt,
            "observation_utc": t_utc,
            "t_offset_minutes": t_offset_min,
            "sgp4_error": state.sgp4_error,
            "sgp4_error_message": state.error_message,
            **static_feats,
            **prop_feats,
        }
        rows.append(row)

    return rows


def _apply_schema_dtypes(df: pd.DataFrame) -> pd.DataFrame:
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


# ---------------------------------------------------------------------------
# Unseen-satellite split assignment
# ---------------------------------------------------------------------------

def assign_satellite_holdout_split(
    df: pd.DataFrame,
    holdout_fraction: float = 0.20,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Add a 'sat_split' column: 'train_sats' or 'holdout_sats'.

    Satellites are randomly assigned at the satellite level (all observations
    of a satellite go together) so that the holdout set contains satellites
    never seen during training.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset with 'norad_cat_id' column.
    holdout_fraction : float
        Fraction of unique satellites to hold out for generalization eval.
    random_seed : int
        Fixed seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Input DataFrame with 'sat_split' column added.
    """
    rng = np.random.default_rng(random_seed)
    unique_ids = sorted(df["norad_cat_id"].unique())
    n_holdout = max(1, int(len(unique_ids) * holdout_fraction))

    holdout_ids = set(rng.choice(unique_ids, size=n_holdout, replace=False).tolist())
    train_ids = set(unique_ids) - holdout_ids

    df = df.copy()
    df["sat_split"] = df["norad_cat_id"].apply(
        lambda nid: "holdout_sats" if nid in holdout_ids else "train_sats"
    )
    return df, sorted(train_ids), sorted(holdout_ids)


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_dataset_v2(
    gp_csv_path: str | Path = "data/raw/active_satellites_gp.csv",
    output_parquet_path: str | Path = _DEFAULT_OUTPUT_PARQUET,
    output_metadata_path: str | Path = _DEFAULT_OUTPUT_METADATA,
    regime_config: RegimeSamplerConfig | None = None,
    pipeline_config: PipelineConfig | None = None,
    holdout_fraction: float = 0.20,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Build the v2 expanded orbital feature dataset with regime diversity.

    Parameters
    ----------
    gp_csv_path : path
        Path to CelesTrak GP CSV.
    output_parquet_path : path
        Output Parquet path (versioned, does NOT overwrite v1).
    output_metadata_path : path
        Output metadata JSON path (versioned).
    regime_config : RegimeSamplerConfig | None
        Per-regime satellite quotas.
    pipeline_config : PipelineConfig | None
        Propagation window/step configuration. max_satellites is ignored
        (regime_config controls selection).
    holdout_fraction : float
        Fraction of satellites to hold out for unseen-satellite evaluation.
    verbose : bool
        Print progress.

    Returns
    -------
    pd.DataFrame
        The complete v2 feature DataFrame (also written to disk).
    """
    build_start_utc = datetime.now(timezone.utc)
    gp_csv_path = Path(gp_csv_path)
    output_parquet_path = Path(output_parquet_path)
    output_metadata_path = Path(output_metadata_path)

    # Safety: refuse to overwrite v1 artefacts
    _V1_PARQUET = Path("data/processed/orbital_features.parquet")
    if output_parquet_path.resolve() == _V1_PARQUET.resolve():
        raise RuntimeError(
            "Refusing to overwrite v1 artefact. Use a versioned output path."
        )

    rcfg = regime_config or RegimeSamplerConfig()
    pcfg = pipeline_config or PipelineConfig()

    # -------------------------------------------------------------------------
    # 1. Load and classify GP data
    # -------------------------------------------------------------------------
    if verbose:
        print(f"[v2 Builder] Loading GP data from: {gp_csv_path}", flush=True)
    gp_df = load_gp_data(gp_csv_path)

    if verbose:
        print(f"[v2 Builder] Total satellites in GP CSV: {len(gp_df)}", flush=True)

    # -------------------------------------------------------------------------
    # 2. Stratified regime-diverse selection
    # -------------------------------------------------------------------------
    if verbose:
        print("[v2 Builder] Selecting regime-diverse satellite subset...", flush=True)
    selected_df, regime_report = select_regime_diverse_satellites(gp_df, rcfg, verbose=verbose)
    n_attempted = len(selected_df)
    n_steps = pcfg.n_steps()

    if verbose:
        print(
            f"[v2 Builder] Building dataset: {n_attempted} satellites × "
            f"{n_steps} steps = ~{n_attempted * n_steps} rows",
            flush=True,
        )

    # -------------------------------------------------------------------------
    # 3. Build rows for each satellite
    # -------------------------------------------------------------------------
    all_rows: list[dict] = []
    n_skipped = 0
    regime_lookup = dict(zip(selected_df["NORAD_CAT_ID"], selected_df["regime"]))

    for idx, (_, gp_row) in enumerate(selected_df.iterrows()):
        norad_id = int(gp_row["NORAD_CAT_ID"])
        if verbose and ((idx + 1) % 50 == 0 or (idx + 1) == n_attempted):
            print(f"  Processed {idx + 1}/{n_attempted} satellites ...", flush=True)

        sat_rows = _build_satellite_rows(gp_row, pcfg)
        if sat_rows is None:
            n_skipped += 1
            continue

        # Annotate each row with regime label
        regime_label = regime_lookup.get(norad_id, "UNKNOWN")
        for row in sat_rows:
            row["regime"] = regime_label

        all_rows.extend(sat_rows)

    n_satellites_built = n_attempted - n_skipped
    if verbose:
        print(
            f"[v2 Builder] Built {len(all_rows)} rows from {n_satellites_built} satellites "
            f"({n_skipped} skipped due to epoch/SGP4 errors).",
            flush=True,
        )

    if not all_rows:
        raise RuntimeError("No rows produced. Check GP data and configuration.")

    # -------------------------------------------------------------------------
    # 4. Assemble DataFrame
    # -------------------------------------------------------------------------
    df = pd.DataFrame(all_rows)

    # -------------------------------------------------------------------------
    # 5. Per-satellite temporal diff + chronological split
    # -------------------------------------------------------------------------
    satellite_dfs: list[pd.DataFrame] = []
    for norad_id, sat_df in df.groupby("norad_cat_id", sort=True):
        sat_df = sat_df.sort_values("t_offset_minutes").reset_index(drop=True)
        sat_df = add_temporal_diff_features(sat_df)
        sat_df = assign_split(sat_df, pcfg.train_frac, pcfg.val_frac)
        satellite_dfs.append(sat_df)
    df = pd.concat(satellite_dfs, ignore_index=True)

    # -------------------------------------------------------------------------
    # 6. Add unseen-satellite split column
    # -------------------------------------------------------------------------
    df, train_sat_ids, holdout_sat_ids = assign_satellite_holdout_split(
        df, holdout_fraction=holdout_fraction, random_seed=42
    )

    # -------------------------------------------------------------------------
    # 7. Reorder to expected schema + add regime column, enforce dtypes
    # -------------------------------------------------------------------------
    # Build final column order: EXPECTED_COLUMNS + extra v2 columns
    base_cols = EXPECTED_COLUMNS  # 40 original columns
    extra_cols = [c for c in ["regime", "sat_split"] if c in df.columns]
    final_cols = base_cols + extra_cols
    # Ensure all expected columns exist
    missing_base = [c for c in base_cols if c not in df.columns]
    if missing_base:
        raise RuntimeError(f"Missing base columns: {missing_base}")
    df = df[final_cols]
    df = _apply_schema_dtypes(df)

    # -------------------------------------------------------------------------
    # 8. Validation (using existing check_dataset on base columns)
    # -------------------------------------------------------------------------
    if verbose:
        print("[v2 Builder] Running validation...", flush=True)
    check_dataset(
        df,
        max_sgp4_error_pct=pcfg.max_sgp4_error_pct,
        expected_n_satellites=n_satellites_built,
        n_steps=n_steps,
    )
    if verbose:
        print("[v2 Builder] Validation passed.", flush=True)

    # -------------------------------------------------------------------------
    # 9. Write Parquet
    # -------------------------------------------------------------------------
    output_parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_parquet_path, index=False)
    if verbose:
        print(f"[v2 Builder] Wrote Parquet: {output_parquet_path} ({len(df)} rows)", flush=True)

    # -------------------------------------------------------------------------
    # 10. Build and write metadata JSON
    # -------------------------------------------------------------------------
    build_end_utc = datetime.now(timezone.utc)
    gp_csv_sha256 = _sha256_of_file(gp_csv_path)

    # Per-regime satellite counts achieved
    regime_actual_counts = df.drop_duplicates("norad_cat_id").groupby("regime").size().to_dict()

    metadata = {
        "schema_version": "v2",
        "build_info": {
            "build_start_utc": build_start_utc.isoformat(),
            "build_end_utc": build_end_utc.isoformat(),
            "duration_seconds": round((build_end_utc - build_start_utc).total_seconds(), 1),
            "layer": "Layer 7 v2 — Expanded Regime-Diverse Dataset",
            "platform": "ADITI 4.0 PS24 SSA Platform",
        },
        "input": {
            "gp_csv_path": str(gp_csv_path),
            "gp_csv_sha256": gp_csv_sha256,
            "total_satellites_in_csv": len(gp_df),
        },
        "regime_sampler_config": {
            "leo_count": rcfg.leo_count,
            "meo_count": rcfg.meo_count,
            "geo_count": rcfg.geo_count,
            "heo_count": rcfg.heo_count,
            "total_target": rcfg.total_target,
        },
        "regime_selection_report": regime_report,
        "regime_actual_counts": regime_actual_counts,
        "pipeline_config": {
            "window_hours": pcfg.window_hours,
            "step_minutes": pcfg.step_minutes,
            "n_steps_per_satellite": n_steps,
            "train_frac": pcfg.train_frac,
            "val_frac": pcfg.val_frac,
            "test_frac": round(1.0 - pcfg.train_frac - pcfg.val_frac, 6),
            "max_sgp4_error_pct": pcfg.max_sgp4_error_pct,
        },
        "output": {
            "parquet_path": str(output_parquet_path),
            "total_rows": len(df),
            "unique_satellites": n_satellites_built,
            "n_columns": len(df.columns),
            "sgp4_error_rows": int((df["sgp4_error"] != 0).sum()),
            "sgp4_error_pct": round(100.0 * (df["sgp4_error"] != 0).sum() / len(df), 3),
            "split_counts": {
                "train": int((df["split"] == "train").sum()),
                "val": int((df["split"] == "val").sum()),
                "test": int((df["split"] == "test").sum()),
            },
            "satellite_holdout_split": {
                "holdout_fraction": holdout_fraction,
                "train_sat_count": len(train_sat_ids),
                "holdout_sat_count": len(holdout_sat_ids),
                "train_sat_ids": train_sat_ids[:50],  # First 50 to keep JSON readable
                "holdout_sat_ids": holdout_sat_ids,
            },
            "n_skipped_satellites": n_skipped,
        },
        "data_leakage_prevention": [
            "Per-satellite chronological split: observations sorted by t_offset_minutes within each satellite.",
            "No shuffling applied. Train observations are always earlier than val, val earlier than test.",
            "Temporal difference features (d_*) use backward-only finite differences: current minus previous.",
            "Unseen-satellite holdout assigns entire satellites to holdout; model never sees any observation from holdout satellites during training.",
        ],
        "v1_comparison": {
            "v1_satellites": 10,
            "v1_rows": 970,
            "v2_satellites": n_satellites_built,
            "v2_rows": len(df),
        },
    }

    output_metadata_path.parent.mkdir(parents=True, exist_ok=True)

    class _NumpyEncoder(json.JSONEncoder):
        """Serialise numpy scalar types that the standard encoder rejects."""
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    with open(output_metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, cls=_NumpyEncoder)
    if verbose:
        print(f"[v2 Builder] Wrote metadata: {output_metadata_path}", flush=True)

    return df


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build v2 expanded regime-diverse orbital feature dataset."
    )
    parser.add_argument("--gp-csv", default="data/raw/active_satellites_gp.csv")
    parser.add_argument("--output", default=_DEFAULT_OUTPUT_PARQUET)
    parser.add_argument("--metadata", default=_DEFAULT_OUTPUT_METADATA)
    parser.add_argument("--max-leo", type=int, default=150)
    parser.add_argument("--max-meo", type=int, default=20)
    parser.add_argument("--max-geo", type=int, default=20)
    parser.add_argument("--max-heo", type=int, default=10)
    parser.add_argument("--window-hours", type=float, default=24.0)
    parser.add_argument("--step-minutes", type=float, default=15.0)
    parser.add_argument("--holdout-fraction", type=float, default=0.20)
    args = parser.parse_args()

    rcfg = RegimeSamplerConfig(
        leo_count=args.max_leo,
        meo_count=args.max_meo,
        geo_count=args.max_geo,
        heo_count=args.max_heo,
    )
    pcfg = PipelineConfig(
        gp_csv_path=args.gp_csv,
        output_parquet_path=args.output,
        output_metadata_path=args.metadata,
        window_hours=args.window_hours,
        step_minutes=args.step_minutes,
    )

    build_dataset_v2(
        gp_csv_path=args.gp_csv,
        output_parquet_path=args.output,
        output_metadata_path=args.metadata,
        regime_config=rcfg,
        pipeline_config=pcfg,
        holdout_fraction=args.holdout_fraction,
        verbose=True,
    )
    print("[v2 Builder] Done.", flush=True)


if __name__ == "__main__":
    main()

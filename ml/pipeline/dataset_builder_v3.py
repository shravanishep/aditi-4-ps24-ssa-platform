"""
ml.pipeline.dataset_builder_v3 — High-volume regime-diverse orbital feature dataset builder (v3).

Builds the expanded Layer 7 v3 dataset by:
1. Ingesting from the expanded CelesTrak raw catalogue (data/raw/satellites_gp_v3.csv, 17,624 records).
2. Sampling a large, balanced regime-diverse subset (target: 350 satellites: 250 LEO, 40 MEO, 45 GEO, 15 HEO).
3. Propagating 24-hour orbital trajectories at 15-minute intervals (97 steps per satellite).
4. Extracting all 40 Layer 7 dynamic, static, and temporal difference features.
5. Establishing a deterministic 20% unseen-satellite holdout split (70 holdout satellites, 280 train satellites).
6. Preserving all v1 and v2 artifacts; writing strictly to v3 paths:
   - data/processed/orbital_features_v3.parquet
   - data/processed/orbital_features_v3_metadata.json
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

from backend.orbital.gp_loader import load_gp_data, parse_epoch
from backend.orbital.sgp4_propagator import propagate_orbit

from ml.pipeline.config import PipelineConfig
from ml.pipeline.feature_engineering import (
    EXPECTED_COLUMNS,
    FEATURE_SCHEMA,
    add_temporal_diff_features,
    assign_split,
    compute_propagated_features,
    compute_static_features,
)
from ml.pipeline.regime_sampler import RegimeSamplerConfig, select_regime_diverse_satellites
from ml.pipeline.validation import check_dataset

_DEFAULT_INPUT_CSV = "data/raw/satellites_gp_v3.csv"
_DEFAULT_OUTPUT_PARQUET = "data/processed/orbital_features_v3.parquet"
_DEFAULT_OUTPUT_METADATA = "data/processed/orbital_features_v3_metadata.json"


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
    norad_id = int(gp_row["NORAD_CAT_ID"])
    object_name = str(gp_row.get("OBJECT_NAME", "")).strip()

    try:
        epoch_dt = parse_epoch(gp_row["EPOCH"])
    except ValueError as exc:
        print(f"  [SKIP] NORAD {norad_id}: invalid epoch — {exc}", file=sys.stderr)
        return None

    timestamps = _build_timestamps(epoch_dt, config.window_hours, config.step_minutes)

    try:
        static_feats = compute_static_features(gp_row)
    except Exception as exc:
        print(f"  [SKIP] NORAD {norad_id}: static features failed — {exc}", file=sys.stderr)
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


def assign_satellite_holdout_split(
    df: pd.DataFrame,
    holdout_fraction: float = 0.20,
    random_seed: int = 42,
) -> tuple[pd.DataFrame, list[int], list[int]]:
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


def build_dataset_v3(
    gp_csv_path: str | Path = _DEFAULT_INPUT_CSV,
    output_parquet_path: str | Path = _DEFAULT_OUTPUT_PARQUET,
    output_metadata_path: str | Path = _DEFAULT_OUTPUT_METADATA,
    max_leo: int = 250,
    max_meo: int = 40,
    max_geo: int = 45,
    max_heo: int = 15,
    window_hours: float = 24.0,
    step_minutes: float = 15.0,
    holdout_fraction: float = 0.20,
    verbose: bool = True,
) -> pd.DataFrame:
    """Build the high-volume Layer 7 v3 dataset."""
    build_start_utc = datetime.now(timezone.utc)
    gp_csv_path = Path(gp_csv_path)
    output_parquet_path = Path(output_parquet_path)
    output_metadata_path = Path(output_metadata_path)

    # Protect existing artifacts
    for protected in ["data/processed/orbital_features.parquet", "data/processed/orbital_features_v2.parquet"]:
        if output_parquet_path.resolve() == Path(protected).resolve():
            raise RuntimeError(f"Refusing to overwrite protected artifact: {protected}")

    rcfg = RegimeSamplerConfig(
        leo_count=max_leo,
        meo_count=max_meo,
        geo_count=max_geo,
        heo_count=max_heo,
    )
    pcfg = PipelineConfig(
        gp_csv_path=str(gp_csv_path),
        output_parquet_path=str(output_parquet_path),
        output_metadata_path=str(output_metadata_path),
        window_hours=window_hours,
        step_minutes=step_minutes,
    )

    if verbose:
        print(f"[v3 Builder] Loading GP data from: {gp_csv_path}", flush=True)
    gp_df = load_gp_data(gp_csv_path)

    if verbose:
        print(f"[v3 Builder] Total satellites in input GP CSV: {len(gp_df)}", flush=True)
        print(f"[v3 Builder] Sampling target: {rcfg.total_target} satellites across regimes...", flush=True)

    selected_df, regime_report = select_regime_diverse_satellites(gp_df, rcfg, verbose=verbose)
    n_attempted = len(selected_df)
    n_steps = pcfg.n_steps()

    if verbose:
        print(f"[v3 Builder] Propagating {n_attempted} satellites × {n_steps} steps = ~{n_attempted * n_steps} rows...", flush=True)

    all_rows: list[dict] = []
    n_skipped = 0
    regime_lookup = dict(zip(selected_df["NORAD_CAT_ID"], selected_df["regime"]))

    for idx, (_, gp_row) in enumerate(selected_df.iterrows()):
        norad_id = int(gp_row["NORAD_CAT_ID"])
        if verbose and ((idx + 1) % 50 == 0 or (idx + 1) == n_attempted):
            print(f"  Propagated {idx + 1}/{n_attempted} satellites...", flush=True)

        sat_rows = _build_satellite_rows(gp_row, pcfg)
        if sat_rows is None:
            n_skipped += 1
            continue

        regime_label = regime_lookup.get(norad_id, "UNKNOWN")
        for row in sat_rows:
            row["regime"] = regime_label

        all_rows.extend(sat_rows)

    n_satellites_built = n_attempted - n_skipped
    if verbose:
        print(f"[v3 Builder] Built {len(all_rows)} rows from {n_satellites_built} satellites ({n_skipped} skipped).", flush=True)

    if not all_rows:
        raise RuntimeError("No rows produced.")

    df = pd.DataFrame(all_rows)

    # Per-satellite temporal diff + chronological split
    satellite_dfs: list[pd.DataFrame] = []
    for norad_id, sat_df in df.groupby("norad_cat_id", sort=True):
        sat_df = sat_df.sort_values("t_offset_minutes").reset_index(drop=True)
        sat_df = add_temporal_diff_features(sat_df)
        sat_df = assign_split(sat_df, pcfg.train_frac, pcfg.val_frac)
        satellite_dfs.append(sat_df)
    df = pd.concat(satellite_dfs, ignore_index=True)

    # Unseen satellite holdout split
    df, train_sat_ids, holdout_sat_ids = assign_satellite_holdout_split(
        df, holdout_fraction=holdout_fraction, random_seed=42
    )

    # Columns order and dtypes
    base_cols = EXPECTED_COLUMNS
    extra_cols = [c for c in ["regime", "sat_split"] if c in df.columns]
    final_cols = base_cols + extra_cols
    df = df[final_cols]
    df = _apply_schema_dtypes(df)

    # Validation
    if verbose:
        print("[v3 Builder] Running validation...", flush=True)
    check_dataset(
        df,
        max_sgp4_error_pct=pcfg.max_sgp4_error_pct,
        expected_n_satellites=n_satellites_built,
        n_steps=n_steps,
    )
    if verbose:
        print("[v3 Builder] Validation passed.", flush=True)

    # Save parquet
    output_parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_parquet_path, index=False)
    if verbose:
        print(f"[v3 Builder] Wrote Parquet: {output_parquet_path} ({len(df)} rows)", flush=True)

    # Save metadata JSON
    build_end_utc = datetime.now(timezone.utc)
    regime_actual_counts = df.drop_duplicates("norad_cat_id").groupby("regime").size().to_dict()

    metadata = {
        "schema_version": "v3",
        "build_info": {
            "build_start_utc": build_start_utc.isoformat(),
            "build_end_utc": build_end_utc.isoformat(),
            "duration_seconds": round((build_end_utc - build_start_utc).total_seconds(), 1),
            "layer": "Layer 7 v3 — Expanded High-Volume Regime-Diverse Dataset",
            "platform": "ADITI 4.0 PS24 SSA Platform",
        },
        "input": {
            "gp_csv_path": str(gp_csv_path),
            "gp_csv_sha256": _sha256_of_file(gp_csv_path),
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
                "train_sat_ids": train_sat_ids[:50],
                "holdout_sat_ids": holdout_sat_ids,
            },
            "n_skipped_satellites": n_skipped,
        },
        "v1_v2_comparison": {
            "v1_satellites": 10,
            "v1_rows": 970,
            "v2_satellites": 200,
            "v2_rows": 19400,
            "v3_satellites": n_satellites_built,
            "v3_rows": len(df),
        },
    }

    output_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, cls=_NumpyEncoder)

    if verbose:
        print(f"[v3 Builder] Wrote metadata: {output_metadata_path}", flush=True)

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Build v3 expanded orbital feature dataset.")
    parser.add_argument("--gp-csv", default=_DEFAULT_INPUT_CSV)
    parser.add_argument("--output", default=_DEFAULT_OUTPUT_PARQUET)
    parser.add_argument("--metadata", default=_DEFAULT_OUTPUT_METADATA)
    parser.add_argument("--max-leo", type=int, default=250)
    parser.add_argument("--max-meo", type=int, default=40)
    parser.add_argument("--max-geo", type=int, default=45)
    parser.add_argument("--max-heo", type=int, default=15)
    parser.add_argument("--window-hours", type=float, default=24.0)
    parser.add_argument("--step-minutes", type=float, default=15.0)
    args = parser.parse_args()

    build_dataset_v3(
        gp_csv_path=args.gp_csv,
        output_parquet_path=args.output,
        output_metadata_path=args.metadata,
        max_leo=args.max_leo,
        max_meo=args.max_meo,
        max_geo=args.max_geo,
        max_heo=args.max_heo,
        window_hours=args.window_hours,
        step_minutes=args.step_minutes,
    )
    print("[v3 Builder] Done.", flush=True)


if __name__ == "__main__":
    main()

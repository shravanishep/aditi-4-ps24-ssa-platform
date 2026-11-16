"""
ml.pipeline.fetch_and_merge_v3 — Ingestion and validation of additional CelesTrak GP records.

Reuses existing CelesTrak data retrieval conventions and validator logic:
- Downloads additional unclassified GP records (visual, analyst, last-30-days, stations)
  from celestrak.org using compliant User-Agent headers.
- Merges with existing data/raw/active_satellites_gp.csv.
- Validates rows using backend.catalog.validator.REQUIRED_GP_FIELDS.
- Deduplicates on NORAD_CAT_ID (preserving existing records on conflict).
- Outputs validated merged dataset to data/raw/satellites_gp_v3.csv without overwriting active_satellites_gp.csv.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from backend.catalog.validator import REQUIRED_GP_FIELDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fetch_and_merge_v3")

CELESTRAK_GROUPS = ["visual", "analyst", "last-30-days", "stations"]
USER_AGENT = "ADITI-SSA-Platform/0.5.0 (https://celestrak.org usage compliant)"


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_celestrak_group(group: str, timeout: float = 15.0) -> pd.DataFrame:
    """Fetch GP CSV for a CelesTrak group."""
    url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=csv"
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    return df


def validate_gp_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Validate required columns and types."""
    missing_cols = [c for c in REQUIRED_GP_FIELDS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"DataFrame missing required GP fields: {missing_cols}")

    initial_count = len(df)
    valid_df = df.dropna(subset=REQUIRED_GP_FIELDS).copy()

    # Numeric range validation
    valid_df = valid_df[
        (valid_df["NORAD_CAT_ID"] > 0)
        & (valid_df["MEAN_MOTION"] > 0)
        & (valid_df["ECCENTRICITY"] >= 0)
        & (valid_df["ECCENTRICITY"] < 1.0)
        & (valid_df["INCLINATION"] >= 0)
        & (valid_df["INCLINATION"] <= 180.0)
    ]

    dropped = initial_count - len(valid_df)
    return valid_df, dropped


def merge_and_save_v3(
    existing_csv_path: str = "data/raw/active_satellites_gp.csv",
    output_csv_path: str = "data/raw/satellites_gp_v3.csv",
    metadata_json_path: str = "data/raw/satellites_gp_v3_metadata.json",
    offline_fallback: bool = True,
) -> dict[str, Any]:
    """Merge existing GP catalogue with additional retrieved CelesTrak records."""
    existing_path = Path(existing_csv_path)
    output_path = Path(output_csv_path)
    meta_path = Path(metadata_json_path)

    if not existing_path.exists():
        raise FileNotFoundError(f"Base CSV not found: {existing_path}")

    logger.info(f"Loading existing baseline GP CSV: {existing_path}")
    base_df = pd.read_csv(existing_path)
    base_valid, base_dropped = validate_gp_dataframe(base_df)
    existing_ids = set(base_valid["NORAD_CAT_ID"])
    logger.info(f"Existing valid records: {len(base_valid)} (dropped {base_dropped} invalid)")

    retrieved_frames: list[pd.DataFrame] = []
    group_stats: dict[str, Any] = {}

    for grp in CELESTRAK_GROUPS:
        try:
            logger.info(f"Fetching CelesTrak group: '{grp}'...")
            df = fetch_celestrak_group(grp)
            v_df, dropped = validate_gp_dataframe(df)
            new_unique = v_df[~v_df["NORAD_CAT_ID"].isin(existing_ids)]
            group_stats[grp] = {
                "status": "success",
                "total_retrieved": len(df),
                "valid_records": len(v_df),
                "new_unique_satellites": len(new_unique),
            }
            logger.info(f"  Group '{grp}': {len(v_df)} valid, {len(new_unique)} new unique.")
            if len(new_unique) > 0:
                retrieved_frames.append(new_unique)
        except Exception as exc:
            logger.warning(f"  Failed to fetch '{grp}': {exc}")
            group_stats[grp] = {"status": "failed", "error": str(exc)}

    if retrieved_frames:
        additional_df = pd.concat(retrieved_frames, ignore_index=True).drop_duplicates("NORAD_CAT_ID")
        combined_df = pd.concat([base_valid, additional_df], ignore_index=True).drop_duplicates("NORAD_CAT_ID")
    else:
        logger.info("No additional records retrieved; using base catalogue.")
        combined_df = base_valid.copy()

    # Save output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined_df.to_csv(output_path, index=False)
    logger.info(f"Saved merged v3 catalogue to {output_path} ({len(combined_df)} records).")

    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_base_csv": str(existing_path),
        "input_base_sha256": sha256_of_file(existing_path),
        "base_satellite_count": len(base_valid),
        "groups_queried": group_stats,
        "new_satellites_added": len(combined_df) - len(base_valid),
        "total_satellites_v3": len(combined_df),
        "output_csv_path": str(output_path),
        "output_csv_sha256": sha256_of_file(output_path),
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return meta


if __name__ == "__main__":
    merge_and_save_v3()

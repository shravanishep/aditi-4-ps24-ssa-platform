from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

REQUIRED_COLUMNS = [
    "OBJECT_NAME",
    "OBJECT_ID",
    "EPOCH",
    "MEAN_MOTION",
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "EPHEMERIS_TYPE",
    "CLASSIFICATION_TYPE",
    "NORAD_CAT_ID",
    "ELEMENT_SET_NO",
    "REV_AT_EPOCH",
    "BSTAR",
    "MEAN_MOTION_DOT",
    "MEAN_MOTION_DDOT",
]

NUMERIC_COLUMNS = [
    "MEAN_MOTION",
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "NORAD_CAT_ID",
    "ELEMENT_SET_NO",
    "REV_AT_EPOCH",
    "BSTAR",
    "MEAN_MOTION_DOT",
    "MEAN_MOTION_DDOT",
]


def parse_epoch(value: str | datetime) -> datetime:
    """Parse a GP EPOCH string and return a timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        dt = value
    elif value is None or str(value).strip() == "":
        raise ValueError("EPOCH value is missing.")
    else:
        value_str = str(value).strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(value_str, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Could not parse EPOCH value: {value!r}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validate_required_columns(columns: Iterable[str]) -> None:
    column_set = set(columns)
    missing = [column for column in REQUIRED_COLUMNS if column not in column_set]
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(f"Required GP columns are missing: {missing_str}")


def _coerce_numeric_fields(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in NUMERIC_COLUMNS:
        if column not in result.columns:
            continue
        try:
            result[column] = pd.to_numeric(result[column], errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Orbital value is invalid for column '{column}'.") from exc
    return result


def load_gp_data(csv_path: str | Path) -> pd.DataFrame:
    """Load the GP CSV and validate the required orbital schema."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"GP data file not found: {path}")

    frame = pd.read_csv(path)
    _validate_required_columns(frame.columns)
    frame = _coerce_numeric_fields(frame)

    for idx, row in frame.iterrows():
        _validate_gp_record(row)

    return frame


def _validate_gp_record(row: pd.Series) -> None:
    """Ensure the row contains valid orbital values and a usable epoch."""
    try:
        parse_epoch(row["EPOCH"])
    except ValueError as exc:
        raise ValueError(f"Invalid EPOCH value for object {row.get('OBJECT_NAME', 'unknown')}: {row.get('EPOCH')!r}") from exc

    required_numeric = [
        "MEAN_MOTION",
        "ECCENTRICITY",
        "INCLINATION",
        "RA_OF_ASC_NODE",
        "ARG_OF_PERICENTER",
        "MEAN_ANOMALY",
        "NORAD_CAT_ID",
        "BSTAR",
        "MEAN_MOTION_DOT",
        "MEAN_MOTION_DDOT",
    ]

    for column in required_numeric:
        value = row.get(column)
        if pd.isna(value):
            raise ValueError(f"Required orbital value is missing for column '{column}'.")

    norad_id = int(row["NORAD_CAT_ID"])
    if norad_id <= 0:
        raise ValueError(f"NORAD_CAT_ID must be positive; got {norad_id!r}.")

    mean_motion = float(row["MEAN_MOTION"])
    if mean_motion <= 0:
        raise ValueError(f"MEAN_MOTION must be positive for NORAD_CAT_ID {norad_id}.")


def get_satellite_by_norad(norad_cat_id: int, csv_path: str | Path = "data/raw/active_satellites_gp.csv") -> pd.Series:
    """Return one GP row matching the given NORAD ID."""
    frame = load_gp_data(csv_path)
    try:
        norad_id = int(norad_cat_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"NORAD_CAT_ID must be an integer; got {norad_cat_id!r}.") from exc

    matches = frame[frame["NORAD_CAT_ID"] == norad_id]
    if matches.empty:
        raise ValueError(f"NORAD_CAT_ID {norad_id} does not exist in the GP dataset.")

    return matches.iloc[0].copy()


def get_satellite_by_name(object_name: str, csv_path: str | Path = "data/raw/active_satellites_gp.csv") -> pd.Series:
    """Optional helper for name-based lookup."""
    frame = load_gp_data(csv_path)
    target = str(object_name).strip()
    matches = frame[frame["OBJECT_NAME"].str.strip() == target]
    if matches.empty:
        raise ValueError(f"OBJECT_NAME '{target}' does not exist in the GP dataset.")
    return matches.iloc[0].copy()

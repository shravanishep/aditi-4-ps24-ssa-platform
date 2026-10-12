"""
backend.catalog.satcat_parser — SATCAT metadata parsing and classification mapping.

Parses CelesTrak-style SATCAT files and maps raw object types and operational
status codes to normalized ObjectClassification enum values.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from backend.catalog.models import ObjectClassification, ValidationRejection

logger = logging.getLogger(__name__)


def map_satcat_classification(
    object_type: str | None,
    ops_status_code: str | None = None,
    decay_date: str | None = None,
) -> ObjectClassification:
    """Map raw SATCAT fields to a normalized ObjectClassification enum.

    Rules
    -----
    1. If a decay date is specified and non-empty, object has re-entered:
       - Payload -> INACTIVE_SATELLITE
       - Rocket Body -> ROCKET_BODY
       - Debris -> DEBRIS
    2. OBJECT_TYPE:
       - "R/B", "RB", "ROCKET BODY" -> ROCKET_BODY
       - "DEB", "DEBRIS" -> DEBRIS
       - "PAY", "PAYLOAD":
         - OPS_STATUS_CODE in ('+', 'P', 'B', 'S', 'X', 'OPERATIONAL') -> ACTIVE_SATELLITE
         - OPS_STATUS_CODE in ('-', 'D', 'NON-OPERATIONAL', 'INACTIVE') -> INACTIVE_SATELLITE
         - Otherwise ('?', '', None) -> UNKNOWN (operational status not established)
       - "UNK", "UNKNOWN", or missing -> UNKNOWN
    """
    t = str(object_type).strip().upper() if object_type is not None else ""
    s = str(ops_status_code).strip().upper() if ops_status_code is not None else ""
    
    has_decayed = False
    if decay_date is not None and pd.notna(decay_date):
        d_str = str(decay_date).strip().lower()
        if d_str and d_str not in ("", "none", "nan", "null"):
            has_decayed = True

    if t in ("R/B", "RB", "ROCKET BODY", "ROCKET_BODY"):
        return ObjectClassification.ROCKET_BODY
    elif t in ("DEB", "DEBRIS"):
        return ObjectClassification.DEBRIS
    elif t in ("PAY", "PAYLOAD", "SATELLITE"):
        if has_decayed or s in ("-", "D", "NON-OPERATIONAL", "INACTIVE", "DEFUNCT"):
            return ObjectClassification.INACTIVE_SATELLITE
        elif s in ("+", "P", "B", "S", "X", "OPERATIONAL", "ACTIVE"):
            return ObjectClassification.ACTIVE_SATELLITE
        else:
            return ObjectClassification.UNKNOWN
    else:
        return ObjectClassification.UNKNOWN


def parse_satcat_dataframe(
    df: pd.DataFrame, source_label: str = "satcat"
) -> tuple[dict[int, dict[str, Any]], list[ValidationRejection]]:
    """Parse SATCAT DataFrame and return map of NORAD_CAT_ID to metadata dict.

    Parameters
    ----------
    df:
        DataFrame containing SATCAT rows.
    source_label:
        Origin identifier for rejection tracking.

    Returns
    -------
    tuple[dict[int, dict[str, Any]], list[ValidationRejection]]
        Map of norad_id -> metadata, and list of rejected records.
    """
    col_map: dict[str, str] = {}
    for col in df.columns:
        c_upper = col.strip().upper()
        if c_upper in ("NORAD_CAT_ID", "OBJECT_NUMBER", "NORAD_ID", "SATCAT_ID"):
            col_map["NORAD_CAT_ID"] = col
        elif c_upper in ("OBJECT_NAME", "NAME", "SATNAME"):
            col_map["OBJECT_NAME"] = col
        elif c_upper in ("OBJECT_ID", "INTLDES", "INTERNATIONAL_DESIGNATOR"):
            col_map["OBJECT_ID"] = col
        elif c_upper in ("OBJECT_TYPE", "OBJSUBTYPE", "TYPE"):
            col_map["OBJECT_TYPE"] = col
        elif c_upper in ("OPS_STATUS_CODE", "STATUS", "OPS_STATUS"):
            col_map["OPS_STATUS_CODE"] = col
        elif c_upper in ("OWNER", "COUNTRY", "COUNTRY_CODE"):
            col_map["OWNER"] = col
        elif c_upper in ("LAUNCH_DATE", "LAUNCH"):
            col_map["LAUNCH_DATE"] = col
        elif c_upper in ("DECAY_DATE", "DECAY"):
            col_map["DECAY_DATE"] = col

    if "NORAD_CAT_ID" not in col_map:
        raise ValueError(
            f"SATCAT dataset missing NORAD ID column. Found columns: {list(df.columns)}"
        )

    records: dict[int, dict[str, Any]] = {}
    rejections: list[ValidationRejection] = []

    for idx, row in df.iterrows():
        raw_id = row.get(col_map["NORAD_CAT_ID"])
        try:
            if pd.isna(raw_id) or str(raw_id).strip() == "":
                rejections.append(
                    ValidationRejection(
                        source=source_label,
                        identifier=f"row_{idx}",
                        reason="Missing NORAD_CAT_ID in SATCAT row.",
                        raw_data=dict(row),
                    )
                )
                continue
            norad_id = int(raw_id)
            if norad_id <= 0:
                rejections.append(
                    ValidationRejection(
                        source=source_label,
                        identifier=norad_id,
                        reason=f"Non-positive NORAD_CAT_ID: {norad_id}",
                        raw_data=dict(row),
                    )
                )
                continue
        except (ValueError, TypeError) as exc:
            rejections.append(
                ValidationRejection(
                    source=source_label,
                    identifier=f"row_{idx}",
                    reason=f"Unparseable NORAD_CAT_ID '{raw_id}': {exc}",
                    raw_data=dict(row),
                )
            )
            continue

        obj_name = str(row.get(col_map.get("OBJECT_NAME", ""), "")).strip()
        obj_id = str(row.get(col_map.get("OBJECT_ID", ""), "")).strip()
        obj_type = row.get(col_map.get("OBJECT_TYPE", None))
        ops_status = row.get(col_map.get("OPS_STATUS_CODE", None))
        decay = row.get(col_map.get("DECAY_DATE", None))
        owner = row.get(col_map.get("OWNER", None))

        classification = map_satcat_classification(
            object_type=obj_type,
            ops_status_code=ops_status,
            decay_date=decay,
        )

        records[norad_id] = {
            "norad_cat_id": norad_id,
            "object_name": obj_name,
            "object_id": obj_id,
            "object_type_raw": str(obj_type).strip() if pd.notna(obj_type) else None,
            "ops_status_code": str(ops_status).strip() if pd.notna(ops_status) else None,
            "owner": str(owner).strip() if pd.notna(owner) else None,
            "decay_date": (
                str(decay).strip()
                if pd.notna(decay) and str(decay).strip().lower() not in ("", "none", "nan", "null")
                else None
            ),
            "classification": classification,
            "source_provenance": source_label,
        }

    return records, rejections

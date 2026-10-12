"""
backend.catalog.validator — Validation and deduplication rules for GP orbital records.

Enforces physical numeric bounds, timestamp parsing, freshness evaluation,
and deterministic deduplication (latest epoch wins).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from backend.catalog.models import ValidationRejection
from backend.orbital.gp_loader import parse_epoch

logger = logging.getLogger(__name__)

REQUIRED_GP_FIELDS = [
    "NORAD_CAT_ID",
    "EPOCH",
    "MEAN_MOTION",
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
]


def validate_gp_row(
    row: pd.Series | dict[str, Any],
    source_label: str = "gp",
    reference_time: datetime | None = None,
) -> tuple[dict[str, Any] | None, ValidationRejection | None]:
    """Validate a single orbital GP record against physical and numeric bounds.

    Returns
    -------
    tuple[dict[str, Any] | None, ValidationRejection | None]
        (validated_record_dict, None) on success, or (None, rejection) on failure.
    """
    row_dict = dict(row)
    raw_id = row_dict.get("NORAD_CAT_ID")

    # 1. NORAD ID check
    try:
        if pd.isna(raw_id) or str(raw_id).strip() == "":
            return None, ValidationRejection(
                source=source_label,
                identifier="unknown",
                reason="Missing NORAD_CAT_ID.",
                raw_data=row_dict,
            )
        norad_id = int(raw_id)
        if norad_id <= 0:
            return None, ValidationRejection(
                source=source_label,
                identifier=norad_id,
                reason=f"Non-positive NORAD_CAT_ID: {norad_id}",
                raw_data=row_dict,
            )
    except (ValueError, TypeError) as exc:
        return None, ValidationRejection(
            source=source_label,
            identifier=str(raw_id),
            reason=f"Invalid NORAD_CAT_ID: {exc}",
            raw_data=row_dict,
        )

    # 2. Required fields check
    for field in REQUIRED_GP_FIELDS:
        val = row_dict.get(field)
        if val is None or pd.isna(val) or str(val).strip() == "":
            return None, ValidationRejection(
                source=source_label,
                identifier=norad_id,
                reason=f"Missing required orbital field: '{field}'",
                raw_data=row_dict,
            )

    # 3. Epoch parsing
    raw_epoch = row_dict.get("EPOCH")
    try:
        epoch_dt = parse_epoch(raw_epoch)
    except Exception as exc:
        return None, ValidationRejection(
            source=source_label,
            identifier=norad_id,
            reason=f"Unparseable EPOCH value '{raw_epoch}': {exc}",
            raw_data=row_dict,
        )

    # 4. Numeric range checks
    try:
        mean_motion = float(row_dict["MEAN_MOTION"])
        if mean_motion <= 0.0:
            return None, ValidationRejection(
                source=source_label,
                identifier=norad_id,
                reason=f"MEAN_MOTION must be strictly positive; got {mean_motion}",
                raw_data=row_dict,
            )

        eccentricity = float(row_dict["ECCENTRICITY"])
        if eccentricity < 0.0 or eccentricity >= 1.0:
            return None, ValidationRejection(
                source=source_label,
                identifier=norad_id,
                reason=f"ECCENTRICITY must be in [0.0, 1.0); got {eccentricity}",
                raw_data=row_dict,
            )

        inclination = float(row_dict["INCLINATION"])
        if inclination < 0.0 or inclination > 180.0:
            return None, ValidationRejection(
                source=source_label,
                identifier=norad_id,
                reason=f"INCLINATION must be in [0.0, 180.0]; got {inclination}",
                raw_data=row_dict,
            )

        raan = float(row_dict["RA_OF_ASC_NODE"])
        arg_p = float(row_dict["ARG_OF_PERICENTER"])
        mean_anom = float(row_dict["MEAN_ANOMALY"])
        for name, val in [("RA_OF_ASC_NODE", raan), ("ARG_OF_PERICENTER", arg_p), ("MEAN_ANOMALY", mean_anom)]:
            if val < 0.0 or val > 360.0:
                # Wrap or warn if out of bounds
                row_dict[name] = val % 360.0

    except (ValueError, TypeError) as exc:
        return None, ValidationRejection(
            source=source_label,
            identifier=norad_id,
            reason=f"Non-numeric orbital element: {exc}",
            raw_data=row_dict,
        )

    # Compute freshness
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    epoch_age_days = (reference_time - epoch_dt).total_seconds() / 86400.0

    validated = dict(row_dict)
    validated["NORAD_CAT_ID"] = norad_id
    validated["EPOCH_DATETIME"] = epoch_dt
    validated["EPOCH_AGE_DAYS"] = epoch_age_days
    validated["MEAN_MOTION"] = mean_motion
    validated["ECCENTRICITY"] = eccentricity
    validated["INCLINATION"] = inclination

    return validated, None


def deduplicate_gp_records(
    records: list[dict[str, Any]],
    source_label: str = "gp",
) -> tuple[dict[int, dict[str, Any]], list[ValidationRejection]]:
    """Deduplicate orbital GP records by NORAD ID using latest epoch wins.

    Parameters
    ----------
    records:
        List of pre-validated GP record dicts containing 'NORAD_CAT_ID'
        and 'EPOCH_DATETIME'.
    source_label:
        Origin identifier for rejection audit tracking.

    Returns
    -------
    tuple[dict[int, dict[str, Any]], list[ValidationRejection]]
        (deduplicated_records_by_norad_id, rejection_audit_list)
    """
    dedup: dict[int, dict[str, Any]] = {}
    rejections: list[ValidationRejection] = []

    for rec in records:
        norad_id = int(rec["NORAD_CAT_ID"])
        epoch = rec["EPOCH_DATETIME"]

        if norad_id not in dedup:
            dedup[norad_id] = rec
        else:
            existing_epoch = dedup[norad_id]["EPOCH_DATETIME"]
            if epoch > existing_epoch:
                # Supersede older record
                old_rec = dedup[norad_id]
                dedup[norad_id] = rec
                rejections.append(
                    ValidationRejection(
                        source=source_label,
                        identifier=norad_id,
                        reason=(
                            f"Superseded duplicate record with older epoch {existing_epoch.isoformat()} "
                            f"by newer epoch {epoch.isoformat()}."
                        ),
                        raw_data=old_rec,
                    )
                )
            else:
                # Discard incoming older or equal record
                rejections.append(
                    ValidationRejection(
                        source=source_label,
                        identifier=norad_id,
                        reason=(
                            f"Ignored duplicate record with epoch {epoch.isoformat()} "
                            f"in favor of existing epoch {existing_epoch.isoformat()}."
                        ),
                        raw_data=rec,
                    )
                )

    return dedup, rejections

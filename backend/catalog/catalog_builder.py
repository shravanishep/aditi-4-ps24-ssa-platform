"""
backend.catalog.catalog_builder — Unified catalogue construction pipeline.

Coordinates multi-source GP loading, SATCAT join, deterministic deduplication,
classification mapping, and data quality tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.catalog.config import CatalogConfig, GPSourceConfig
from backend.catalog.models import (
    CatalogObject,
    ObjectClassification,
    UnifiedCatalog,
    ValidationRejection,
)
from backend.catalog.satcat_parser import parse_satcat_dataframe
from backend.catalog.source_adapter import SourceAdapter
from backend.catalog.validator import deduplicate_gp_records, validate_gp_row

logger = logging.getLogger(__name__)


def build_unified_catalog(
    config: CatalogConfig | None = None,
    adapter: SourceAdapter | None = None,
    include_satcat_only_objects: bool = False,
) -> UnifiedCatalog:
    """Build a unified, validated space object catalogue from configured sources.

    Parameters
    ----------
    config:
        CatalogConfig instance. If None, CatalogConfig.default() is used.
    adapter:
        Optional SourceAdapter instance. If None, a new SourceAdapter is used.
    include_satcat_only_objects:
        If True, objects present in SATCAT without orbital GP data are included
        with ``has_orbital_data=False``.

    Returns
    -------
    UnifiedCatalog
        Complete catalogue containing validated objects, deduplication audit,
        and rejection records.
    """
    if config is None:
        config = CatalogConfig.default()
    if adapter is None:
        adapter = SourceAdapter()

    catalog = UnifiedCatalog()
    ref_time = config.reference_time or datetime.now(timezone.utc)

    # 1. Load SATCAT metadata if configured
    satcat_records: dict[int, dict[str, Any]] = {}
    satcat_df, satcat_rejections = adapter.load_satcat_source(
        satcat_path=config.satcat_path,
        remote_url=config.satcat_remote_url,
        allow_remote=config.allow_remote_fetch,
        timeout=config.http_timeout_seconds,
    )
    for rej in satcat_rejections:
        catalog.add_rejection(rej)

    if satcat_df is not None and not satcat_df.empty:
        try:
            parsed_satcat, parse_rejections = parse_satcat_dataframe(
                satcat_df, source_label="satcat"
            )
            satcat_records = parsed_satcat
            for rej in parse_rejections:
                catalog.add_rejection(rej)
            logger.info("Loaded SATCAT metadata for %d objects", len(satcat_records))
        except Exception as exc:
            logger.warning("Failed parsing SATCAT dataset: %s", exc)
            catalog.add_rejection(
                ValidationRejection(
                    source="satcat",
                    identifier="dataset",
                    reason=f"SATCAT parsing failed: {exc}",
                )
            )

    # 2. Ingest and validate all enabled GP sources
    raw_gp_records: list[dict[str, Any]] = []
    source_hints: dict[int, ObjectClassification] = {}
    source_labels: dict[int, str] = {}

    for gp_cfg in config.gp_sources:
        if not gp_cfg.enabled:
            continue

        df_gp, gp_load_rejections = adapter.load_gp_source(
            gp_cfg,
            allow_remote=config.allow_remote_fetch,
            timeout=config.http_timeout_seconds,
        )
        for rej in gp_load_rejections:
            catalog.add_rejection(rej)

        if df_gp is None or df_gp.empty:
            logger.debug("GP source '%s' yielded no data", gp_cfg.source_name)
            continue

        for _, row in df_gp.iterrows():
            valid_rec, val_rej = validate_gp_row(
                row,
                source_label=gp_cfg.source_name,
                reference_time=ref_time,
            )
            if val_rej is not None:
                catalog.add_rejection(val_rej)
            elif valid_rec is not None:
                nid = int(valid_rec["NORAD_CAT_ID"])
                raw_gp_records.append(valid_rec)
                if gp_cfg.category_hint is not None and nid not in source_hints:
                    source_hints[nid] = gp_cfg.category_hint
                if nid not in source_labels:
                    source_labels[nid] = gp_cfg.source_name

    # 3. Deduplicate GP records (latest epoch wins)
    dedup_gp, dedup_rejections = deduplicate_gp_records(
        raw_gp_records, source_label="gp_deduplication"
    )
    for rej in dedup_rejections:
        catalog.add_rejection(rej)

    catalog.max_epoch_age_threshold_days = config.max_epoch_age_days
    catalog.stale_data_policy = config.stale_data_policy

    # 4. Assemble objects with orbital records
    for norad_id, gp_rec in dedup_gp.items():
        obj_name = str(gp_rec.get("OBJECT_NAME", "")).strip()
        obj_id = str(gp_rec.get("OBJECT_ID", "")).strip()
        epoch_dt = gp_rec.get("EPOCH_DATETIME")
        age_days = gp_rec.get("EPOCH_AGE_DAYS")
        src_label = source_labels.get(norad_id, "gp")

        # Freshness evaluation
        is_stale = False
        freshness_status = "fresh"
        if epoch_dt is None:
            freshness_status = "missing_epoch"
        elif config.max_epoch_age_days is not None and age_days is not None:
            if age_days > config.max_epoch_age_days:
                is_stale = True
                freshness_status = "stale"

        # Join SATCAT metadata if present
        satcat_meta = satcat_records.get(norad_id)
        if satcat_meta is not None:
            classification = satcat_meta["classification"]
            ops_status = satcat_meta.get("ops_status_code")
            owner = satcat_meta.get("owner")
            classification_verified = (classification != ObjectClassification.UNKNOWN)
            classification_source = "satcat"
            provenance = f"{src_label}+satcat"
            if not obj_name:
                obj_name = satcat_meta.get("object_name", "")
            if not obj_id:
                obj_id = satcat_meta.get("object_id", "")
        else:
            # Fall back to category hint or UNKNOWN
            classification = source_hints.get(norad_id, ObjectClassification.UNKNOWN)
            ops_status = None
            owner = None
            classification_verified = False
            classification_source = "source_group_hint" if norad_id in source_hints else "unverified"
            provenance = f"{src_label} (source_group_hint, no SATCAT)"

        cat_obj = CatalogObject(
            norad_cat_id=norad_id,
            object_name=obj_name,
            object_id=obj_id,
            classification=classification,
            classification_verified=classification_verified,
            classification_source=classification_source,
            ops_status_code=ops_status,
            owner=owner,
            epoch=epoch_dt,
            epoch_age_days=age_days,
            is_stale=is_stale,
            freshness_status=freshness_status,
            source_provenance=provenance,
            has_orbital_data=True,
            orbital_record=gp_rec,
            is_protected_target=(classification == ObjectClassification.ACTIVE_SATELLITE),
            is_threat_candidate=True,
        )
        catalog.add_object(cat_obj)

    # 5. Optionally include objects that exist in SATCAT without orbital data
    if include_satcat_only_objects:
        for norad_id, sat_meta in satcat_records.items():
            if norad_id in catalog.objects:
                continue
            cat_obj = CatalogObject(
                norad_cat_id=norad_id,
                object_name=sat_meta.get("object_name", ""),
                object_id=sat_meta.get("object_id", ""),
                classification=sat_meta.get("classification", ObjectClassification.UNKNOWN),
                ops_status_code=sat_meta.get("ops_status_code"),
                owner=sat_meta.get("owner"),
                epoch=None,
                epoch_age_days=None,
                source_provenance="satcat_only",
                has_orbital_data=False,
                orbital_record=None,
                is_protected_target=(sat_meta.get("classification") == ObjectClassification.ACTIVE_SATELLITE),
                is_threat_candidate=False,
            )
            catalog.add_object(cat_obj)

    return catalog

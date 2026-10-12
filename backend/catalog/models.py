"""
backend.catalog.models — Data models for Layer 10 unified object catalogue.

Defines normalized classifications, catalog object records, rejection audit models,
freshness indicators, and the UnifiedCatalog container class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable

import numpy as np
import pandas as pd


class ObjectClassification(str, Enum):
    """Normalized object classification for catalogued Earth-orbiting objects."""

    ACTIVE_SATELLITE = "ACTIVE_SATELLITE"
    INACTIVE_SATELLITE = "INACTIVE_SATELLITE"
    ROCKET_BODY = "ROCKET_BODY"
    DEBRIS = "DEBRIS"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_string(cls, val: str | None) -> ObjectClassification:
        if not val:
            return cls.UNKNOWN
        clean = str(val).strip().upper()
        for member in cls:
            if member.value == clean or member.name == clean:
                return member
        return cls.UNKNOWN


@dataclass
class CatalogObject:
    """A single catalogued space object with orbital state and metadata."""

    norad_cat_id: int
    object_name: str
    object_id: str = ""
    classification: ObjectClassification = ObjectClassification.UNKNOWN
    classification_verified: bool = False
    classification_source: str = "unverified"
    ops_status_code: str | None = None
    owner: str | None = None
    epoch: datetime | None = None
    epoch_age_days: float | None = None
    is_stale: bool = False
    freshness_status: str = "fresh"  # "fresh", "stale", "missing_epoch"
    source_provenance: str = "unknown"
    has_orbital_data: bool = False
    orbital_record: dict[str, Any] | None = None
    is_protected_target: bool = False
    is_threat_candidate: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert object metadata to dictionary."""
        return {
            "norad_cat_id": self.norad_cat_id,
            "object_name": self.object_name,
            "object_id": self.object_id,
            "classification": self.classification.value,
            "classification_verified": self.classification_verified,
            "classification_source": self.classification_source,
            "ops_status_code": self.ops_status_code,
            "owner": self.owner,
            "epoch": self.epoch.isoformat() if self.epoch else None,
            "epoch_age_days": self.epoch_age_days,
            "is_stale": self.is_stale,
            "freshness_status": self.freshness_status,
            "source_provenance": self.source_provenance,
            "has_orbital_data": self.has_orbital_data,
            "is_protected_target": self.is_protected_target,
            "is_threat_candidate": self.is_threat_candidate,
        }


@dataclass
class ValidationRejection:
    """Record of an invalid, unparseable, or duplicate record during ingestion."""

    source: str
    identifier: str | int
    reason: str
    raw_data: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CatalogSummary:
    """Summary statistics for a UnifiedCatalog instance."""

    total_objects: int
    counts_by_classification: dict[str, int]
    counts_by_source: dict[str, int]
    objects_with_orbital_data: int
    objects_without_orbital_data: int
    rejected_records_count: int
    fresh_records_count: int = 0
    stale_records_count: int = 0
    missing_epoch_count: int = 0
    max_epoch_age_threshold_days: float | None = None
    stale_data_policy: str = "flag"
    freshest_epoch: datetime | None = None
    oldest_epoch: datetime | None = None
    median_epoch_age_days: float | None = None
    disclaimer: str = (
        "Catalogue data is derived from unclassified public sources (e.g. CelesTrak) "
        "and simplified SGP4 general perturbations. It is an educational and research "
        "prototype, not a certified operational collision-avoidance catalogue."
    )


class UnifiedCatalog:
    """Container holding validated space objects and ingestion audit trail."""

    def __init__(self) -> None:
        self.objects: dict[int, CatalogObject] = {}
        self.rejections: list[ValidationRejection] = []
        self.max_epoch_age_threshold_days: float | None = None
        self.stale_data_policy: str = "flag"

    def add_object(self, obj: CatalogObject) -> None:
        """Add or update an object in the catalogue."""
        self.objects[obj.norad_cat_id] = obj

    def add_rejection(self, rejection: ValidationRejection) -> None:
        """Record an ingestion failure or duplicate rejection."""
        self.rejections.append(rejection)

    def get(self, norad_id: int) -> CatalogObject | None:
        """Look up object by NORAD ID."""
        return self.objects.get(int(norad_id))

    def __len__(self) -> int:
        return len(self.objects)

    def __iter__(self) -> Iterable[CatalogObject]:
        return iter(self.objects.values())

    def get_by_classification(self, classification: ObjectClassification) -> list[CatalogObject]:
        """Filter catalogue by normalized classification."""
        return [o for o in self.objects.values() if o.classification == classification]

    def get_active_satellites(self) -> list[CatalogObject]:
        """Return active satellites in catalogue."""
        return self.get_by_classification(ObjectClassification.ACTIVE_SATELLITE)

    def get_threat_candidates(self) -> list[CatalogObject]:
        """Return all objects flagged as potential threat candidates."""
        return [o for o in self.objects.values() if o.is_threat_candidate and o.has_orbital_data]

    def to_gp_dataframe(
        self, only_with_orbital_data: bool = True, exclude_stale: bool = False
    ) -> pd.DataFrame:
        """Export catalogue to a pandas DataFrame compatible with SGP4 and Layer 9.

        Includes standard orbital columns plus Layer 10 metadata columns:
        ``CLASSIFICATION``, ``OBJECT_TYPE``, ``SOURCE_PROVENANCE``, ``OPS_STATUS_CODE``,
        ``OWNER``, ``CLASSIFICATION_VERIFIED``, ``CLASSIFICATION_SOURCE``,
        ``IS_STALE``, and ``FRESHNESS_STATUS``.
        """
        rows = []
        for obj in self.objects.values():
            if only_with_orbital_data and not obj.has_orbital_data:
                continue
            if exclude_stale and obj.is_stale:
                continue
            if obj.orbital_record is not None:
                row = dict(obj.orbital_record)
            else:
                row = {
                    "NORAD_CAT_ID": obj.norad_cat_id,
                    "OBJECT_NAME": obj.object_name,
                    "OBJECT_ID": obj.object_id,
                    "EPOCH": obj.epoch.isoformat() if obj.epoch else None,
                }
            # Add or override normalized classification and freshness metadata
            row["CLASSIFICATION"] = obj.classification.value
            row["OBJECT_TYPE"] = obj.classification.value
            row["CLASSIFICATION_VERIFIED"] = obj.classification_verified
            row["CLASSIFICATION_SOURCE"] = obj.classification_source
            row["OPS_STATUS_CODE"] = obj.ops_status_code or ""
            row["OWNER"] = obj.owner or ""
            row["SOURCE_PROVENANCE"] = obj.source_provenance
            row["HAS_ORBITAL_DATA"] = obj.has_orbital_data
            row["IS_STALE"] = obj.is_stale
            row["FRESHNESS_STATUS"] = obj.freshness_status
            row["EPOCH_AGE_DAYS"] = obj.epoch_age_days
            rows.append(row)

        if not rows:
            return pd.DataFrame(
                columns=[
                    "NORAD_CAT_ID",
                    "OBJECT_NAME",
                    "OBJECT_ID",
                    "EPOCH",
                    "CLASSIFICATION",
                    "OBJECT_TYPE",
                    "CLASSIFICATION_VERIFIED",
                    "CLASSIFICATION_SOURCE",
                    "OPS_STATUS_CODE",
                    "OWNER",
                    "SOURCE_PROVENANCE",
                    "HAS_ORBITAL_DATA",
                    "IS_STALE",
                    "FRESHNESS_STATUS",
                    "EPOCH_AGE_DAYS",
                ]
            )
        return pd.DataFrame(rows)

    def summary(self, reference_time: datetime | None = None) -> CatalogSummary:
        """Compute summary statistics, classification counts, and freshness metrics."""
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        counts_by_class = {c.value: 0 for c in ObjectClassification}
        counts_by_source: dict[str, int] = {}
        with_orbital = 0
        without_orbital = 0
        epochs: list[datetime] = []
        ages_days: list[float] = []

        fresh_count = 0
        stale_count = 0
        missing_epoch_count = 0

        for obj in self.objects.values():
            counts_by_class[obj.classification.value] += 1
            src = obj.source_provenance or "unknown"
            counts_by_source[src] = counts_by_source.get(src, 0) + 1

            if obj.has_orbital_data and obj.epoch:
                with_orbital += 1
                epochs.append(obj.epoch)
                age = (reference_time - obj.epoch).total_seconds() / 86400.0
                ages_days.append(age)

                if obj.is_stale:
                    stale_count += 1
                else:
                    fresh_count += 1
            else:
                without_orbital += 1
                missing_epoch_count += 1

        freshest = max(epochs) if epochs else None
        oldest = min(epochs) if epochs else None
        median_age = float(np.median(ages_days)) if ages_days else None

        return CatalogSummary(
            total_objects=len(self.objects),
            counts_by_classification=counts_by_class,
            counts_by_source=counts_by_source,
            objects_with_orbital_data=with_orbital,
            objects_without_orbital_data=without_orbital,
            rejected_records_count=len(self.rejections),
            fresh_records_count=fresh_count,
            stale_records_count=stale_count,
            missing_epoch_count=missing_epoch_count,
            max_epoch_age_threshold_days=self.max_epoch_age_threshold_days,
            stale_data_policy=self.stale_data_policy,
            freshest_epoch=freshest,
            oldest_epoch=oldest,
            median_epoch_age_days=median_age,
        )

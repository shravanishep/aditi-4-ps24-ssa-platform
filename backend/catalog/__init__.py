"""
backend.catalog — Layer 10 space object catalogue and ingestion package.

Provides unified loading, validation, SATCAT joining, classification mapping,
and deduplication for active satellites, debris, rocket bodies, and inactive objects.
"""

from backend.catalog.config import CatalogConfig, GPSourceConfig
from backend.catalog.models import (
    CatalogObject,
    CatalogSummary,
    ObjectClassification,
    UnifiedCatalog,
    ValidationRejection,
)
from backend.catalog.satcat_parser import (
    map_satcat_classification,
    parse_satcat_dataframe,
)
from backend.catalog.source_adapter import RemoteIngestionError, SourceAdapter
from backend.catalog.catalog_builder import build_unified_catalog
from backend.catalog.validator import deduplicate_gp_records, validate_gp_row

__all__ = [
    "CatalogConfig",
    "GPSourceConfig",
    "CatalogObject",
    "CatalogSummary",
    "ObjectClassification",
    "UnifiedCatalog",
    "ValidationRejection",
    "map_satcat_classification",
    "parse_satcat_dataframe",
    "RemoteIngestionError",
    "SourceAdapter",
    "build_unified_catalog",
    "validate_gp_row",
    "deduplicate_gp_records",
]

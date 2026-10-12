"""
backend.catalog.config — Configuration models for Layer 10 catalogue ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.catalog.models import ObjectClassification


@dataclass
class GPSourceConfig:
    """Configuration for a single orbital GP dataset source."""

    source_name: str
    path: str | Path | None = None
    remote_url: str | None = None
    category_hint: ObjectClassification | None = None
    enabled: bool = True

    def get_path(self) -> Path | None:
        if self.path is None:
            return None
        return Path(self.path)


@dataclass
class CatalogConfig:
    """Master configuration for Layer 10 unified catalogue assembly."""

    gp_sources: list[GPSourceConfig] = field(default_factory=list)
    satcat_path: str | Path | None = "data/raw/satcat.csv"
    satcat_remote_url: str | None = "https://celestrak.org/pub/satcat.csv"
    allow_remote_fetch: bool = False
    http_timeout_seconds: float = 10.0
    reference_time: datetime | None = None
    max_epoch_age_days: float | None = None
    stale_data_policy: str = "flag"  # "flag" or "exclude"

    def get_satcat_path(self) -> Path | None:
        if self.satcat_path is None:
            return None
        return Path(self.satcat_path)

    @classmethod
    def default(cls) -> CatalogConfig:
        """Create standard default configuration pointing to local repository files."""
        return cls(
            gp_sources=[
                GPSourceConfig(
                    source_name="active_satellites_gp",
                    path="data/raw/active_satellites_gp.csv",
                    remote_url="https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=csv",
                    category_hint=ObjectClassification.ACTIVE_SATELLITE,
                    enabled=True,
                ),
            ],
            satcat_path="data/raw/satcat.csv",
            satcat_remote_url="https://celestrak.org/pub/satcat.csv",
            allow_remote_fetch=False,
            http_timeout_seconds=10.0,
        )

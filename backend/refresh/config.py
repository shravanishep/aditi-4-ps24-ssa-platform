"""
backend.refresh.config — Configuration definitions for automated data refresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.catalog.models import ObjectClassification


@dataclass
class RefreshSourceConfig:
    """Configuration for an individual remote data source to be refreshed."""

    source_name: str
    url: str
    dest_path: Path | str
    category_hint: ObjectClassification | None = None
    is_gp_data: bool = True
    enabled: bool = True
    min_expected_records: int = 20
    required: bool = True

    def get_dest_path(self) -> Path:
        return Path(self.dest_path)


@dataclass
class RefreshConfig:
    """Master configuration for the automated data refresh workflow."""

    sources: list[RefreshSourceConfig] = field(default_factory=list)
    metadata_path: Path | str = "data/catalog_refresh_metadata.json"
    http_timeout_seconds: float = 15.0
    max_retries: int = 3
    backoff_factor: float = 1.0
    max_epoch_age_days: float = 30.0
    dry_run: bool = False

    def get_metadata_path(self) -> Path:
        return Path(self.metadata_path)

    @classmethod
    def default(cls, project_root: Path | None = None) -> RefreshConfig:
        """Create standard default configuration pointing to project datasets."""
        root = project_root or Path(".")
        return cls(
            sources=[
                RefreshSourceConfig(
                    source_name="active_satellites_gp",
                    url="https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=csv",
                    dest_path=root / "data" / "raw" / "active_satellites_gp.csv",
                    category_hint=ObjectClassification.ACTIVE_SATELLITE,
                    is_gp_data=True,
                    enabled=True,
                    min_expected_records=50,
                    required=True,
                ),
                RefreshSourceConfig(
                    source_name="satcat",
                    url="https://celestrak.org/pub/satcat.csv",
                    dest_path=root / "data" / "raw" / "satcat.csv",
                    category_hint=None,
                    is_gp_data=False,
                    enabled=True,
                    min_expected_records=50,
                    required=False,  # SATCAT is optional metadata
                ),
            ],
            metadata_path=root / "data" / "catalog_refresh_metadata.json",
            http_timeout_seconds=15.0,
            max_retries=3,
            backoff_factor=1.0,
            max_epoch_age_days=30.0,
            dry_run=False,
        )

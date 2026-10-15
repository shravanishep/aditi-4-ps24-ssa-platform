"""
backend.refresh.metadata — Metadata persistence and tracking for dataset refresh.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SourceRefreshMetadata:
    """Metadata recorded for an individual refreshed data source."""

    source_name: str
    url: str
    dest_path: str
    retrieved_at: str | None = None
    success: bool = False
    error_message: str | None = None
    status_code: int | None = None
    bytes_downloaded: int = 0
    total_records: int = 0
    valid_records: int = 0
    rejected_records: int = 0
    oldest_epoch: str | None = None
    newest_epoch: str | None = None
    max_epoch_age_days: float | None = None
    stale_records_count: int = 0
    classification_source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRefreshMetadata:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RefreshMetadata:
    """Complete metadata for the latest dataset refresh operation."""

    last_refresh_attempt: str | None = None
    last_successful_refresh: str | None = None
    status: str = "unrefreshed"  # "success", "failed", "partial", "unrefreshed"
    sources: dict[str, SourceRefreshMetadata] = field(default_factory=dict)
    summary_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_refresh_attempt": self.last_refresh_attempt,
            "last_successful_refresh": self.last_successful_refresh,
            "status": self.status,
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "summary_notes": self.summary_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RefreshMetadata:
        raw_sources = data.get("sources", {})
        sources = {
            k: SourceRefreshMetadata.from_dict(v) if isinstance(v, dict) else v
            for k, v in raw_sources.items()
        }
        return cls(
            last_refresh_attempt=data.get("last_refresh_attempt"),
            last_successful_refresh=data.get("last_successful_refresh"),
            status=data.get("status", "unrefreshed"),
            sources=sources,
            summary_notes=data.get("summary_notes", []),
        )

    def save(self, path: Path | str) -> None:
        """Atomically persist metadata to JSON file on disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        with tempfile.NamedTemporaryFile(
            "w", dir=target.parent, delete=False, encoding="utf-8", suffix=".tmp"
        ) as tf:
            json.dump(data, tf, indent=2)
            temp_path = Path(tf.name)

        temp_path.replace(target)
        logger.debug("Saved refresh metadata to %s", target)

    @classmethod
    def load(cls, path: Path | str) -> RefreshMetadata:
        """Load metadata from JSON file, returning empty baseline if missing or unreadable."""
        target = Path(path)
        if not target.exists():
            return cls()
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as exc:
            logger.warning("Could not load refresh metadata from %s: %exc", target, exc)
            return cls(
                status="failed",
                summary_notes=[f"Failed reading previous metadata file: {exc}"],
            )

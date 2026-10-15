"""
backend.refresh.service — Automated data refresh workflow with validation and atomic updates.
"""

from __future__ import annotations

import io
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

from backend.catalog.validator import REQUIRED_GP_FIELDS, validate_gp_row
from backend.orbital.gp_loader import parse_epoch
from backend.refresh.config import RefreshConfig, RefreshSourceConfig
from backend.refresh.metadata import RefreshMetadata, SourceRefreshMetadata

logger = logging.getLogger(__name__)


class DataRefreshError(RuntimeError):
    """Raised when data refresh validation or retrieval fails."""


class DataRefreshService:
    """Orchestrates resilient, validated orbital data retrieval and atomic caching."""

    def __init__(
        self,
        config: RefreshConfig | None = None,
        http_client: Any | None = None,
        on_refresh_success: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the data refresh service.

        Parameters
        ----------
        config:
            RefreshConfig instance. Defaults to RefreshConfig.default().
        http_client:
            Optional injectable HTTP client (e.g. requests.Session or MagicMock).
        on_refresh_success:
            Optional callback invoked upon a successful refresh (e.g. cache invalidation).
        """
        self.config = config or RefreshConfig.default()
        self.http_client = http_client
        self.on_refresh_success = on_refresh_success

    def _fetch_with_retries(self, url: str, timeout: float) -> tuple[int, str]:
        """Fetch remote URL with configured retries and exponential backoff.

        Returns
        -------
        tuple[int, str]
            (status_code, response_text)
        """
        max_retries = max(1, self.config.max_retries)
        last_exc: Exception | None = None

        for attempt in range(max_retries):
            try:
                if self.http_client is not None:
                    resp = self.http_client.get(url, timeout=timeout)
                else:
                    resp = requests.get(url, timeout=timeout)

                status_code = getattr(resp, "status_code", 200)
                text = getattr(resp, "text", "")

                if status_code == 200:
                    return status_code, text

                logger.warning(
                    "Fetch attempt %d/%d for %s returned HTTP %d",
                    attempt + 1, max_retries, url, status_code,
                )
                if attempt < max_retries - 1:
                    time.sleep(self.config.backoff_factor * (2**attempt))
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Fetch attempt %d/%d for %s failed: %s",
                    attempt + 1, max_retries, url, exc,
                )
                if attempt < max_retries - 1:
                    time.sleep(self.config.backoff_factor * (2**attempt))

        if last_exc is not None:
            raise DataRefreshError(f"Network error fetching {url} after {max_retries} attempts: {last_exc}") from last_exc
        raise DataRefreshError(f"Remote endpoint {url} returned non-200 status code after {max_retries} attempts.")

    def validate_and_analyze_gp_content(
        self,
        content: str,
        source_cfg: RefreshSourceConfig,
        now: datetime | None = None,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Validate downloaded GP CSV content and compute orbital freshness metrics.

        Raises
        ------
        DataRefreshError
            If content is empty, invalid CSV, missing required fields, or suspiciously truncated.
        """
        if not content or len(content.strip()) == 0:
            raise DataRefreshError(f"Remote response for {source_cfg.source_name} is empty.")

        try:
            df = pd.read_csv(io.StringIO(content))
        except Exception as exc:
            raise DataRefreshError(f"Downloaded content for {source_cfg.source_name} is not a valid CSV: {exc}") from exc

        if len(df) < source_cfg.min_expected_records:
            raise DataRefreshError(
                f"Suspiciously incomplete download for {source_cfg.source_name}: "
                f"contains {len(df)} rows, minimum expected is {source_cfg.min_expected_records}."
            )

        # Validate required GP headers
        missing_cols = [c for c in REQUIRED_GP_FIELDS if c not in df.columns]
        if missing_cols:
            raise DataRefreshError(
                f"Missing required orbital GP columns for {source_cfg.source_name}: {missing_cols}"
            )

        ref_time = now or datetime.now(timezone.utc)
        valid_count = 0
        rejected_count = 0
        parsed_epochs: list[datetime] = []
        epoch_ages_days: list[float] = []

        # Validate rows and extract epoch timestamps
        for _, row in df.iterrows():
            rec, rej = validate_gp_row(row, source_label=source_cfg.source_name, reference_time=ref_time)
            if rec is not None:
                valid_count += 1
                try:
                    dt = parse_epoch(row["EPOCH"])
                    parsed_epochs.append(dt)
                    age = (ref_time - dt).total_seconds() / 86400.0
                    epoch_ages_days.append(age)
                except Exception:
                    pass
            else:
                rejected_count += 1

        if valid_count == 0:
            raise DataRefreshError(
                f"All {len(df)} records in {source_cfg.source_name} failed physical orbital validation."
            )

        stale_threshold = self.config.max_epoch_age_days
        stale_count = sum(1 for age in epoch_ages_days if age > stale_threshold) if stale_threshold else 0
        max_age = max(epoch_ages_days) if epoch_ages_days else None
        oldest_epoch_str = min(parsed_epochs).isoformat() if parsed_epochs else None
        newest_epoch_str = max(parsed_epochs).isoformat() if parsed_epochs else None

        stats = {
            "total_records": len(df),
            "valid_records": valid_count,
            "rejected_records": rejected_count,
            "oldest_epoch": oldest_epoch_str,
            "newest_epoch": newest_epoch_str,
            "max_epoch_age_days": round(max_age, 2) if max_age is not None else None,
            "stale_records_count": stale_count,
            "classification_source": "source_group_hint" if source_cfg.category_hint else "unverified",
        }
        return df, stats

    def validate_and_analyze_satcat_content(
        self,
        content: str,
        source_cfg: RefreshSourceConfig,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Validate downloaded SATCAT CSV content."""
        if not content or len(content.strip()) == 0:
            raise DataRefreshError(f"Remote response for {source_cfg.source_name} is empty.")

        try:
            df = pd.read_csv(io.StringIO(content))
        except Exception as exc:
            raise DataRefreshError(f"Downloaded SATCAT content is not a valid CSV: {exc}") from exc

        if len(df) < source_cfg.min_expected_records:
            raise DataRefreshError(
                f"Suspiciously incomplete SATCAT download: contains {len(df)} rows, "
                f"minimum expected is {source_cfg.min_expected_records}."
            )

        # Check for core SATCAT identification column
        id_candidates = ["NORAD_CAT_ID", "OBJECT_NUMBER", "SATCAT"]
        if not any(c in df.columns for c in id_candidates):
            raise DataRefreshError(
                f"SATCAT download missing identifier column. Columns found: {list(df.columns[:5])}"
            )

        stats = {
            "total_records": len(df),
            "valid_records": len(df),
            "rejected_records": 0,
            "oldest_epoch": None,
            "newest_epoch": None,
            "max_epoch_age_days": None,
            "stale_records_count": 0,
            "classification_source": "satcat",
        }
        return df, stats

    def refresh_source(
        self,
        source_cfg: RefreshSourceConfig,
        dry_run: bool = False,
    ) -> SourceRefreshMetadata:
        """Download, validate, and atomically replace an individual data source.

        Guarantees that an existing valid snapshot is never corrupted or overwritten
        if download or validation fails.
        """
        now = datetime.now(timezone.utc)
        retrieved_at = now.isoformat()
        dest = source_cfg.get_dest_path()

        meta = SourceRefreshMetadata(
            source_name=source_cfg.source_name,
            url=source_cfg.url,
            dest_path=str(dest),
            retrieved_at=retrieved_at,
            success=False,
        )

        try:
            status_code, content = self._fetch_with_retries(
                source_cfg.url, timeout=self.config.http_timeout_seconds
            )
            meta.status_code = status_code
            meta.bytes_downloaded = len(content.encode("utf-8"))

            if source_cfg.is_gp_data:
                _, stats = self.validate_and_analyze_gp_content(content, source_cfg, now=now)
            else:
                _, stats = self.validate_and_analyze_satcat_content(content, source_cfg)

            meta.total_records = stats["total_records"]
            meta.valid_records = stats["valid_records"]
            meta.rejected_records = stats["rejected_records"]
            meta.oldest_epoch = stats["oldest_epoch"]
            meta.newest_epoch = stats["newest_epoch"]
            meta.max_epoch_age_days = stats["max_epoch_age_days"]
            meta.stale_records_count = stats["stale_records_count"]
            meta.classification_source = stats["classification_source"]

            # If validation succeeded and not dry-run: atomically replace destination file
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    "w", dir=dest.parent, delete=False, encoding="utf-8", suffix=".tmp"
                ) as tf:
                    tf.write(content)
                    temp_path = Path(tf.name)

                temp_path.replace(dest)
                logger.info(
                    "Atomically refreshed %s -> %s (%d records)",
                    source_cfg.source_name, dest, meta.valid_records,
                )

            meta.success = True
            return meta

        except Exception as exc:
            logger.error("Refresh failed for source %s: %s", source_cfg.source_name, exc)
            meta.success = False
            meta.error_message = str(exc)
            return meta

    def refresh_all(
        self,
        source_names: list[str] | None = None,
        dry_run: bool | None = None,
    ) -> RefreshMetadata:
        """Execute refresh across all configured (or selected) data sources.

        Parameters
        ----------
        source_names:
            Optional subset of source names to refresh. If None, all enabled sources run.
        dry_run:
            If True, fetches and validates without writing files. Defaults to self.config.dry_run.
        """
        is_dry = self.config.dry_run if dry_run is None else dry_run
        now = datetime.now(timezone.utc)
        meta_path = self.config.get_metadata_path()

        # Load existing metadata or create fresh
        existing = RefreshMetadata.load(meta_path)
        existing.last_refresh_attempt = now.isoformat()

        targets = [
            s for s in self.config.sources
            if s.enabled and (source_names is None or s.source_name in source_names)
        ]

        if not targets:
            existing.summary_notes.append("No active sources selected for refresh.")
            return existing

        required_success = True
        any_success = False

        for s in targets:
            src_meta = self.refresh_source(s, dry_run=is_dry)
            existing.sources[s.source_name] = src_meta
            if src_meta.success:
                any_success = True
            elif s.required:
                required_success = False

        if required_success:
            existing.status = "success"
            existing.last_successful_refresh = now.isoformat()
            if self.on_refresh_success is not None and not is_dry:
                try:
                    self.on_refresh_success()
                except Exception as exc:
                    logger.warning("Cache invalidation callback error: %s", exc)
        elif any_success:
            existing.status = "partial"
        else:
            existing.status = "failed"

        if not is_dry:
            existing.save(meta_path)

        return existing

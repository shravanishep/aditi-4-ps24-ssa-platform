"""
backend.catalog.source_adapter — Local and optional remote dataset ingestion adapter.

Supports reading local GP and SATCAT files, optional remote retrieval from public
CelesTrak endpoints with strict timeout and HTTP error handling, atomic file caching,
and mockable HTTP session interfaces for automated unit testing.
"""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

from backend.catalog.config import GPSourceConfig
from backend.catalog.models import ValidationRejection

logger = logging.getLogger(__name__)


class RemoteIngestionError(RuntimeError):
    """Raised when remote dataset retrieval fails or returns invalid data."""


class SourceAdapter:
    """Ingestion adapter for local and remote orbital and metadata files."""

    def __init__(self, http_client: Any | None = None) -> None:
        """Initialize adapter.

        Parameters
        ----------
        http_client:
            Optional injectable HTTP client (e.g. requests.Session or MagicMock).
            If None, requests.get is used.
        """
        self.http_client = http_client

    def fetch_remote_csv(self, url: str, timeout: float = 10.0) -> str:
        """Fetch remote CSV content as string with timeout and error handling.

        Raises
        ------
        RemoteIngestionError
            On HTTP error, timeout, or empty response.
        """
        try:
            if self.http_client is not None:
                resp = self.http_client.get(url, timeout=timeout)
            else:
                resp = requests.get(url, timeout=timeout)
            
            if resp.status_code != 200:
                raise RemoteIngestionError(
                    f"Remote request to {url} failed with status {resp.status_code}: {resp.text[:200]}"
                )
            content = resp.text
            if not content or len(content.strip()) == 0:
                raise RemoteIngestionError(f"Remote endpoint {url} returned an empty response.")
            return content
        except requests.exceptions.Timeout as exc:
            raise RemoteIngestionError(f"Connection to {url} timed out after {timeout}s: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            raise RemoteIngestionError(f"Network error fetching {url}: {exc}") from exc
        except Exception as exc:
            if isinstance(exc, RemoteIngestionError):
                raise
            raise RemoteIngestionError(f"Unexpected error retrieving {url}: {exc}") from exc

    def fetch_and_cache(
        self,
        url: str,
        dest_path: Path | str,
        timeout: float = 10.0,
    ) -> Path:
        """Fetch remote CSV and atomically write to local cache file.

        Guarantees that an existing local cache is never overwritten or corrupted
        if the network fetch or parsing fails.
        """
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        content = self.fetch_remote_csv(url, timeout=timeout)

        # Write to temporary file in same directory for atomic rename
        with tempfile.NamedTemporaryFile("w", dir=dest.parent, delete=False, encoding="utf-8") as tf:
            tf.write(content)
            temp_path = Path(tf.name)

        try:
            # Validate basic CSV readability before replacing
            pd.read_csv(temp_path, nrows=2)
            temp_path.replace(dest)
            logger.info("Successfully cached remote dataset from %s to %s", url, dest)
            return dest
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink()
            raise RemoteIngestionError(
                f"Fetched content from {url} is not a valid CSV: {exc}"
            ) from exc

    def load_local_csv(self, path: Path | str) -> pd.DataFrame:
        """Load local CSV file into pandas DataFrame."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Local file does not exist: {p}")
        return pd.read_csv(p)

    def load_gp_source(
        self,
        config: GPSourceConfig,
        allow_remote: bool = False,
        timeout: float = 10.0,
    ) -> tuple[pd.DataFrame | None, list[ValidationRejection]]:
        """Load a GP dataset from configured local path or remote URL."""
        rejections: list[ValidationRejection] = []
        p = config.get_path()

        if p is not None and p.exists():
            try:
                df = self.load_local_csv(p)
                return df, rejections
            except Exception as exc:
                rejections.append(
                    ValidationRejection(
                        source=config.source_name,
                        identifier=str(p),
                        reason=f"Failed to read local GP CSV: {exc}",
                    )
                )

        # Fall back to remote fetch if configured and permitted
        if allow_remote and config.remote_url:
            try:
                content = self.fetch_remote_csv(config.remote_url, timeout=timeout)
                df = pd.read_csv(io.StringIO(content))
                return df, rejections
            except Exception as exc:
                rejections.append(
                    ValidationRejection(
                        source=config.source_name,
                        identifier=config.remote_url,
                        reason=f"Remote ingestion failed: {exc}",
                    )
                )

        return None, rejections

    def load_satcat_source(
        self,
        satcat_path: Path | str | None,
        remote_url: str | None = None,
        allow_remote: bool = False,
        timeout: float = 10.0,
    ) -> tuple[pd.DataFrame | None, list[ValidationRejection]]:
        """Load SATCAT metadata from local path or optional remote URL."""
        rejections: list[ValidationRejection] = []

        if satcat_path is not None:
            p = Path(satcat_path)
            if p.exists():
                try:
                    df = self.load_local_csv(p)
                    return df, rejections
                except Exception as exc:
                    rejections.append(
                        ValidationRejection(
                            source="satcat_local",
                            identifier=str(p),
                            reason=f"Failed reading SATCAT CSV: {exc}",
                        )
                    )

        if allow_remote and remote_url:
            try:
                content = self.fetch_remote_csv(remote_url, timeout=timeout)
                df = pd.read_csv(io.StringIO(content))
                return df, rejections
            except Exception as exc:
                rejections.append(
                    ValidationRejection(
                        source="satcat_remote",
                        identifier=remote_url,
                        reason=f"Remote SATCAT ingestion failed: {exc}",
                    )
                )

        return None, rejections

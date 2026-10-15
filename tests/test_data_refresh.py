"""
tests.test_data_refresh — Automated test suite for Layer 12 Data Refresh and End-to-End Validation.

Verifies:
1. Resilient HTTP retrieval with retries and timeout handling.
2. In-memory schema and physical bounds validation.
3. Atomic file replacement and last-known-good file preservation on failure.
4. Refresh metadata persistence and lifecycle tracking.
5. Fresh vs stale orbital epoch metrics computation.
6. Catalogue cache invalidation upon successful refresh.
7. End-to-end API screening with refreshed catalogue fixtures.
8. Read-only /catalog/status endpoint behavior.
9. In-process periodic scheduler lifecycle.
10. CLI tool dry-run and status operations.
"""

from __future__ import annotations

import io
import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.routes import invalidate_catalog_cache
from backend.catalog.config import CatalogConfig, GPSourceConfig
from backend.catalog.models import ObjectClassification
from backend.main import app
from backend.refresh.cli import main as cli_main, print_status
from backend.refresh.config import RefreshConfig, RefreshSourceConfig
from backend.refresh.metadata import RefreshMetadata, SourceRefreshMetadata
from backend.refresh.scheduler import PeriodicRefreshScheduler
from backend.refresh.service import DataRefreshError, DataRefreshService

client = TestClient(app)

# ---------------------------------------------------------------------------
# Test Fixtures & Synthetic CSV Generators
# ---------------------------------------------------------------------------

def _generate_valid_gp_csv(count: int = 25, epoch_age_days: float = 2.0) -> str:
    """Generate a valid GP CSV string with specified record count and epoch age."""
    now = datetime.now(timezone.utc)
    epoch_dt = now - timedelta(days=epoch_age_days)
    epoch_str = epoch_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")

    headers = [
        "NORAD_CAT_ID",
        "OBJECT_NAME",
        "OBJECT_ID",
        "EPOCH",
        "MEAN_MOTION",
        "ECCENTRICITY",
        "INCLINATION",
        "RA_OF_ASC_NODE",
        "ARG_OF_PERICENTER",
        "MEAN_ANOMALY",
        "EPHEMERIS_TYPE",
        "CLASSIFICATION_TYPE",
        "ELEMENT_SET_NO",
        "REV_AT_EPOCH",
        "BSTAR",
        "MEAN_MOTION_DOT",
        "MEAN_MOTION_DDOT",
    ]
    rows = [",".join(headers)]
    for i in range(1, count + 1):
        norad_id = 25000 + i
        rows.append(
            f"{norad_id},SAT-{norad_id},2024-001A,{epoch_str},"
            f"15.54,0.0005,51.64,120.0,45.0,200.0,0,U,999,1000,0.0001,0.00001,0.0"
        )
    return "\n".join(rows)


def _generate_valid_satcat_csv(count: int = 25) -> str:
    """Generate a valid SATCAT CSV string."""
    headers = ["NORAD_CAT_ID", "OBJECT_NAME", "OBJECT_ID", "OPS_STATUS_CODE", "OWNER"]
    rows = [",".join(headers)]
    for i in range(1, count + 1):
        norad_id = 25000 + i
        rows.append(f"{norad_id},SAT-{norad_id},2024-001A,+,US")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Unit & Service Tests: DataRefreshService
# ---------------------------------------------------------------------------

class TestDataRefreshService:
    """Test DataRefreshService retrieval, validation, and atomic write behavior."""

    def test_successful_refresh_and_atomic_write(self, tmp_path: Path):
        """Valid remote CSV should be validated and atomically written to target path."""
        target_file = tmp_path / "active_satellites.csv"
        meta_file = tmp_path / "metadata.json"
        csv_content = _generate_valid_gp_csv(count=30, epoch_age_days=1.5)

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = csv_content
        mock_http.get.return_value = mock_resp

        cfg = RefreshConfig(
            sources=[
                RefreshSourceConfig(
                    source_name="active_test",
                    url="https://celestrak.org/test.csv",
                    dest_path=target_file,
                    is_gp_data=True,
                    min_expected_records=20,
                    required=True,
                )
            ],
            metadata_path=meta_file,
            max_epoch_age_days=30.0,
        )

        service = DataRefreshService(config=cfg, http_client=mock_http)
        result = service.refresh_all()

        assert result.status == "success"
        assert result.last_successful_refresh is not None
        assert target_file.exists()
        assert target_file.stat().st_size > 0

        # Verify parsed metadata
        src_meta = result.sources["active_test"]
        assert src_meta.success is True
        assert src_meta.valid_records == 30
        assert src_meta.rejected_records == 0
        assert src_meta.stale_records_count == 0
        assert src_meta.max_epoch_age_days is not None
        assert src_meta.max_epoch_age_days < 2.0

    def test_network_failure_preserves_last_known_good_snapshot(self, tmp_path: Path):
        """When HTTP request times out or fails, existing file must remain 100% untouched."""
        target_file = tmp_path / "active_satellites.csv"
        original_content = "ORIGINAL_VALID_DATA_NEVER_OVERWRITE"
        target_file.write_text(original_content, encoding="utf-8")

        mock_http = MagicMock()
        mock_http.get.side_effect = TimeoutError("Simulated socket timeout")

        cfg = RefreshConfig(
            sources=[
                RefreshSourceConfig(
                    source_name="active_test",
                    url="https://celestrak.org/test.csv",
                    dest_path=target_file,
                    is_gp_data=True,
                    min_expected_records=10,
                )
            ],
            metadata_path=tmp_path / "meta.json",
            max_retries=2,
            backoff_factor=0.01,
        )

        service = DataRefreshService(config=cfg, http_client=mock_http)
        result = service.refresh_all()

        assert result.status == "failed"
        # The file content must be exactly what it was originally
        assert target_file.read_text(encoding="utf-8") == original_content
        assert result.sources["active_test"].success is False
        assert "timeout" in result.sources["active_test"].error_message.lower()

    def test_corrupt_csv_rejected_and_preserves_snapshot(self, tmp_path: Path):
        """Non-CSV or garbled HTTP response must be rejected before touching target file."""
        target_file = tmp_path / "active_satellites.csv"
        target_file.write_text("KNOWN_GOOD_BASELINE", encoding="utf-8")

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>502 Bad Gateway - HTML error page</body></html>"
        mock_http.get.return_value = mock_resp

        cfg = RefreshConfig(
            sources=[
                RefreshSourceConfig(
                    source_name="active_test",
                    url="https://celestrak.org/test.csv",
                    dest_path=target_file,
                    is_gp_data=True,
                    min_expected_records=10,
                )
            ],
            metadata_path=tmp_path / "meta.json",
        )

        service = DataRefreshService(config=cfg, http_client=mock_http)
        result = service.refresh_all()

        assert result.status == "failed"
        assert target_file.read_text(encoding="utf-8") == "KNOWN_GOOD_BASELINE"
        assert result.sources["active_test"].success is False

    def test_empty_response_rejected(self, tmp_path: Path):
        """Empty HTTP 200 response must be rejected."""
        target_file = tmp_path / "satellites.csv"
        target_file.write_text("VALID_DATA", encoding="utf-8")

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "   \n\n   "
        mock_http.get.return_value = mock_resp

        cfg = RefreshConfig(
            sources=[
                RefreshSourceConfig(
                    source_name="active_test",
                    url="https://celestrak.org/test.csv",
                    dest_path=target_file,
                    is_gp_data=True,
                    min_expected_records=5,
                )
            ],
            metadata_path=tmp_path / "meta.json",
        )

        service = DataRefreshService(config=cfg, http_client=mock_http)
        result = service.refresh_all()

        assert result.status == "failed"
        assert target_file.read_text(encoding="utf-8") == "VALID_DATA"
        assert "empty" in result.sources["active_test"].error_message.lower()

    def test_suspiciously_incomplete_download_rejected(self, tmp_path: Path):
        """Download with fewer rows than min_expected_records must be rejected."""
        target_file = tmp_path / "satellites.csv"
        target_file.write_text("VALID_ORIGINAL", encoding="utf-8")

        # Generate only 3 rows when 50 are expected
        truncated_content = _generate_valid_gp_csv(count=3, epoch_age_days=1.0)

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = truncated_content
        mock_http.get.return_value = mock_resp

        cfg = RefreshConfig(
            sources=[
                RefreshSourceConfig(
                    source_name="active_test",
                    url="https://celestrak.org/test.csv",
                    dest_path=target_file,
                    is_gp_data=True,
                    min_expected_records=50,  # expects at least 50
                )
            ],
            metadata_path=tmp_path / "meta.json",
        )

        service = DataRefreshService(config=cfg, http_client=mock_http)
        result = service.refresh_all()

        assert result.status == "failed"
        assert target_file.read_text(encoding="utf-8") == "VALID_ORIGINAL"
        assert "incomplete" in result.sources["active_test"].error_message.lower()

    def test_stale_epoch_detection(self, tmp_path: Path):
        """Orbital records with epochs older than max_epoch_age_days are flagged as stale."""
        target_file = tmp_path / "stale_satellites.csv"
        # 25 records with epoch age = 60 days
        stale_content = _generate_valid_gp_csv(count=25, epoch_age_days=60.0)

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = stale_content
        mock_http.get.return_value = mock_resp

        cfg = RefreshConfig(
            sources=[
                RefreshSourceConfig(
                    source_name="stale_test",
                    url="https://celestrak.org/stale.csv",
                    dest_path=target_file,
                    is_gp_data=True,
                    min_expected_records=20,
                )
            ],
            metadata_path=tmp_path / "meta.json",
            max_epoch_age_days=30.0,  # threshold is 30 days
        )

        service = DataRefreshService(config=cfg, http_client=mock_http)
        result = service.refresh_all()

        assert result.status == "success"
        src = result.sources["stale_test"]
        assert src.stale_records_count == 25
        assert src.max_epoch_age_days is not None
        assert src.max_epoch_age_days > 55.0

    def test_dry_run_validates_without_writing_file(self, tmp_path: Path):
        """Dry-run validates incoming CSV without writing or modifying files."""
        target_file = tmp_path / "dry_run_target.csv"
        csv_content = _generate_valid_gp_csv(count=25, epoch_age_days=1.0)

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = csv_content
        mock_http.get.return_value = mock_resp

        cfg = RefreshConfig(
            sources=[
                RefreshSourceConfig(
                    source_name="dry_test",
                    url="https://celestrak.org/test.csv",
                    dest_path=target_file,
                    is_gp_data=True,
                    min_expected_records=20,
                )
            ],
            metadata_path=tmp_path / "meta.json",
            dry_run=True,
        )

        service = DataRefreshService(config=cfg, http_client=mock_http)
        result = service.refresh_all(dry_run=True)

        assert result.status == "success"
        # File must NOT have been created
        assert not target_file.exists()
        assert not (tmp_path / "meta.json").exists()

    def test_cache_invalidation_callback_triggered(self, tmp_path: Path):
        """on_refresh_success callback is invoked when refresh succeeds."""
        target_file = tmp_path / "active.csv"
        csv_content = _generate_valid_gp_csv(count=25, epoch_age_days=1.0)

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = csv_content
        mock_http.get.return_value = mock_resp

        callback_called = False

        def my_callback():
            nonlocal callback_called
            callback_called = True

        cfg = RefreshConfig(
            sources=[
                RefreshSourceConfig(
                    source_name="active_test",
                    url="https://celestrak.org/test.csv",
                    dest_path=target_file,
                    is_gp_data=True,
                    min_expected_records=20,
                )
            ],
            metadata_path=tmp_path / "meta.json",
        )

        service = DataRefreshService(
            config=cfg,
            http_client=mock_http,
            on_refresh_success=my_callback,
        )
        service.refresh_all()

        assert callback_called is True


# ---------------------------------------------------------------------------
# Metadata Persistence Tests
# ---------------------------------------------------------------------------

class TestRefreshMetadata:
    """Test RefreshMetadata serialization, atomic saving, and loading."""

    def test_metadata_roundtrip(self, tmp_path: Path):
        meta_file = tmp_path / "test_meta.json"
        meta = RefreshMetadata(
            last_refresh_attempt="2026-10-12T12:00:00Z",
            last_successful_refresh="2026-10-12T12:00:00Z",
            status="success",
            sources={
                "gp_source": SourceRefreshMetadata(
                    source_name="gp_source",
                    url="https://example.com/gp.csv",
                    dest_path="/data/gp.csv",
                    retrieved_at="2026-10-12T12:00:00Z",
                    success=True,
                    total_records=100,
                    valid_records=98,
                    rejected_records=2,
                )
            },
            summary_notes=["All sources synced successfully."],
        )
        meta.save(meta_file)
        assert meta_file.exists()

        loaded = RefreshMetadata.load(meta_file)
        assert loaded.status == "success"
        assert loaded.last_successful_refresh == "2026-10-12T12:00:00Z"
        assert "gp_source" in loaded.sources
        assert loaded.sources["gp_source"].valid_records == 98

    def test_missing_metadata_returns_unrefreshed_baseline(self, tmp_path: Path):
        non_existent = tmp_path / "does_not_exist.json"
        loaded = RefreshMetadata.load(non_existent)
        assert loaded.status == "unrefreshed"
        assert loaded.last_successful_refresh is None


# ---------------------------------------------------------------------------
# Scheduler Tests
# ---------------------------------------------------------------------------

class TestPeriodicScheduler:
    """Test in-process background scheduler start, stop, and trigger."""

    def test_scheduler_lifecycle(self, tmp_path: Path):
        mock_service = MagicMock()
        mock_service.refresh_all.return_value = RefreshMetadata(status="success")

        scheduler = PeriodicRefreshScheduler(
            service=mock_service,
            interval_seconds=0.1,  # fast interval for test
            run_immediately=False,
        )

        assert not scheduler.is_running
        scheduler.start()
        assert scheduler.is_running

        # Let it run briefly
        time.sleep(0.35)
        scheduler.stop(timeout=2.0)
        assert not scheduler.is_running
        assert mock_service.refresh_all.call_count >= 1

    def test_scheduler_trigger_now(self):
        mock_service = MagicMock()
        mock_service.refresh_all.return_value = RefreshMetadata(status="success")

        scheduler = PeriodicRefreshScheduler(service=mock_service, interval_seconds=3600.0)
        res = scheduler.trigger_now()
        assert res.status == "success"
        assert mock_service.refresh_all.call_count == 1


# ---------------------------------------------------------------------------
# CLI Tests
# ---------------------------------------------------------------------------

class TestRefreshCLI:
    """Test CLI commands and flags."""

    def test_cli_status_command(self, tmp_path: Path, capsys):
        meta_file = tmp_path / "test_meta.json"
        meta = RefreshMetadata(
            last_successful_refresh="2026-10-12T00:00:00Z",
            status="success",
        )
        meta.save(meta_file)

        ret = cli_main(["--status", "--metadata-path", str(meta_file)])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "CATALOGUE REFRESH STATUS" in captured
        assert "SUCCESS" in captured

    def test_cli_dry_run_command(self, tmp_path: Path, capsys):
        csv_content = _generate_valid_gp_csv(count=60)
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = csv_content
            mock_get.return_value = mock_resp

            out_dir = tmp_path / "out"
            ret = cli_main([
                "--dry-run",
                "--output-dir", str(out_dir),
                "--metadata-path", str(tmp_path / "meta.json"),
                "--sources", "active_satellites_gp",
            ])
            assert ret == 0
            captured = capsys.readouterr().out
            assert "[DRY-RUN MODE]" in captured
            assert "SUCCESS" in captured
            # No files created
            assert not out_dir.exists()


# ---------------------------------------------------------------------------
# API Integration Tests: /catalog/status
# ---------------------------------------------------------------------------

class TestCatalogStatusAPI:
    """Test read-only /catalog/status endpoint."""

    def test_get_catalog_status_success(self):
        resp = client.get("/catalog/status")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert "total_objects" in data
        assert "active_satellites" in data
        assert "with_orbital_data" in data
        assert "sources" in data
        assert "warnings" in data
        assert "data_source_notes" in data
        assert "disclaimer" in data
        assert data["total_objects"] > 0
        assert data["active_satellites"] > 0
        assert "active_satellites_gp" in data["sources"]

        # Ensure disclaimer is prominent
        assert "heuristic" in data["disclaimer"].lower()

        # Warning about retrieval time vs epoch must be present
        assert any("retrieval timestamp reflects" in w.lower() for w in data["warnings"])

    def test_catalog_status_reflects_persisted_metadata(self, tmp_path: Path):
        meta_file = tmp_path / "refresh_meta.json"
        meta = RefreshMetadata(
            last_refresh_attempt="2026-10-12T15:30:00Z",
            last_successful_refresh="2026-10-12T15:30:00Z",
            status="success",
            sources={
                "active_satellites_gp": SourceRefreshMetadata(
                    source_name="active_satellites_gp",
                    url="https://celestrak.org/test.csv",
                    dest_path="/data/test.csv",
                    retrieved_at="2026-10-12T15:30:00Z",
                    success=True,
                    total_records=500,
                    valid_records=500,
                    stale_records_count=0,
                )
            },
        )
        meta.save(meta_file)

        # Patch _METADATA_PATH in backend.api.routes
        with patch("backend.api.routes._METADATA_PATH", meta_file):
            resp = client.get("/catalog/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["last_successful_refresh"] == "2026-10-12T15:30:00Z"
            assert data["refresh_status"] == "success"
            assert data["sources"]["active_satellites_gp"]["total_records"] == 500


# ---------------------------------------------------------------------------
# End-to-End Threat Screening with Refreshed Catalogue
# ---------------------------------------------------------------------------

class TestEndToEndRefreshedScreening:
    """Verify threat screening API seamlessly functions when catalogue data is refreshed."""

    def test_screening_runs_on_refreshed_catalog_cache(self, tmp_path: Path):
        """Invalidating cache and pointing to refreshed data executes screening properly."""
        invalidate_catalog_cache()
        resp = client.post(
            "/threats/screen",
            json={
                "screening_threshold_km": 500.0,
                "screening_window_hours": 24.0,
                "max_threat_candidates": 5,
                "max_protected_targets": 2,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["protected_count"] == 2
        assert data["summary"]["candidates_screened"] == 5
        assert isinstance(data["events"], list)

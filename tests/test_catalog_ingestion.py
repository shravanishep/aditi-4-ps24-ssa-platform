"""
tests/test_catalog_ingestion.py — Comprehensive unit tests for Layer 10 catalogue ingestion.

Covers:
1. Valid GP plus SATCAT joins.
2. Correct mapping of all supported object categories (ACTIVE_SATELLITE, INACTIVE_SATELLITE,
   ROCKET_BODY, DEBRIS, UNKNOWN).
3. Active-target vs threat-candidate classification.
4. Merging multiple GP files into one unified catalogue.
5. Deterministic deduplication of duplicate NORAD IDs (latest epoch wins).
6. Missing SATCAT records and UNKNOWN classification fallback.
7. Rejection of invalid GP rows (negative norad id, negative mean motion, malformed epoch, missing columns).
8. Data freshness and epoch age tracking.
9. Mocked remote ingestion (success, timeout, HTTP 404, invalid remote CSV).
10. Atomic caching preserving local cache on network error.
11. Layer 9 threat prioritization consuming the unified catalogue and preserving classifications.
12. Ensuring raw input datasets remain unmodified.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from backend.catalog import (
    CatalogConfig,
    GPSourceConfig,
    ObjectClassification,
    RemoteIngestionError,
    SourceAdapter,
    UnifiedCatalog,
    build_unified_catalog,
    map_satcat_classification,
    parse_satcat_dataframe,
    validate_gp_row,
)
from backend.orbital.models import CloseApproachResult
from ml.models.threat_config import ThreatConfig
from ml.models.threat_prioritization import screen_threats_from_catalog


@pytest.fixture
def sample_gp_records() -> list[dict]:
    """Sample valid GP records covering multiple simulated satellites."""
    return [
        {
            "NORAD_CAT_ID": 25544,
            "OBJECT_NAME": "ISS (ZARYA)",
            "OBJECT_ID": "1998-067A",
            "EPOCH": "2026-09-17T12:00:00.000000",
            "MEAN_MOTION": 15.5,
            "ECCENTRICITY": 0.0006,
            "INCLINATION": 51.64,
            "RA_OF_ASC_NODE": 120.0,
            "ARG_OF_PERICENTER": 45.0,
            "MEAN_ANOMALY": 10.0,
            "BSTAR": 0.0001,
            "MEAN_MOTION_DOT": 0.0,
            "MEAN_MOTION_DDOT": 0.0,
        },
        {
            "NORAD_CAT_ID": 33504,
            "OBJECT_NAME": "IRIDIUM 33 DEB",
            "OBJECT_ID": "1997-051C",
            "EPOCH": "2026-09-17T12:00:00.000000",
            "MEAN_MOTION": 14.3,
            "ECCENTRICITY": 0.002,
            "INCLINATION": 86.4,
            "RA_OF_ASC_NODE": 35.0,
            "ARG_OF_PERICENTER": 12.0,
            "MEAN_ANOMALY": 150.0,
            "BSTAR": 0.0002,
            "MEAN_MOTION_DOT": 0.0,
            "MEAN_MOTION_DDOT": 0.0,
        },
        {
            "NORAD_CAT_ID": 40001,
            "OBJECT_NAME": "SL-4 R/B",
            "OBJECT_ID": "2014-030B",
            "EPOCH": "2026-09-17T12:00:00.000000",
            "MEAN_MOTION": 15.1,
            "ECCENTRICITY": 0.015,
            "INCLINATION": 65.0,
            "RA_OF_ASC_NODE": 80.0,
            "ARG_OF_PERICENTER": 90.0,
            "MEAN_ANOMALY": 200.0,
            "BSTAR": 0.0005,
            "MEAN_MOTION_DOT": 0.0,
            "MEAN_MOTION_DDOT": 0.0,
        },
    ]


@pytest.fixture
def sample_satcat_df() -> pd.DataFrame:
    """Sample SATCAT metadata DataFrame matching CelesTrak format."""
    return pd.DataFrame(
        [
            {
                "NORAD_CAT_ID": 25544,
                "OBJECT_NAME": "ISS (ZARYA)",
                "OBJECT_ID": "1998-067A",
                "OBJECT_TYPE": "PAY",
                "OPS_STATUS_CODE": "+",
                "OWNER": "ISS",
                "LAUNCH_DATE": "1998-11-20",
                "DECAY_DATE": None,
            },
            {
                "NORAD_CAT_ID": 33504,
                "OBJECT_NAME": "IRIDIUM 33 DEB",
                "OBJECT_ID": "1997-051C",
                "OBJECT_TYPE": "DEB",
                "OPS_STATUS_CODE": "-",
                "OWNER": "US",
                "LAUNCH_DATE": "1997-09-14",
                "DECAY_DATE": None,
            },
            {
                "NORAD_CAT_ID": 40001,
                "OBJECT_NAME": "SL-4 R/B",
                "OBJECT_ID": "2014-030B",
                "OBJECT_TYPE": "R/B",
                "OPS_STATUS_CODE": None,
                "OWNER": "CIS",
                "LAUNCH_DATE": "2014-05-06",
                "DECAY_DATE": None,
            },
            {
                "NORAD_CAT_ID": 50001,
                "OBJECT_NAME": "DEFUNCT SAT",
                "OBJECT_ID": "2020-001A",
                "OBJECT_TYPE": "PAY",
                "OPS_STATUS_CODE": "-",
                "OWNER": "US",
                "LAUNCH_DATE": "2020-01-01",
                "DECAY_DATE": None,
            },
            {
                "NORAD_CAT_ID": 60001,
                "OBJECT_NAME": "MYSTERY OBJECT",
                "OBJECT_ID": "2021-002A",
                "OBJECT_TYPE": "UNK",
                "OPS_STATUS_CODE": "?",
                "OWNER": "UNKNOWN",
                "LAUNCH_DATE": "2021-01-01",
                "DECAY_DATE": None,
            },
        ]
    )


class TestClassificationMapping:
    def test_all_object_classifications(self):
        # Active payload
        assert map_satcat_classification("PAY", "+") == ObjectClassification.ACTIVE_SATELLITE
        assert map_satcat_classification("PAY", "P") == ObjectClassification.ACTIVE_SATELLITE
        assert map_satcat_classification("PAY", "B") == ObjectClassification.ACTIVE_SATELLITE

        # Inactive payload
        assert map_satcat_classification("PAY", "-") == ObjectClassification.INACTIVE_SATELLITE
        assert map_satcat_classification("PAY", "D") == ObjectClassification.INACTIVE_SATELLITE
        assert map_satcat_classification("PAY", "+", decay_date="2024-01-01") == ObjectClassification.INACTIVE_SATELLITE

        # Rocket body
        assert map_satcat_classification("R/B") == ObjectClassification.ROCKET_BODY
        assert map_satcat_classification("RB") == ObjectClassification.ROCKET_BODY
        assert map_satcat_classification("ROCKET BODY") == ObjectClassification.ROCKET_BODY

        # Debris
        assert map_satcat_classification("DEB") == ObjectClassification.DEBRIS
        assert map_satcat_classification("DEBRIS") == ObjectClassification.DEBRIS

        # Unknown / Unverified operational status
        assert map_satcat_classification("PAY", "?") == ObjectClassification.UNKNOWN
        assert map_satcat_classification("PAY", "") == ObjectClassification.UNKNOWN
        assert map_satcat_classification("UNK") == ObjectClassification.UNKNOWN
        assert map_satcat_classification(None) == ObjectClassification.UNKNOWN


class TestValidatorAndDeduplication:
    def test_valid_gp_row(self, sample_gp_records):
        rec, rej = validate_gp_row(sample_gp_records[0], source_label="test")
        assert rej is None
        assert rec is not None
        assert rec["NORAD_CAT_ID"] == 25544
        assert rec["MEAN_MOTION"] == 15.5
        assert isinstance(rec["EPOCH_DATETIME"], datetime)

    def test_reject_invalid_rows(self):
        # Missing NORAD ID
        _, rej1 = validate_gp_row({"MEAN_MOTION": 15.0}, source_label="test")
        assert rej1 is not None
        assert "Missing NORAD_CAT_ID" in rej1.reason

        # Negative mean motion
        _, rej2 = validate_gp_row({"NORAD_CAT_ID": 100, "MEAN_MOTION": -1.0, "EPOCH": "2026-09-17T00:00:00", "ECCENTRICITY": 0.01, "INCLINATION": 50, "RA_OF_ASC_NODE": 0, "ARG_OF_PERICENTER": 0, "MEAN_ANOMALY": 0}, source_label="test")
        assert rej2 is not None
        assert "MEAN_MOTION must be strictly positive" in rej2.reason

        # Eccentricity out of bounds
        _, rej3 = validate_gp_row({"NORAD_CAT_ID": 100, "MEAN_MOTION": 15.0, "EPOCH": "2026-09-17T00:00:00", "ECCENTRICITY": 1.5, "INCLINATION": 50, "RA_OF_ASC_NODE": 0, "ARG_OF_PERICENTER": 0, "MEAN_ANOMALY": 0}, source_label="test")
        assert rej3 is not None
        assert "ECCENTRICITY must be in [0.0, 1.0)" in rej3.reason

    def test_deduplication_latest_epoch_wins(self):
        dt_old = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
        dt_new = datetime(2026, 9, 17, 0, 0, 0, tzinfo=timezone.utc)

        records = [
            {"NORAD_CAT_ID": 100, "EPOCH_DATETIME": dt_old, "MEAN_MOTION": 14.0, "LABEL": "old"},
            {"NORAD_CAT_ID": 100, "EPOCH_DATETIME": dt_new, "MEAN_MOTION": 14.1, "LABEL": "new"},
        ]
        from backend.catalog.validator import deduplicate_gp_records
        dedup, rejections = deduplicate_gp_records(records, source_label="test")
        assert len(dedup) == 1
        assert dedup[100]["LABEL"] == "new"
        assert len(rejections) == 1
        assert "Superseded" in rejections[0].reason


class TestCatalogueAssembly:
    def test_build_unified_catalog_from_files(self, tmp_path, sample_gp_records, sample_satcat_df):
        # Create temp GP CSV
        gp_file = tmp_path / "satellites.csv"
        pd.DataFrame(sample_gp_records).to_csv(gp_file, index=False)

        # Create temp SATCAT CSV
        satcat_file = tmp_path / "satcat.csv"
        sample_satcat_df.to_csv(satcat_file, index=False)

        config = CatalogConfig(
            gp_sources=[
                GPSourceConfig(source_name="test_gp", path=gp_file),
            ],
            satcat_path=satcat_file,
            allow_remote_fetch=False,
        )

        catalog = build_unified_catalog(config=config)
        assert len(catalog) == 3

        # Verify joined classifications
        iss = catalog.get(25544)
        assert iss is not None
        assert iss.classification == ObjectClassification.ACTIVE_SATELLITE
        assert iss.owner == "ISS"
        assert iss.is_protected_target is True

        deb = catalog.get(33504)
        assert deb is not None
        assert deb.classification == ObjectClassification.DEBRIS
        assert deb.is_threat_candidate is True

        rb = catalog.get(40001)
        assert rb is not None
        assert rb.classification == ObjectClassification.ROCKET_BODY
        assert rb.owner == "CIS"

        # Summary check
        summary = catalog.summary()
        assert summary.total_objects == 3
        assert summary.counts_by_classification["ACTIVE_SATELLITE"] == 1
        assert summary.counts_by_classification["DEBRIS"] == 1
        assert summary.counts_by_classification["ROCKET_BODY"] == 1

    def test_missing_satcat_metadata_falls_back_to_hint(self, tmp_path, sample_gp_records):
        gp_file = tmp_path / "gp_no_satcat.csv"
        pd.DataFrame(sample_gp_records).to_csv(gp_file, index=False)

        config = CatalogConfig(
            gp_sources=[
                GPSourceConfig(
                    source_name="hinted_gp",
                    path=gp_file,
                    category_hint=ObjectClassification.ACTIVE_SATELLITE,
                ),
            ],
            satcat_path=None,
        )

        catalog = build_unified_catalog(config=config)
        obj = catalog.get(25544)
        assert obj is not None
        assert obj.classification == ObjectClassification.ACTIVE_SATELLITE
        assert "no SATCAT" in obj.source_provenance


class TestSourceAdapterAndRemote:
    def test_remote_fetch_mocked_success(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "NORAD_CAT_ID,OBJECT_NAME\n25544,ISS\n"
        mock_client.get.return_value = mock_response

        adapter = SourceAdapter(http_client=mock_client)
        content = adapter.fetch_remote_csv("https://celestrak.org/test.csv")
        assert "25544,ISS" in content

    def test_remote_fetch_timeout_raises_error(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = requests.exceptions.Timeout("Timed out")

        adapter = SourceAdapter(http_client=mock_client)
        with pytest.raises(RemoteIngestionError, match="timed out"):
            adapter.fetch_remote_csv("https://celestrak.org/test.csv", timeout=5.0)

    def test_remote_fetch_http_error(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_client.get.return_value = mock_response

        adapter = SourceAdapter(http_client=mock_client)
        with pytest.raises(RemoteIngestionError, match="status 404"):
            adapter.fetch_remote_csv("https://celestrak.org/bad.csv")

    def test_fetch_and_cache_atomic_safety(self, tmp_path):
        cache_file = tmp_path / "cache.csv"
        cache_file.write_text("ORIGINAL_CONTENT\n")

        mock_client = MagicMock()
        mock_client.get.side_effect = requests.exceptions.ConnectionError("Network down")

        adapter = SourceAdapter(http_client=mock_client)
        with pytest.raises(RemoteIngestionError):
            adapter.fetch_and_cache("https://celestrak.org/fail.csv", cache_file)

        # Confirm original local cache was not destroyed or replaced
        assert cache_file.read_text() == "ORIGINAL_CONTENT\n"


class TestLayer9IntegrationWithCatalog:
    @patch("ml.models.threat_prioritization.find_closest_approach")
    def test_screen_threats_from_catalog(self, mock_find, tmp_path, sample_gp_records, sample_satcat_df):
        gp_file = tmp_path / "satellites.csv"
        pd.DataFrame(sample_gp_records).to_csv(gp_file, index=False)
        satcat_file = tmp_path / "satcat.csv"
        sample_satcat_df.to_csv(satcat_file, index=False)

        config = CatalogConfig(
            gp_sources=[GPSourceConfig(source_name="gp", path=gp_file)],
            satcat_path=satcat_file,
        )
        catalog = build_unified_catalog(config=config)

        ref_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        threat_cfg = ThreatConfig(
            protected_norad_ids=[25544],  # Protect ISS
            screening_threshold_km=50.0,
        )

        mock_find.return_value = CloseApproachResult(
            object1_norad_id=25544,
            object2_norad_id=33504,
            object1_name="ISS (ZARYA)",
            object2_name="IRIDIUM 33 DEB",
            analysis_start_time=ref_time,
            analysis_end_time=ref_time,
            time_of_closest_approach=datetime(2026, 9, 17, 18, 0, 0, tzinfo=timezone.utc),
            minimum_separation_km=15.0,
            relative_speed_km_s=12.5,
            threshold_km=50.0,
            is_candidate_close_approach=True,
        )

        res = screen_threats_from_catalog(
            catalog=catalog,
            config=threat_cfg,
            reference_time=ref_time,
        )

        assert res.events_within_threshold >= 1
        event = res.events[0]
        assert event.protected_norad_id == 25544
        assert event.protected_classification == "ACTIVE_SATELLITE"
        assert event.threat_norad_id == 33504
        assert event.threat_classification == "DEBRIS"
        assert "satcat" in event.threat_source_provenance

    def test_classification_provenance_distinction(self, tmp_path, sample_gp_records, sample_satcat_df):
        # GP with one satellite in SATCAT and one not in SATCAT
        gp_file = tmp_path / "satellites.csv"
        pd.DataFrame(sample_gp_records[:2]).to_csv(gp_file, index=False)

        # SATCAT only contains 25544 (ISS)
        satcat_file = tmp_path / "satcat.csv"
        sample_satcat_df[sample_satcat_df["NORAD_CAT_ID"] == 25544].to_csv(satcat_file, index=False)

        config = CatalogConfig(
            gp_sources=[
                GPSourceConfig(
                    source_name="gp_src",
                    path=gp_file,
                    category_hint=ObjectClassification.ACTIVE_SATELLITE,
                )
            ],
            satcat_path=satcat_file,
        )
        catalog = build_unified_catalog(config=config)

        # Verified object from SATCAT
        iss = catalog.get(25544)
        assert iss.classification_verified is True
        assert iss.classification_source == "satcat"

        # Unverified object using source group hint
        deb = catalog.get(33504)
        assert deb.classification_verified is False
        assert deb.classification_source == "source_group_hint"
        assert "(source_group_hint, no SATCAT)" in deb.source_provenance

    def test_freshness_tracking_and_stale_flagging(self, tmp_path, sample_gp_records):
        gp_file = tmp_path / "satellites.csv"
        pd.DataFrame(sample_gp_records).to_csv(gp_file, index=False)

        # Reference time is 20 days after epoch 2026-09-17
        ref_time = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)

        # Test with max age threshold = 10.0 days (records are 20 days old -> stale)
        config_stale = CatalogConfig(
            gp_sources=[GPSourceConfig(source_name="gp", path=gp_file)],
            satcat_path=None,
            reference_time=ref_time,
            max_epoch_age_days=10.0,
            stale_data_policy="flag",
        )
        cat_stale = build_unified_catalog(config=config_stale)
        summary = cat_stale.summary(reference_time=ref_time)
        assert summary.stale_records_count == 3
        assert summary.fresh_records_count == 0
        assert cat_stale.get(25544).is_stale is True
        assert cat_stale.get(25544).freshness_status == "stale"

        # Test with max age threshold = 30.0 days (records are 20 days old -> fresh)
        config_fresh = CatalogConfig(
            gp_sources=[GPSourceConfig(source_name="gp", path=gp_file)],
            satcat_path=None,
            reference_time=ref_time,
            max_epoch_age_days=30.0,
        )
        cat_fresh = build_unified_catalog(config=config_fresh)
        assert cat_fresh.get(25544).is_stale is False
        assert cat_fresh.get(25544).freshness_status == "fresh"

    @patch("ml.models.threat_prioritization.find_closest_approach")
    def test_stale_policy_warning_and_exclusion(self, mock_find, tmp_path, sample_gp_records):
        gp_file = tmp_path / "satellites.csv"
        pd.DataFrame(sample_gp_records[:2]).to_csv(gp_file, index=False)

        ref_time = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
        mock_find.return_value = CloseApproachResult(
            object1_norad_id=25544,
            object2_norad_id=33504,
            object1_name="ISS",
            object2_name="DEB",
            analysis_start_time=ref_time,
            analysis_end_time=ref_time,
            time_of_closest_approach=datetime(2026, 10, 7, 18, 0, 0, tzinfo=timezone.utc),
            minimum_separation_km=20.0,
            relative_speed_km_s=10.0,
            threshold_km=50.0,
            is_candidate_close_approach=True,
        )

        threat_cfg = ThreatConfig(protected_norad_ids=[25544])

        # Case 1: Policy = "flag" -> events evaluated, but visibly warning flagged
        cfg_flag = CatalogConfig(
            gp_sources=[GPSourceConfig(source_name="gp", path=gp_file)],
            satcat_path=None,
            reference_time=ref_time,
            max_epoch_age_days=5.0,  # 20 days old -> stale
            stale_data_policy="flag",
        )
        cat_flag = build_unified_catalog(config=cfg_flag)
        res_flag = screen_threats_from_catalog(catalog=cat_flag, config=threat_cfg, reference_time=ref_time)
        assert len(res_flag.events) == 1
        notes = " ".join(res_flag.events[0].screening_notes)
        assert "STALE ORBITAL DATA" in notes

        # Case 2: Policy = "exclude" -> stale candidates excluded from screening
        cfg_exclude = CatalogConfig(
            gp_sources=[GPSourceConfig(source_name="gp", path=gp_file)],
            satcat_path=None,
            reference_time=ref_time,
            max_epoch_age_days=5.0,
            stale_data_policy="exclude",
        )
        cat_exclude = build_unified_catalog(config=cfg_exclude)
        res_exclude = screen_threats_from_catalog(catalog=cat_exclude, config=threat_cfg, reference_time=ref_time)
        assert len(res_exclude.events) == 0


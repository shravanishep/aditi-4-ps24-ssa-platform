"""
tests/test_threat_prioritization.py — Unit tests for Layer 9 threat prioritization engine.

Verifies:
1. Protected target identification (explicit list, protect_all_active, validation errors).
2. Threat candidate selection (exclusion of protected targets, candidate capping).
3. Layer 8 anomaly integration (available vs unavailable, missing-data handling).
4. Conjunction screening integration and ranking (end-to-end with mocked conjunctions).
5. Data-source limitation notes (active-only limitation, missing metadata warnings).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.orbital.models import CloseApproachResult
from ml.models.threat_config import ThreatConfig
from ml.models.threat_prioritization import (
    ScreeningResult,
    ThreatEvent,
    _get_anomaly_score_for_object,
    _select_threat_candidates,
    identify_protected_targets,
    screen_threats,
)


@pytest.fixture
def sample_gp_df() -> pd.DataFrame:
    """Fixture providing a minimal GP DataFrame for testing."""
    return pd.DataFrame(
        [
            {
                "NORAD_CAT_ID": 1001,
                "OBJECT_NAME": "SAT_ALPHA",
                "EPOCH": "2026-09-17T12:00:00.000000",
                "MEAN_MOTION": 15.1,
                "ECCENTRICITY": 0.001,
                "INCLINATION": 51.6,
                "RA_OF_ASC_NODE": 120.0,
                "ARG_OF_PERICENTER": 45.0,
                "MEAN_ANOMALY": 10.0,
                "BSTAR": 0.0001,
                "MEAN_MOTION_DOT": 0.0,
                "MEAN_MOTION_DDOT": 0.0,
            },
            {
                "NORAD_CAT_ID": 1002,
                "OBJECT_NAME": "SAT_BETA",
                "EPOCH": "2026-09-17T12:00:00.000000",
                "MEAN_MOTION": 15.15,
                "ECCENTRICITY": 0.0012,
                "INCLINATION": 51.65,
                "RA_OF_ASC_NODE": 120.5,
                "ARG_OF_PERICENTER": 45.2,
                "MEAN_ANOMALY": 10.5,
                "BSTAR": 0.0001,
                "MEAN_MOTION_DOT": 0.0,
                "MEAN_MOTION_DDOT": 0.0,
            },
            {
                "NORAD_CAT_ID": 1003,
                "OBJECT_NAME": "SAT_GAMMA",
                "EPOCH": "2026-09-17T12:00:00.000000",
                "MEAN_MOTION": 14.5,
                "ECCENTRICITY": 0.002,
                "INCLINATION": 98.0,
                "RA_OF_ASC_NODE": 30.0,
                "ARG_OF_PERICENTER": 60.0,
                "MEAN_ANOMALY": 20.0,
                "BSTAR": 0.00005,
                "MEAN_MOTION_DOT": 0.0,
                "MEAN_MOTION_DDOT": 0.0,
            },
        ]
    )


class TestProtectedTargetIdentification:
    def test_identify_explicit_targets(self, sample_gp_df: pd.DataFrame):
        config = ThreatConfig(protected_norad_ids=[1001])
        targets = identify_protected_targets(sample_gp_df, config)
        assert targets == [1001]

    def test_identify_protect_all_active(self, sample_gp_df: pd.DataFrame):
        config = ThreatConfig(protect_all_active=True)
        targets = identify_protected_targets(sample_gp_df, config)
        assert targets == [1001, 1002, 1003]

    def test_missing_norad_id_raises_value_error(self, sample_gp_df: pd.DataFrame):
        config = ThreatConfig(protected_norad_ids=[9999])
        with pytest.raises(ValueError, match="Protected NORAD IDs not found"):
            identify_protected_targets(sample_gp_df, config)

    def test_empty_protected_ids_raises_value_error(self, sample_gp_df: pd.DataFrame):
        config = ThreatConfig(protected_norad_ids=[], protect_all_active=False)
        with pytest.raises(ValueError, match="No protected targets specified"):
            identify_protected_targets(sample_gp_df, config)


class TestCandidateSelection:
    def test_excludes_protected_targets(self, sample_gp_df: pd.DataFrame):
        config = ThreatConfig(protected_norad_ids=[1001], max_threat_candidates=10)
        candidates = _select_threat_candidates(sample_gp_df, {1001}, config)
        assert 1001 not in candidates["NORAD_CAT_ID"].values
        assert set(candidates["NORAD_CAT_ID"].values) == {1002, 1003}

    def test_respects_max_threat_candidates(self, sample_gp_df: pd.DataFrame):
        config = ThreatConfig(protected_norad_ids=[1001], max_threat_candidates=1)
        candidates = _select_threat_candidates(sample_gp_df, {1001}, config)
        assert len(candidates) == 1
        assert candidates["NORAD_CAT_ID"].iloc[0] == 1002  # sorted ascending

    def test_protect_all_active_preserves_all_candidates(self, sample_gp_df: pd.DataFrame):
        config = ThreatConfig(protect_all_active=True, max_threat_candidates=10)
        candidates = _select_threat_candidates(sample_gp_df, {1001, 1002, 1003}, config)
        assert len(candidates) == 3
        assert set(candidates["NORAD_CAT_ID"].values) == {1001, 1002, 1003}


class TestAnomalyIntegration:
    def test_anomaly_unavailable_when_detector_none(self):
        score, sev = _get_anomaly_score_for_object(1002, None, None)
        assert score is None
        assert sev == "unavailable"

    def test_anomaly_unavailable_when_object_not_in_features(self):
        df_feat = pd.DataFrame([{"norad_cat_id": 9999, "t_offset_minutes": 0.0}])
        mock_detector = MagicMock()
        score, sev = _get_anomaly_score_for_object(1002, df_feat, mock_detector)
        assert score is None
        assert sev == "unavailable"
        mock_detector.predict.assert_not_called()

    def test_anomaly_extracted_when_object_present(self):
        df_feat = pd.DataFrame(
            [
                {"norad_cat_id": 1002, "t_offset_minutes": -30.0},
                {"norad_cat_id": 1002, "t_offset_minutes": 0.0},
            ]
        )
        mock_detector = MagicMock()
        mock_detector.predict.return_value = pd.DataFrame(
            [{"normalized_anomaly_score": 0.75, "anomaly_severity": "warning"}]
        )
        score, sev = _get_anomaly_score_for_object(1002, df_feat, mock_detector)
        assert score == 0.75
        assert sev == "warning"
        mock_detector.predict.assert_called_once()


class TestScreenThreats:
    @patch("ml.models.threat_prioritization.find_closest_approach")
    def test_screen_threats_ranking_and_notes(
        self, mock_find_closest: MagicMock, sample_gp_df: pd.DataFrame
    ):
        ref_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        config = ThreatConfig(
            protected_norad_ids=[1001],
            screening_threshold_km=50.0,
            screening_window_hours=24.0,
        )

        # Mock close approach results for 1001 vs 1002 (candidate close approach)
        # and 1001 vs 1003 (not a candidate close approach)
        def side_effect(sat1_row, sat2_row, **kwargs):
            threat_id = int(sat2_row["NORAD_CAT_ID"])
            if threat_id == 1002:
                return CloseApproachResult(
                    object1_norad_id=1001,
                    object2_norad_id=1002,
                    object1_name="SAT_ALPHA",
                    object2_name="SAT_BETA",
                    analysis_start_time=ref_time,
                    analysis_end_time=ref_time,
                    time_of_closest_approach=datetime(2026, 9, 17, 18, 0, 0, tzinfo=timezone.utc),
                    minimum_separation_km=12.5,
                    relative_speed_km_s=11.2,
                    threshold_km=50.0,
                    is_candidate_close_approach=True,
                )
            else:
                return CloseApproachResult(
                    object1_norad_id=1001,
                    object2_norad_id=1003,
                    object1_name="SAT_ALPHA",
                    object2_name="SAT_GAMMA",
                    analysis_start_time=ref_time,
                    analysis_end_time=ref_time,
                    time_of_closest_approach=datetime(2026, 9, 17, 20, 0, 0, tzinfo=timezone.utc),
                    minimum_separation_km=450.0,
                    relative_speed_km_s=8.0,
                    threshold_km=50.0,
                    is_candidate_close_approach=False,
                )

        mock_find_closest.side_effect = side_effect

        result = screen_threats(
            gp_df=sample_gp_df,
            protected_ids=[1001],
            config=config,
            reference_time=ref_time,
        )

        assert isinstance(result, ScreeningResult)
        assert result.protected_count == 1
        assert result.candidates_screened == 2
        assert result.pairs_evaluated == 2
        assert result.events_within_threshold == 1
        assert len(result.events) == 1

        ev = result.events[0]
        assert isinstance(ev, ThreatEvent)
        assert ev.protected_norad_id == 1001
        assert ev.threat_norad_id == 1002
        assert ev.minimum_separation_km == 12.5
        assert ev.relative_speed_km_s == 11.2
        assert ev.hours_to_tca == 6.0
        assert 0.0 <= ev.risk_score <= 1.0
        assert ev.risk_severity in ["low", "warning", "critical"]
        assert ev.threat_anomaly_score is None
        assert ev.threat_anomaly_severity == "unavailable"
        assert len(ev.screening_notes) >= 1

        # Check documented data source limitation notes
        notes_str = " ".join(result.data_source_notes)
        assert "No separate debris/rocket-body GP dataset configured" in notes_str
        assert "active-satellite-vs-active-satellite" in notes_str
        assert "OBJECT_TYPE" in notes_str

    @patch("ml.models.threat_prioritization.find_closest_approach")
    def test_screen_threats_common_time_window_and_deduplication(
        self, mock_find_closest: MagicMock, sample_gp_df: pd.DataFrame
    ):
        ref_time = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        config = ThreatConfig(
            protect_all_active=True,
            screening_threshold_km=50.0,
            screening_window_hours=48.0,
        )

        mock_find_closest.return_value = CloseApproachResult(
            object1_norad_id=1001,
            object2_norad_id=1002,
            object1_name="SAT_ALPHA",
            object2_name="SAT_BETA",
            analysis_start_time=ref_time,
            analysis_end_time=ref_time,
            time_of_closest_approach=datetime(2026, 9, 18, 0, 0, 0, tzinfo=timezone.utc),
            minimum_separation_km=100.0,
            relative_speed_km_s=5.0,
            threshold_km=50.0,
            is_candidate_close_approach=False,
        )

        result = screen_threats(
            gp_df=sample_gp_df,
            protected_ids=[1001, 1002, 1003],
            config=config,
            reference_time=ref_time,
        )

        # 3 satellites -> exactly 3 unique pairs: (1001, 1002), (1001, 1003), (1002, 1003)
        assert result.pairs_evaluated == 3

        # Verify common time window was passed to all calls
        for call_args in mock_find_closest.call_args_list:
            assert call_args.kwargs["start_time"] == ref_time
            assert call_args.kwargs["end_time"] == ref_time + pd.Timedelta(hours=48.0)
            assert call_args.kwargs["sat1_row"]["NORAD_CAT_ID"] != call_args.kwargs["sat2_row"]["NORAD_CAT_ID"]


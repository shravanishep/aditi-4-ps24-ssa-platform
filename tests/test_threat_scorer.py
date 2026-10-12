"""
tests/test_threat_scorer.py — Unit tests for Layer 9 threat scoring and config.

Verifies:
1. ThreatConfig validation (weights, positive thresholds, ordering).
2. Individual normalisation factors (separation, relative velocity, time-to-TCA, anomaly).
3. Bounded composite score in [0.0, 1.0].
4. Missing anomaly data handling (zero contribution, explicit flagging).
5. Explainability dictionary structure and factor decomposition.
6. Severity classification thresholds.
"""

from __future__ import annotations

import pytest

from ml.models.threat_config import ThreatConfig
from ml.models.threat_scorer import (
    classify_severity,
    compute_risk_score,
    explain_risk_score,
)


@pytest.fixture
def default_config() -> ThreatConfig:
    """Fixture providing a default validated ThreatConfig."""
    config = ThreatConfig()
    config.validate()
    return config


class TestThreatConfig:
    def test_default_config_is_valid(self, default_config: ThreatConfig):
        assert default_config.weight_separation == 0.40
        assert default_config.weight_relative_velocity == 0.25
        assert default_config.weight_anomaly_score == 0.20
        assert default_config.weight_time_to_tca == 0.15
        total_weight = (
            default_config.weight_separation
            + default_config.weight_relative_velocity
            + default_config.weight_anomaly_score
            + default_config.weight_time_to_tca
        )
        assert pytest.approx(total_weight, abs=1e-6) == 1.0

    def test_invalid_weights_sum_raises_error(self):
        config = ThreatConfig(
            weight_separation=0.5,
            weight_relative_velocity=0.5,
            weight_anomaly_score=0.2,
            weight_time_to_tca=0.2,
        )
        with pytest.raises(ValueError, match="Scoring weights must sum to 1.0"):
            config.validate()

    def test_negative_weight_raises_error(self):
        config = ThreatConfig(
            weight_separation=-0.1,
            weight_relative_velocity=0.5,
            weight_anomaly_score=0.3,
            weight_time_to_tca=0.3,
        )
        with pytest.raises(ValueError, match="Scoring weight at index 0 is negative"):
            config.validate()

    def test_negative_threshold_raises_error(self):
        config = ThreatConfig(screening_threshold_km=-5.0)
        with pytest.raises(ValueError, match="screening_threshold_km must be positive"):
            config.validate()

    def test_inverted_severity_thresholds_raises_error(self):
        config = ThreatConfig(
            critical_risk_threshold=0.3,
            warning_risk_threshold=0.6,
        )
        with pytest.raises(ValueError, match="Severity thresholds must satisfy"):
            config.validate()

    def test_has_threat_data_source(self, tmp_path):
        config = ThreatConfig()
        assert not config.has_threat_data_source()
        
        # When file exists
        fake_threat_file = tmp_path / "debris.csv"
        fake_threat_file.write_text("header\n")
        config.threat_gp_csv_path = str(fake_threat_file)
        assert config.has_threat_data_source()


class TestThreatScorer:
    def test_worst_case_max_risk(self, default_config: ThreatConfig):
        """Zero separation, max relative velocity, immediate TCA, max anomaly score."""
        score = compute_risk_score(
            min_separation_km=0.0,
            relative_speed_km_s=default_config.ref_max_rel_velocity_km_s,
            hours_to_tca=0.0,
            anomaly_score=1.0,
            config=default_config,
        )
        assert pytest.approx(score, abs=1e-5) == 1.0
        assert classify_severity(score, default_config) == "critical"

    def test_benign_case_min_risk(self, default_config: ThreatConfig):
        """Separation at or above ref_max, zero relative velocity, distant TCA, zero anomaly."""
        score = compute_risk_score(
            min_separation_km=default_config.ref_max_separation_km,
            relative_speed_km_s=0.0,
            hours_to_tca=default_config.ref_max_time_to_tca_hours,
            anomaly_score=0.0,
            config=default_config,
        )
        assert pytest.approx(score, abs=1e-5) == 0.0
        assert classify_severity(score, default_config) == "low"

    def test_separation_clamped_beyond_reference(self, default_config: ThreatConfig):
        """Separation beyond ref_max_separation_km yields 0 contribution, not negative."""
        score1 = compute_risk_score(
            min_separation_km=default_config.ref_max_separation_km,
            relative_speed_km_s=5.0,
            hours_to_tca=10.0,
            anomaly_score=None,
            config=default_config,
        )
        score2 = compute_risk_score(
            min_separation_km=default_config.ref_max_separation_km * 2.0,
            relative_speed_km_s=5.0,
            hours_to_tca=10.0,
            anomaly_score=None,
            config=default_config,
        )
        assert score1 == score2

    def test_missing_anomaly_contributes_zero(self, default_config: ThreatConfig):
        """When anomaly_score is None, the anomaly term contributes 0 to the score."""
        score_none = compute_risk_score(
            min_separation_km=10.0,
            relative_speed_km_s=5.0,
            hours_to_tca=12.0,
            anomaly_score=None,
            config=default_config,
        )
        score_zero = compute_risk_score(
            min_separation_km=10.0,
            relative_speed_km_s=5.0,
            hours_to_tca=12.0,
            anomaly_score=0.0,
            config=default_config,
        )
        assert pytest.approx(score_none, abs=1e-6) == score_zero

    def test_explain_risk_score_structure(self, default_config: ThreatConfig):
        explanation = explain_risk_score(
            min_separation_km=5.0,
            relative_speed_km_s=10.0,
            hours_to_tca=6.0,
            anomaly_score=0.8,
            config=default_config,
        )
        assert "risk_score" in explanation
        assert "risk_severity" in explanation
        assert "factors" in explanation
        assert "disclaimer" in explanation

        factors = explanation["factors"]
        assert "separation" in factors
        assert "relative_velocity" in factors
        assert "time_to_tca" in factors
        assert "anomaly_score" in factors

        assert factors["anomaly_score"]["raw_value"] == 0.8
        assert explanation["anomaly_data_available"] is True

        # Weighted sum consistency
        total = sum(f["contribution"] for f in factors.values())
        assert pytest.approx(explanation["risk_score"], abs=1e-5) == total

    def test_explain_risk_score_missing_anomaly(self, default_config: ThreatConfig):
        explanation = explain_risk_score(
            min_separation_km=5.0,
            relative_speed_km_s=10.0,
            hours_to_tca=6.0,
            anomaly_score=None,
            config=default_config,
        )
        assert explanation["anomaly_data_available"] is False
        anom_info = explanation["factors"]["anomaly_score"]
        assert anom_info["raw_value"] == "unavailable"
        assert anom_info["contribution"] == 0.0

    def test_severity_classification_boundaries(self, default_config: ThreatConfig):
        assert classify_severity(0.80, default_config) == "critical"
        assert classify_severity(0.95, default_config) == "critical"
        assert classify_severity(0.79, default_config) == "warning"
        assert classify_severity(0.50, default_config) == "warning"
        assert classify_severity(0.49, default_config) == "low"
        assert classify_severity(0.00, default_config) == "low"

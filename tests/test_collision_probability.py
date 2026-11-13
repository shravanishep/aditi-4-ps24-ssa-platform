"""Unit and integration tests for Collision Probability (Pc) and CDM parsing (Feature 3).

Tests:
  - CDM text parsing and covariance extraction
  - Foster's 2-D encounter-plane Pc method
  - Positive semi-definiteness (PSD) validation
  - Covariance requirement (pc=None when unavailable)
  - FastAPI endpoints (/cdm/parse, /pc/compute, /pc/from-cdm, /pc/method-info)
"""

import math
import pytest
from fastapi.testclient import TestClient

from backend.orbital.cdm_parser import parse_cdm, validate_covariance_psd
from backend.orbital.collision_probability import compute_pc_foster_2d
from backend.main import app


SAMPLE_VALID_CDM = """
CCSDS_CDM_VERS = 1.0
COMMENT = Test Conjunction Data Message
CREATION_DATE = 2026-11-13T12:00:00Z
TCA = 2026-11-14T08:30:00Z
MISS_DISTANCE = 0.850
RELATIVE_SPEED = 14.250
RELATIVE_POSITION_R = 0.200
RELATIVE_POSITION_T = 0.100
RELATIVE_POSITION_N = 0.800
OBJECT1_DESIGNATOR = 25544
OBJECT1_NAME = ISS (ZARYA)
OBJECT2_DESIGNATOR = 99001
OBJECT2_NAME = DEBRIS-FRAG-A
COV_FRAME = RTN
COV_RR = 0.25
COV_RT = 0.00
COV_RN = 0.00
COV_TT = 1.00
COV_TN = 0.00
COV_NN = 0.25
"""

SAMPLE_CDM_NO_COVARIANCE = """
CCSDS_CDM_VERS = 1.0
TCA = 2026-11-14T10:00:00Z
RELATIVE_SPEED = 11.2
RELATIVE_POSITION_R = 1.0
RELATIVE_POSITION_T = 0.0
RELATIVE_POSITION_N = 2.0
OBJECT1_NAME = SAT-A
OBJECT2_NAME = SAT-B
"""


# ===========================================================================
# CDM Parser Tests
# ===========================================================================

class TestCDMParser:
    def test_parse_valid_cdm(self):
        rec = parse_cdm(SAMPLE_VALID_CDM)
        assert rec.object1.object_name == "ISS (ZARYA)"
        assert rec.object2.object_name == "DEBRIS-FRAG-A"
        assert rec.relative_speed_km_s == 14.25
        assert rec.relative_position_r_km == 0.2
        assert rec.object1.covariance_matrix is not None
        assert len(rec.object1.covariance_matrix) == 3
        assert rec.object1.covariance_matrix[0][0] == 0.25

    def test_parse_cdm_no_covariance(self):
        rec = parse_cdm(SAMPLE_CDM_NO_COVARIANCE)
        assert rec.object1.covariance_matrix is None
        assert rec.object1.covariance_frame == "UNKNOWN"

    def test_missing_tca_raises(self):
        bad_text = "OBJECT1_NAME = TEST\nRELATIVE_SPEED = 5.0"
        with pytest.raises(ValueError, match="TCA"):
            parse_cdm(bad_text)

    def test_psd_validation(self):
        # Identity matrix is PSD
        assert validate_covariance_psd([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]) is True
        # Negative diagonal is not PSD
        assert validate_covariance_psd([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]) is False


# ===========================================================================
# Collision Probability Unit Tests
# ===========================================================================

class TestCollisionProbability:
    def test_missing_covariance_returns_none(self):
        result = compute_pc_foster_2d(
            miss_distance_km=1.0,
            relative_speed_km_s=10.0,
            cov1_rtn_3x3=None,
            cov2_rtn_3x3=None,
        )
        assert result.pc is None
        assert result.combined_covariance_valid is False
        assert result.pc_method == "unavailable"
        assert "disclaimer" in result.__dict__

    def test_valid_covariance_computes_pc(self):
        # 1 km standard deviation spherical covariance
        cov = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        result = compute_pc_foster_2d(
            miss_distance_km=0.5,
            relative_speed_km_s=12.0,
            cov1_rtn_3x3=cov,
            cov2_rtn_3x3=cov,
            hard_body_radius_km=0.020,
        )
        assert result.pc is not None
        assert 0.0 <= result.pc <= 1.0
        assert result.combined_covariance_valid is True
        assert result.pc_method == "Foster_2D"
        assert result.b_plane_sigma1_km is not None
        assert result.b_plane_sigma2_km is not None

    def test_closer_miss_distance_yields_higher_pc(self):
        cov = [[0.5, 0.0, 0.0], [0.0, 0.5, 0.0], [0.0, 0.0, 0.5]]
        res_close = compute_pc_foster_2d(
            miss_distance_km=0.05,
            relative_speed_km_s=10.0,
            cov1_rtn_3x3=cov,
            hard_body_radius_km=0.020,
        )
        res_far = compute_pc_foster_2d(
            miss_distance_km=2.0,
            relative_speed_km_s=10.0,
            cov1_rtn_3x3=cov,
            hard_body_radius_km=0.020,
        )
        assert res_close.pc is not None
        assert res_far.pc is not None
        assert res_close.pc > res_far.pc

    def test_invalid_miss_distance_raises(self):
        with pytest.raises(ValueError):
            compute_pc_foster_2d(miss_distance_km=0.0, relative_speed_km_s=10.0)
        with pytest.raises(ValueError):
            compute_pc_foster_2d(miss_distance_km=-1.0, relative_speed_km_s=10.0)


# ===========================================================================
# API Integration Tests
# ===========================================================================

client = TestClient(app, raise_server_exceptions=False)


def test_api_cdm_parse_valid():
    res = client.post("/cdm/parse", json={"cdm_text": SAMPLE_VALID_CDM})
    assert res.status_code == 200
    data = res.json()
    assert data["object1_name"] == "ISS (ZARYA)"
    assert data["covariance_available"] is True
    assert data["covariance_valid"] is True


def test_api_cdm_parse_no_covariance():
    res = client.post("/cdm/parse", json={"cdm_text": SAMPLE_CDM_NO_COVARIANCE})
    assert res.status_code == 200
    data = res.json()
    assert data["covariance_available"] is False
    assert data["covariance_valid"] is False


def test_api_pc_compute_without_cov():
    res = client.post("/pc/compute", json={"miss_distance_km": 1.5, "rel_speed_km_s": 10.0})
    assert res.status_code == 200
    data = res.json()
    assert data["pc"] is None
    assert data["combined_covariance_valid"] is False


def test_api_pc_compute_with_cov():
    payload = {
        "miss_distance_km": 0.2,
        "rel_speed_km_s": 11.5,
        "cov1_rtn": [[0.5, 0.0, 0.0], [0.0, 0.5, 0.0], [0.0, 0.0, 0.5]],
        "hard_body_radius_km": 0.020,
    }
    res = client.post("/pc/compute", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["pc"] is not None
    assert data["combined_covariance_valid"] is True


def test_api_pc_from_cdm():
    res = client.post("/pc/from-cdm", json={"cdm_text": SAMPLE_VALID_CDM, "hard_body_radius_km": 0.020})
    assert res.status_code == 200
    data = res.json()
    assert "tca" in data
    assert data["pc_result"]["pc"] is not None


def test_api_method_info():
    res = client.get("/pc/method-info")
    assert res.status_code == 200
    data = res.json()
    assert "Foster" in data["method"]
    assert "assumptions" in data


import datetime

import pytest

from backend.orbital.conjunction import find_closest_approach
from backend.orbital.models import CloseApproachResult


@pytest.fixture
def mock_sat1():
    return {
        "NORAD_CAT_ID": 11111,
        "OBJECT_NAME": "MOCK SAT 1",
        "EPOCH": "2026-09-17T00:00:00",
        "MEAN_MOTION": 15.0,
        "ECCENTRICITY": 0.0001,
        "INCLINATION": 50.0,
        "RA_OF_ASC_NODE": 100.0,
        "ARG_OF_PERICENTER": 50.0,
        "MEAN_ANOMALY": 10.0,
        "BSTAR": 0.0,
        "MEAN_MOTION_DOT": 0.0,
        "MEAN_MOTION_DDOT": 0.0,
    }


@pytest.fixture
def mock_sat2():
    return {
        "NORAD_CAT_ID": 22222,
        "OBJECT_NAME": "MOCK SAT 2",
        "EPOCH": "2026-09-17T00:00:00",
        "MEAN_MOTION": 15.0,
        "ECCENTRICITY": 0.0001,
        "INCLINATION": 50.0,
        "RA_OF_ASC_NODE": 100.0,
        "ARG_OF_PERICENTER": 50.0,
        "MEAN_ANOMALY": 11.0,
        "BSTAR": 0.0,
        "MEAN_MOTION_DOT": 0.0,
        "MEAN_MOTION_DDOT": 0.0,
    }

def test_same_norad_id_rejection(mock_sat1):
    start = datetime.datetime(2026, 9, 17, 0, 0, 0, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(hours=1)
    
    with pytest.raises(ValueError, match="different NORAD IDs"):
        find_closest_approach(mock_sat1, mock_sat1, start, end, 10.0)

def test_invalid_analysis_window(mock_sat1, mock_sat2):
    start = datetime.datetime(2026, 9, 17, 1, 0, 0, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2026, 9, 17, 0, 0, 0, tzinfo=datetime.timezone.utc)
    
    with pytest.raises(ValueError, match="greater than start_time"):
        find_closest_approach(mock_sat1, mock_sat2, start, end, 10.0)

def test_invalid_threshold(mock_sat1, mock_sat2):
    start = datetime.datetime(2026, 9, 17, 0, 0, 0, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(hours=1)
    
    with pytest.raises(ValueError, match="threshold_km must be greater than 0"):
        find_closest_approach(mock_sat1, mock_sat2, start, end, 0.0)

def test_invalid_steps(mock_sat1, mock_sat2):
    start = datetime.datetime(2026, 9, 17, 0, 0, 0, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(hours=1)
    
    with pytest.raises(ValueError, match="coarse_step_sec must be greater than 0"):
        find_closest_approach(mock_sat1, mock_sat2, start, end, 10.0, coarse_step_sec=0)
        
    with pytest.raises(ValueError, match="fine_step_sec must be greater than 0"):
        find_closest_approach(mock_sat1, mock_sat2, start, end, 10.0, fine_step_sec=0)

    with pytest.raises(ValueError, match="fine_step_sec must be less than or equal to coarse_step_sec"):
        find_closest_approach(mock_sat1, mock_sat2, start, end, 10.0, coarse_step_sec=10, fine_step_sec=20)


def test_find_closest_approach_success(mock_sat1, mock_sat2):
    start = datetime.datetime(2026, 9, 17, 0, 0, 0, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(minutes=30)
    
    res = find_closest_approach(
        mock_sat1,
        mock_sat2,
        start,
        end,
        threshold_km=500.0,
        coarse_step_sec=60.0,
        fine_step_sec=1.0
    )
    
    assert isinstance(res, CloseApproachResult)
    assert res.object1_norad_id == 11111
    assert res.object2_norad_id == 22222
    assert res.analysis_start_time == start
    assert res.analysis_end_time == end
    assert start <= res.time_of_closest_approach <= end
    assert res.minimum_separation_km >= 0
    assert res.relative_speed_km_s >= 0
    
    # Depending on the synthetic data, they might or might not be close. 
    # But it should complete without error.
    assert res.is_candidate_close_approach == (res.minimum_separation_km <= 500.0)

def test_find_closest_approach_propagation_error(mock_sat1, mock_sat2):
    # Mess up eccentricity to cause SGP4 error
    bad_sat2 = mock_sat2.copy()
    bad_sat2["ECCENTRICITY"] = 1.5  # Invalid for SGP4 init typically, or causes error on propagate
    
    start = datetime.datetime(2026, 9, 17, 0, 0, 0, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(minutes=10)
    
    with pytest.raises(ValueError, match="No valid SGP4 states found"):
        find_closest_approach(mock_sat1, bad_sat2, start, end, 100.0)

from unittest.mock import patch
from backend.orbital.models import PropagatedOrbitState

@patch('backend.orbital.conjunction.propagate_orbit')
def test_fine_search_failure(mock_propagate, mock_sat1, mock_sat2):
    start = datetime.datetime(2026, 9, 17, 0, 0, 0, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(minutes=10)

    call_count = [0]
    def side_effect(row, dt):
        call_count[0] += 1
        # Coarse search: 11 evaluation points * 2 calls per point = 22 calls
        err = 0 if call_count[0] <= 22 else 1
        msg = "" if call_count[0] <= 22 else "Mock Error"
        return PropagatedOrbitState(
            object_name="Mock", norad_cat_id=1, timestamp=dt,
            position_x_km=1.0, position_y_km=2.0, position_z_km=3.0,
            velocity_x_km_s=1.0, velocity_y_km_s=2.0, velocity_z_km_s=3.0,
            sgp4_error=err, error_message=msg
        )

    mock_propagate.side_effect = side_effect
    
    with pytest.raises(ValueError, match="No valid SGP4 states found during fine search"):
        find_closest_approach(mock_sat1, mock_sat2, start, end, 100.0)

@patch('backend.orbital.conjunction.propagate_orbit')
def test_final_tca_sgp4_error(mock_propagate, mock_sat1, mock_sat2):
    start = datetime.datetime(2026, 9, 17, 0, 0, 0, tzinfo=datetime.timezone.utc)
    end = start + datetime.timedelta(minutes=10)

    call_count = [0]
    def side_effect(row, dt):
        call_count[0] += 1
        # Coarse: 22 calls
        # Fine: window is 0 to 60 (since min is at 0), so 61 points. 61 * 2 = 122 calls.
        # Total before final evaluate = 144 calls.
        err = 0 if call_count[0] <= 144 else 1
        msg = "" if call_count[0] <= 144 else "Final Error"
        return PropagatedOrbitState(
            object_name="Mock", norad_cat_id=1, timestamp=dt,
            position_x_km=1.0, position_y_km=2.0, position_z_km=3.0,
            velocity_x_km_s=1.0, velocity_y_km_s=2.0, velocity_z_km_s=3.0,
            sgp4_error=err, error_message=msg
        )

    mock_propagate.side_effect = side_effect
    
    with pytest.raises(ValueError, match="SGP4 error at final TCA calculation"):
        find_closest_approach(mock_sat1, mock_sat2, start, end, 100.0)

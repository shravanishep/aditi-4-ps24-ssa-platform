import datetime
from datetime import timezone

import numpy as np
import pytest

from backend.orbital.calculations import (
    calculate_distance,
    calculate_orbital_radius,
    calculate_relative_position,
    calculate_relative_velocity,
    calculate_velocity_magnitude,
)
from backend.orbital.models import PropagatedOrbitState

@pytest.fixture
def base_time():
    return datetime.datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)

@pytest.fixture
def state1(base_time):
    return PropagatedOrbitState(
        object_name="SAT 1",
        norad_cat_id=11111,
        timestamp=base_time,
        position_x_km=3.0,
        position_y_km=4.0,
        position_z_km=0.0,
        velocity_x_km_s=1.0,
        velocity_y_km_s=2.0,
        velocity_z_km_s=2.0,
        sgp4_error=0,
    )

@pytest.fixture
def state2(base_time):
    return PropagatedOrbitState(
        object_name="SAT 2",
        norad_cat_id=22222,
        timestamp=base_time,
        position_x_km=0.0,
        position_y_km=0.0,
        position_z_km=12.0,
        velocity_x_km_s=1.0,
        velocity_y_km_s=0.0,
        velocity_z_km_s=0.0,
        sgp4_error=0,
    )

@pytest.fixture
def state_diff_time(base_time):
    return PropagatedOrbitState(
        object_name="SAT 3",
        norad_cat_id=33333,
        timestamp=base_time + datetime.timedelta(seconds=1),
        position_x_km=1.0,
        position_y_km=1.0,
        position_z_km=1.0,
        velocity_x_km_s=1.0,
        velocity_y_km_s=1.0,
        velocity_z_km_s=1.0,
        sgp4_error=0,
    )

def test_calculate_orbital_radius(state1):
    # sqrt(3^2 + 4^2 + 0^2) = 5.0
    radius = calculate_orbital_radius(state1)
    assert radius == pytest.approx(5.0)

def test_calculate_velocity_magnitude(state1):
    # sqrt(1^2 + 2^2 + 2^2) = sqrt(9) = 3.0
    speed = calculate_velocity_magnitude(state1)
    assert speed == pytest.approx(3.0)

def test_calculate_relative_position(state1, state2):
    # state2 (0, 0, 12) - state1 (3, 4, 0) = (-3, -4, 12)
    rel_pos = calculate_relative_position(state1, state2)
    assert isinstance(rel_pos, np.ndarray)
    np.testing.assert_allclose(rel_pos, np.array([-3.0, -4.0, 12.0]))

def test_calculate_relative_velocity(state1, state2):
    # state2 (1, 0, 0) - state1 (1, 2, 2) = (0, -2, -2)
    rel_vel = calculate_relative_velocity(state1, state2)
    assert isinstance(rel_vel, np.ndarray)
    np.testing.assert_allclose(rel_vel, np.array([0.0, -2.0, -2.0]))

def test_calculate_distance(state1, state2):
    # distance between (3, 4, 0) and (0, 0, 12) = sqrt(3^2 + 4^2 + 12^2) = sqrt(9 + 16 + 144) = sqrt(169) = 13.0
    dist = calculate_distance(state1, state2)
    assert dist == pytest.approx(13.0)

def test_timestamp_validation(state1, state_diff_time):
    with pytest.raises(ValueError, match="timestamps"):
        calculate_relative_position(state1, state_diff_time)
        
    with pytest.raises(ValueError, match="timestamps"):
        calculate_relative_velocity(state1, state_diff_time)
        
    with pytest.raises(ValueError, match="timestamps"):
        calculate_distance(state1, state_diff_time)

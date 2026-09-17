from datetime import datetime, timezone

import pytest

from backend.orbital.gp_loader import get_satellite_by_norad
from backend.orbital.models import PropagatedOrbitState
from backend.orbital.sgp4_propagator import propagate_orbit, propagate_orbit_from_norad

DATA_PATH = "data/raw/active_satellites_gp.csv"


def test_sgp4_propagation_returns_position_and_velocity():
    row = get_satellite_by_norad(900, DATA_PATH)
    state = propagate_orbit(row, datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc))

    assert isinstance(state, PropagatedOrbitState)
    assert state.sgp4_error == 0
    assert state.position_x_km is not None
    assert state.position_y_km is not None
    assert state.position_z_km is not None
    assert state.velocity_x_km_s is not None
    assert state.velocity_y_km_s is not None
    assert state.velocity_z_km_s is not None

    assert state.position_x_km != 0
    assert state.position_y_km != 0
    assert state.position_z_km != 0


def test_propagation_result_contains_expected_units():
    row = get_satellite_by_norad(900, DATA_PATH)
    state = propagate_orbit(row, datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc))

    assert state.position_x_km > -100000 and state.position_x_km < 100000
    assert state.position_y_km > -100000 and state.position_y_km < 100000
    assert state.position_z_km > -100000 and state.position_z_km < 100000
    assert abs(state.velocity_x_km_s) < 100
    assert abs(state.velocity_y_km_s) < 100
    assert abs(state.velocity_z_km_s) < 100


def test_non_zero_sgp4_error_is_reported():
    row = get_satellite_by_norad(900, DATA_PATH).copy()
    row["MEAN_MOTION"] = 0
    state = propagate_orbit(row, datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc))

    assert state.sgp4_error != 0
    assert state.error_message


def test_norad_wrapper_works():
    state = propagate_orbit_from_norad(
        900,
        datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc),
        DATA_PATH,
    )

    assert state.norad_cat_id == 900
    assert state.object_name == "CALSPHERE 1"
    assert state.sgp4_error == 0

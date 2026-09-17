from datetime import datetime, timezone

import pytest

from backend.orbital.gp_loader import (
    get_satellite_by_norad,
    load_gp_data,
    parse_epoch,
)

DATA_PATH = "data/raw/active_satellites_gp.csv"


def test_csv_loads_successfully():
    df = load_gp_data(DATA_PATH)
    assert not df.empty
    assert len(df.columns) >= 17


def test_required_columns_exist():
    df = load_gp_data(DATA_PATH)
    required_columns = {
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
        "NORAD_CAT_ID",
        "ELEMENT_SET_NO",
        "REV_AT_EPOCH",
        "BSTAR",
        "MEAN_MOTION_DOT",
        "MEAN_MOTION_DDOT",
    }
    assert required_columns.issubset(set(df.columns))


def test_norad_lookup_works():
    row = get_satellite_by_norad(900, DATA_PATH)
    assert row["OBJECT_NAME"] == "CALSPHERE 1"
    assert row["NORAD_CAT_ID"] == 900


def test_invalid_norad_id_raises_clear_error():
    with pytest.raises(ValueError, match="NORAD_CAT_ID"):
        get_satellite_by_norad(999999, DATA_PATH)


def test_epoch_parses_correctly():
    row = get_satellite_by_norad(900, DATA_PATH)
    dt = parse_epoch(row["EPOCH"])
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(dt)

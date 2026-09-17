from __future__ import annotations

import math
from datetime import datetime, timezone

from sgp4.api import Satrec, WGS72
from sgp4.conveniences import check_satrec

from .gp_loader import parse_epoch
from .models import PropagatedOrbitState


def _gp_epoch_to_sgp4_epoch(epoch_dt: datetime) -> float:
    """
    Convert a UTC datetime into the SGP4 epoch convention.

    SGP4 expects epoch as days since 1949-12-31 00:00:00 UTC.
    """

    epoch0 = datetime(
        1949,
        12,
        31,
        tzinfo=timezone.utc,
    )

    epoch_dt = epoch_dt.astimezone(timezone.utc)

    return (
        (epoch_dt - epoch0).total_seconds()
        / 86400.0
    )


def _build_sgp4_satellite(row) -> Satrec:
    """
    Build and validate an SGP4 satellite record from
    one CelesTrak GP CSV row.
    """

    sat = Satrec()

    # ---------------------------------------------------------
    # Epoch
    # ---------------------------------------------------------
    epoch_dt = parse_epoch(row["EPOCH"])

    epoch = _gp_epoch_to_sgp4_epoch(epoch_dt)

    # ---------------------------------------------------------
    # GP orbital parameters
    # ---------------------------------------------------------
    mean_motion = float(row["MEAN_MOTION"])
    eccentricity = float(row["ECCENTRICITY"])

    inclination_deg = float(
        row["INCLINATION"]
    )

    ra_of_asc_node_deg = float(
        row["RA_OF_ASC_NODE"]
    )

    arg_of_pericenter_deg = float(
        row["ARG_OF_PERICENTER"]
    )

    mean_anomaly_deg = float(
        row["MEAN_ANOMALY"]
    )

    bstar = float(row["BSTAR"])

    mean_motion_dot = float(
        row["MEAN_MOTION_DOT"]
    )

    mean_motion_ddot = float(
        row["MEAN_MOTION_DDOT"]
    )

    norad_cat_id = int(
        row["NORAD_CAT_ID"]
    )

    # ---------------------------------------------------------
    # Convert GP units to SGP4 units
    # ---------------------------------------------------------
    #
    # CelesTrak GP:
    # MEAN_MOTION = revolutions/day
    #
    # sgp4init():
    # no_kozai = radians/minute
    #
    no_kozai = (
        mean_motion
        / 720.0
        * math.pi
    )

    # Mean motion derivatives are converted to the
    # units expected by sgp4init().
    ndot = (
        mean_motion_dot
        / (1036800.0 / math.pi)
    )

    nddot = (
        mean_motion_ddot
        / (
            2985984000.0
            / (2.0 * math.pi)
        )
    )

    # ---------------------------------------------------------
    # Initialize SGP4
    # ---------------------------------------------------------
    sat.sgp4init(
        WGS72,
        "i",
        norad_cat_id,
        epoch,
        bstar,
        ndot,
        nddot,
        eccentricity,
        math.radians(
            arg_of_pericenter_deg
        ),
        math.radians(
            inclination_deg
        ),
        math.radians(
            mean_anomaly_deg
        ),
        no_kozai,
        math.radians(
            ra_of_asc_node_deg
        ),
    )

    # ---------------------------------------------------------
    # Validate initialized SGP4 record
    # ---------------------------------------------------------
    #
    # check_satrec() raises ValueError when the initialized
    # orbital parameters are outside the valid SGP4 ranges.
    #
    check_satrec(sat)

    return sat


def _ensure_utc(timestamp: datetime) -> datetime:
    """
    Return a timezone-aware UTC datetime.

    Naive timestamps are explicitly interpreted as UTC rather
    than allowing the local machine timezone to influence
    propagation.
    """

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(
            tzinfo=timezone.utc
        )

    return timestamp.astimezone(timezone.utc)


def propagate_orbit(
    row,
    timestamp: datetime,
) -> PropagatedOrbitState:
    """
    Propagate one GP orbital record to a requested UTC time.

    Returns:
        PropagatedOrbitState containing TEME position in km
        and velocity in km/s.
    """

    # ---------------------------------------------------------
    # Parse and normalize timestamps
    # ---------------------------------------------------------
    epoch_dt = parse_epoch(
        row["EPOCH"]
    )

    target_dt = _ensure_utc(
        timestamp
    )

    # ---------------------------------------------------------
    # Build SGP4 satellite record
    # ---------------------------------------------------------
    sat = _build_sgp4_satellite(
        row
    )

    # ---------------------------------------------------------
    # Calculate minutes since GP epoch
    # ---------------------------------------------------------
    tsince_minutes = (
        target_dt - epoch_dt
    ).total_seconds() / 60.0

    # ---------------------------------------------------------
    # Propagate
    # ---------------------------------------------------------
    error, position, velocity = (
        sat.sgp4_tsince(
            tsince_minutes
        )
    )

    # ---------------------------------------------------------
    # Handle SGP4 errors
    # ---------------------------------------------------------
    error_message = ""

    if error != 0:
        error_message = getattr(
            sat,
            "error_message",
            "",
        )

        if not error_message:
            error_message = (
                "SGP4 propagation returned "
                f"error code {error}."
            )

    # ---------------------------------------------------------
    # Return orbital state
    # ---------------------------------------------------------
    return PropagatedOrbitState(
        object_name=str(
            row["OBJECT_NAME"]
        ).strip(),

        norad_cat_id=int(
            row["NORAD_CAT_ID"]
        ),

        timestamp=target_dt,

        position_x_km=float(
            position[0]
        ),

        position_y_km=float(
            position[1]
        ),

        position_z_km=float(
            position[2]
        ),

        velocity_x_km_s=float(
            velocity[0]
        ),

        velocity_y_km_s=float(
            velocity[1]
        ),

        velocity_z_km_s=float(
            velocity[2]
        ),

        sgp4_error=int(
            error
        ),

        error_message=error_message,
    )


def propagate_orbit_from_norad(
    norad_cat_id: int,
    timestamp: datetime,
    csv_path: str,
) -> PropagatedOrbitState:
    """
    Load a GP row by NORAD ID and propagate it
    to the requested time.
    """

    from .gp_loader import (
        get_satellite_by_norad,
    )

    row = get_satellite_by_norad(
        norad_cat_id,
        csv_path,
    )

    return propagate_orbit(
        row,
        timestamp,
    )
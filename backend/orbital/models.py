from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PropagatedOrbitState:
    """Simple orbital state returned by the SGP4 propagator."""

    object_name: str
    norad_cat_id: int
    timestamp: datetime
    position_x_km: float
    position_y_km: float
    position_z_km: float
    velocity_x_km_s: float
    velocity_y_km_s: float
    velocity_z_km_s: float
    sgp4_error: int
    error_message: str = ""
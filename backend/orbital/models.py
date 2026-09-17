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

@dataclass
class CloseApproachResult:
    """Structured result for a neighbourhood/conjunction analysis."""

    object1_norad_id: int
    object2_norad_id: int
    object1_name: str
    object2_name: str
    analysis_start_time: datetime
    analysis_end_time: datetime
    time_of_closest_approach: datetime
    minimum_separation_km: float
    relative_speed_km_s: float
    threshold_km: float
    is_candidate_close_approach: bool
    error_message: str = ""
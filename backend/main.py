from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from backend.orbital.gp_loader import get_satellite_by_norad
from backend.orbital.sgp4_propagator import propagate_orbit


def main() -> None:
    """Run a single real-object propagation example using the GP CSV."""
    csv_path = "data/raw/active_satellites_gp.csv"
    norad_id = 900
    propagation_time = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)

    row = get_satellite_by_norad(norad_id, csv_path)
    state = propagate_orbit(row, propagation_time)

    print("Object:", state.object_name)
    print("NORAD ID:", state.norad_cat_id)
    print("Epoch:", row["EPOCH"])
    print("Propagation time:", state.timestamp.isoformat())
    print("Position:")
    print(f"X: {state.position_x_km:.6f} km")
    print(f"Y: {state.position_y_km:.6f} km")
    print(f"Z: {state.position_z_km:.6f} km")
    print("Velocity:")
    print(f"VX: {state.velocity_x_km_s:.6f} km/s")
    print(f"VY: {state.velocity_y_km_s:.6f} km/s")
    print(f"VZ: {state.velocity_z_km_s:.6f} km/s")
    print("SGP4 error:", state.sgp4_error)


if __name__ == "__main__":
    main()

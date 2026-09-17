import numpy as np

from .models import PropagatedOrbitState

def _validate_timestamps(state1: PropagatedOrbitState, state2: PropagatedOrbitState) -> None:
    if state1.timestamp != state2.timestamp:
        raise ValueError("Cannot compare orbital states with different timestamps.")

def calculate_orbital_radius(state: PropagatedOrbitState) -> float:
    """Calculate the orbital radius (magnitude of position vector) in km."""
    pos = np.array([state.position_x_km, state.position_y_km, state.position_z_km])
    return float(np.linalg.norm(pos))

def calculate_velocity_magnitude(state: PropagatedOrbitState) -> float:
    """Calculate the velocity magnitude (speed) in km/s."""
    vel = np.array([state.velocity_x_km_s, state.velocity_y_km_s, state.velocity_z_km_s])
    return float(np.linalg.norm(vel))

def calculate_relative_position(state1: PropagatedOrbitState, state2: PropagatedOrbitState) -> np.ndarray:
    """Calculate the relative position vector (state2 - state1) in km."""
    _validate_timestamps(state1, state2)
    pos1 = np.array([state1.position_x_km, state1.position_y_km, state1.position_z_km])
    pos2 = np.array([state2.position_x_km, state2.position_y_km, state2.position_z_km])
    return pos2 - pos1

def calculate_relative_velocity(state1: PropagatedOrbitState, state2: PropagatedOrbitState) -> np.ndarray:
    """Calculate the relative velocity vector (state2 - state1) in km/s."""
    _validate_timestamps(state1, state2)
    vel1 = np.array([state1.velocity_x_km_s, state1.velocity_y_km_s, state1.velocity_z_km_s])
    vel2 = np.array([state2.velocity_x_km_s, state2.velocity_y_km_s, state2.velocity_z_km_s])
    return vel2 - vel1

def calculate_distance(state1: PropagatedOrbitState, state2: PropagatedOrbitState) -> float:
    """Calculate the Euclidean distance between two orbital states in km."""
    rel_pos = calculate_relative_position(state1, state2)
    return float(np.linalg.norm(rel_pos))

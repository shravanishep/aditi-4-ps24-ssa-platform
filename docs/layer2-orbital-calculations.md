# Layer 2: Orbital Calculations

This document describes the orbital calculations module added in Layer 2.

## Overview
The `backend.orbital.calculations` module provides pure mathematical functions that compute derived physical metrics from `PropagatedOrbitState` objects. These utilities are strictly designed to consume the TEME positions and velocities produced by SGP4 in Layer 1. 

**Important Notes:**
- Layer 2 operates solely on the existing TEME coordinates. It does NOT perform any coordinate frame transformations (e.g., to ECEF, J2000, or GCRF).
- All relative calculations rigorously enforce timestamp validation to ensure that physical state vectors are only compared when they correspond to exactly the same epoch.
- All vector calculations leverage NumPy arrays for efficiency and downstream interoperability.

## Mathematical Functions and Formulas

### Orbital Radius
Calculates the magnitude of the position vector.
- **Function**: `calculate_orbital_radius(state: PropagatedOrbitState) -> float`
- **Formula**: $r = \sqrt{x^2 + y^2 + z^2}$
- **Unit**: km

### Velocity Magnitude (Speed)
Calculates the magnitude of the velocity vector.
- **Function**: `calculate_velocity_magnitude(state: PropagatedOrbitState) -> float`
- **Formula**: $v = \sqrt{v_x^2 + v_y^2 + v_z^2}$
- **Unit**: km/s

### Relative Position
Calculates the vector pointing from `state1` to `state2`.
- **Function**: `calculate_relative_position(state1: PropagatedOrbitState, state2: PropagatedOrbitState) -> numpy.ndarray`
- **Formula**: $\Delta \vec{r} = \vec{r}_2 - \vec{r}_1$
- **Unit**: km

### Relative Velocity
Calculates the velocity difference between `state2` and `state1`.
- **Function**: `calculate_relative_velocity(state1: PropagatedOrbitState, state2: PropagatedOrbitState) -> numpy.ndarray`
- **Formula**: $\Delta \vec{v} = \vec{v}_2 - \vec{v}_1$
- **Unit**: km/s

### Distance
Calculates the Euclidean distance between two orbital states.
- **Function**: `calculate_distance(state1: PropagatedOrbitState, state2: PropagatedOrbitState) -> float`
- **Formula**: $d = \sqrt{\Delta x^2 + \Delta y^2 + \Delta z^2}$
- **Unit**: km

## Timestamp Validation
Any function that compares two states (`calculate_relative_position`, `calculate_relative_velocity`, `calculate_distance`) will explicitly verify that `state1.timestamp == state2.timestamp`. If the timestamps differ, a `ValueError` is raised, preventing nonsensical calculations.

# Layer 3: Neighbourhood and Conjunction Analysis

## Purpose
The purpose of Layer 3 is to identify and analyze potentially close approaches (conjunctions) between two orbital objects. It builds on the existing SGP4 propagation from Layer 1 and the mathematical distance/velocity calculations from Layer 2.

**Important Note**: This is a course-project analytical prototype based on public orbital data. It performs numerical searches to find the Time of Closest Approach (TCA) and minimum separation between two objects. It does **not** perform operational collision avoidance, compute collision probabilities, or assign risk scores. A "candidate close approach" simply means the minimum separation distance is below a configurable threshold.

## Architecture and Integration
- **Layer 1 Integration**: Layer 3 relies strictly on the `propagate_orbit` functionality. It propagates two objects simultaneously to identical timestamps.
- **Layer 2 Integration**: The distance between objects at each timestamp is evaluated using `calculate_distance`. The relative speed at TCA is computed using `calculate_relative_velocity`.
- **Core Function**: `find_closest_approach` performs a coarse-to-fine search over a specified time window to locate the minimum separation.
- **Result Model**: The analysis returns a structured `CloseApproachResult` dataclass summarizing the event.

## Coarse-to-Fine Search Algorithm
To avoid unnecessary computation while preserving accuracy, Layer 3 uses a two-pass numerical search strategy:
1. **Coarse Search**: Propagates the two objects at a fixed `coarse_step_sec` interval (default: 60s) from the analysis start time to the end time. It records the timestamp that yields the minimum separation.
2. **Fine Search**: Creates a localized window around the coarse minimum (from `coarse_minimum - coarse_step_sec` to `coarse_minimum + coarse_step_sec`, clamped to the analysis start/end times). It propagates the objects at a `fine_step_sec` interval (default: 1s) within this small window to pinpoint the approximate TCA.

## Configurable Threshold
The analysis takes a mandatory `threshold_km` parameter. If the `minimum_separation_km` at TCA is less than or equal to this threshold, the event is flagged as a `is_candidate_close_approach`. (For example, CelesTrak SOCRATES often uses 5 km as a screening threshold, but this value is fully configurable and not hard-coded).

## Handling Errors
If SGP4 propagation fails for a specific timestamp, that timestamp is skipped and the error is recorded. If enough valid samples remain, the best valid result is returned along with the error messages. If no valid states can be computed throughout the search, a `ValueError` is raised. 

## Limitations
- **Numerical Approximation**: The accuracy of the TCA and minimum separation depends on the chosen coarse and fine step sizes.
- **No Coordinate Transformations**: All positions and distances are calculated in the TEME frame directly derived from SGP4.
- **No Machine Learning**: Anomaly detection and advanced event intelligence are intentionally excluded from this layer.

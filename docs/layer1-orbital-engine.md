# Layer 1 orbital engine

## What GP data is

The CelesTrak GP CSV contains mean orbital element data in a modern format designed for SGP4 propagation. Each row represents a satellite state at an epoch, with fields such as mean motion, eccentricity, inclination, right ascension of the ascending node, argument of perigee, mean anomaly, and B* drag term.

## Why this project uses GP data

The project needs real orbital-element data that can be converted directly into an SGP4-compatible satellite record. The GP CSV is already in the required modern format and does not need conversion to legacy TLE text. This keeps the implementation closer to the actual CelesTrak source data and makes it reusable later in a backend service.

## Why SGP4 is used

SGP4 is a standard simplified general perturbations propagator used widely for near-Earth satellites. It is appropriate for this prototype because the input data is in the GP element set format that SGP4 expects. SGP4 provides a propagated orbital state from the elements; it is not a high-fidelity numerical orbit propagator and it should not be treated as operational-grade collision prediction.

## Input fields used by the propagator

The implementation uses these GP fields:

- `EPOCH`
- `MEAN_MOTION`
- `ECCENTRICITY`
- `INCLINATION`
- `RA_OF_ASC_NODE`
- `ARG_OF_PERICENTER`
- `MEAN_ANOMALY`
- `BSTAR`
- `MEAN_MOTION_DOT`
- `MEAN_MOTION_DDOT`
- `NORAD_CAT_ID`
- `CLASSIFICATION_TYPE`
- `OBJECT_NAME`

These are converted into the SGP4 satellite record with the correct angular units and time scaling expected by the `sgp4` library.

## Output units

The propagated orbit returns:

- position in kilometers (km)
- velocity in kilometers per second (km/s)

The output model stores:

- `position_x_km`
- `position_y_km`
- `position_z_km`
- `velocity_x_km_s`
- `velocity_y_km_s`
- `velocity_z_km_s`

## Data flow

1. Load the GP CSV from `data/raw/active_satellites_gp.csv`.
2. Validate the required columns and the numeric orbital values.
3. Select a record by `NORAD_CAT_ID`.
4. Parse `EPOCH` as a UTC datetime.
5. Initialize an `sgp4` `Satrec` using the GP values converted to the SGP4 expected units.
6. Propagate to the requested UTC timestamp.
7. Return the propagated position, velocity, and the SGP4 error code.

## How to run the example

From the project root:

```bash
python -m pip install -r requirements.txt
python backend/main.py
```

## Known limitations

- This Layer 1 implementation validates and propagates a single GP record from the provided CSV.
- SGP4 is suitable for prototype orbital-state propagation, not high-fidelity force modeling.
- The example is a learning prototype and is not a collision-warning system.
- This task intentionally does not implement SATCAT, conjunction analysis, ML, or frontend visualization.

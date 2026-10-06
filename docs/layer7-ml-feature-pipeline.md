# Layer 7 — ML Feature Engineering and Dataset Pipeline

## Purpose and Scope

Layer 7 creates the **ML-ready orbital feature dataset** that serves as the foundation
for future anomaly detection models (Layer 8+).

The pipeline ingests the public CelesTrak GP orbital element snapshot and uses the existing
Layer 1 SGP4 propagator to generate a time-series feature dataset, with one row per
(satellite, timestamp) observation.

This layer does **not** train any model.  It only produces and validates the dataset.

---

## Architecture

```
data/raw/active_satellites_gp.csv    ← CelesTrak GP snapshot
        │
        ▼
ml/pipeline/dataset_builder.py       ← Orchestrator and CLI
        │
        ├── ml/pipeline/config.py               ← Build parameters
        ├── ml/pipeline/feature_engineering.py  ← Feature computation
        └── ml/pipeline/validation.py           ← Quality checks
        │
        ▼
data/processed/
  orbital_features.parquet           ← ML-ready feature dataset
  orbital_features_metadata.json     ← Schema, provenance, statistics
```

Layers 1–6 are not modified by Layer 7.

---

## Propagation Strategy

For each satellite, the pipeline propagates the SGP4 model at **97 evenly-spaced UTC
timestamps** over a **24-hour window centred on the GP element-set epoch**:

- Window: `[epoch − 12 h, epoch + 12 h]`
- Step: 15 minutes
- Observations per satellite: 97

Centering the window on the epoch is a practical choice that limits the propagation
distance from the element-set epoch, which tends to reduce accumulation of numerical
error.  This is not a formal accuracy guarantee: SGP4 accuracy depends on the quality
of the element set, the orbital regime, and atmospheric conditions, among other factors.

Each satellite's observations are sorted by `t_offset_minutes` (minutes since the
satellite's GP epoch), which serves as the temporal coordinate for that satellite.

---

## Feature Schema

Each row is a **(satellite × timestamp)** observation with 40 columns.

### Identity / Metadata

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `norad_cat_id` | int32 | — | NORAD Catalog ID |
| `object_name` | string | — | Satellite name from GP CSV |
| `epoch_utc` | datetime (UTC) | — | GP element set epoch |
| `observation_utc` | datetime (UTC) | — | Absolute propagation timestamp |
| `t_offset_minutes` | float32 | min | Minutes from GP epoch; temporal axis |
| `sgp4_error` | int8 | — | SGP4 error code (0 = success) |
| `sgp4_error_message` | string | — | Error description (empty on success) |
| `split` | string | — | `"train"`, `"val"`, or `"test"` |

### Static Orbital Elements (from GP row)

| Column | Type | Unit | Source |
|--------|------|------|--------|
| `mean_motion_rev_day` | float32 | rev/day | GP `MEAN_MOTION` |
| `eccentricity` | float32 | — | GP `ECCENTRICITY` |
| `inclination_deg` | float32 | deg | GP `INCLINATION` |
| `raan_deg` | float32 | deg | GP `RA_OF_ASC_NODE` |
| `arg_of_pericenter_deg` | float32 | deg | GP `ARG_OF_PERICENTER` |
| `mean_anomaly_epoch_deg` | float32 | deg | GP `MEAN_ANOMALY` |
| `bstar` | float32 | 1/Re | GP `BSTAR` |
| `mean_motion_dot` | float32 | rev/day² | GP `MEAN_MOTION_DOT` |
| `mean_motion_ddot` | float32 | rev/day³ | GP `MEAN_MOTION_DDOT` |

### Derived Static Features

| Column | Type | Unit | Calculation |
|--------|------|------|-------------|
| `semi_major_axis_km` | float32 | km | `(μ / n²)^(1/3)`, μ = 398600.4418 km³/s² |
| `orbital_period_min` | float32 | min | `1440 / mean_motion_rev_day` |
| `perigee_km` | float32 | km | `a(1 − e) − 6371` |
| `apogee_km` | float32 | km | `a(1 + e) − 6371` |

### Propagated Physical State (NaN on SGP4 error)

| Column | Type | Unit | Source |
|--------|------|------|--------|
| `pos_x_km` | float32 | km | SGP4 TEME position X |
| `pos_y_km` | float32 | km | SGP4 TEME position Y |
| `pos_z_km` | float32 | km | SGP4 TEME position Z |
| `vel_x_km_s` | float32 | km/s | SGP4 TEME velocity X |
| `vel_y_km_s` | float32 | km/s | SGP4 TEME velocity Y |
| `vel_z_km_s` | float32 | km/s | SGP4 TEME velocity Z |

### Derived Propagated Features (NaN on SGP4 error)

| Column | Type | Unit | Calculation |
|--------|------|------|-------------|
| `orbital_radius_km` | float32 | km | `‖r⃗‖` |
| `altitude_km` | float32 | km | `orbital_radius_km − 6371` |
| `speed_km_s` | float32 | km/s | `‖v⃗‖` |
| `radial_vel_km_s` | float32 | km/s | `(r⃗ · v⃗) / ‖r⃗‖` |
| `cross_track_vel_km_s` | float32 | km/s | `‖r⃗ × v⃗‖ / ‖r⃗‖` |
| `angular_momentum_km2_s` | float32 | km²/s | `‖r⃗ × v⃗‖` |
| `specific_energy_km2_s2` | float32 | km²/s² | `v²/2 − μ/r` (negative = bound orbit) |

### Temporal Difference Features

The `d_*` features are **fixed-interval absolute differences** between consecutive
observations of the same satellite.  They are NOT rates-per-unit-time.
The first observation per satellite has NaN for all `d_*` columns.

To convert to a rate, divide by `dt_minutes`.

| Column | Type | Unit | Calculation |
|--------|------|------|-------------|
| `d_altitude_km` | float32 | km | `altitude_km[t] − altitude_km[t−1]` |
| `d_orbital_radius_km` | float32 | km | `orbital_radius_km[t] − orbital_radius_km[t−1]` |
| `d_speed_km_s` | float32 | km/s | `speed_km_s[t] − speed_km_s[t−1]` |
| `d_specific_energy_km2_s2` | float32 | km²/s² | `specific_energy[t] − specific_energy[t−1]` |
| `d_angular_momentum_km2_s` | float32 | km²/s | `angular_momentum[t] − angular_momentum[t−1]` |
| `dt_minutes` | float32 | min | `t_offset_minutes[t] − t_offset_minutes[t−1]` |

---

## SGP4 Error Handling

Any timestamp for which SGP4 returns a non-zero error code produces a row with:
- `sgp4_error` = the error code
- `sgp4_error_message` = the description
- All propagated and derived features set to `NaN`

The row is retained (not dropped) so that the error history is preserved and
downstream models can decide how to handle it.

If the GP row itself fails validation at build time (e.g., `check_satrec` raises),
the satellite is skipped entirely and logged to stderr.

---

## Data Leakage Prevention

Leakage prevention is enforced by two mechanisms:

1. **Per-satellite chronological split**: The train/val/test split is assigned in
   temporal order (ascending `t_offset_minutes`) within each satellite.  No shuffling
   is applied.  Train observations are always earlier than val, and val earlier than test.

2. **Backward-only finite differences**: The `d_*` temporal difference features are
   computed from the immediately preceding observation only.  No future observation is
   used to construct any feature for an earlier row.

Note: `t_offset_minutes` is a consistent temporal coordinate (minutes from the
satellite's own GP epoch) that enables chronological ordering within each satellite.
It does not, by itself, prevent leakage — leakage prevention comes from the split
methodology and the direction of differencing described above.

---

## Train / Validation / Test Split

The split is per-satellite and chronological:

| Split | Observations | Default fraction |
|-------|-------------|-----------------|
| train | First 60% of each satellite's rows | 0.60 |
| val   | Next 20% | 0.20 |
| test  | Final 20% | 0.20 |

For 97 observations: train=58, val=19, test=20.

The `split` column in the dataset is informational.  Future models may define their
own split strategy.

---

## Running the Pipeline

From the project root:

```bash
python -m ml.pipeline.dataset_builder \
    --gp-csv data/raw/active_satellites_gp.csv \
    --output data/processed/orbital_features.parquet \
    --window-hours 24 \
    --step-minutes 15 \
    --max-satellites 200
```

Use `--max-satellites 0` to process the full GP dataset (may take several minutes).

---

## Output Files

### `data/processed/orbital_features.parquet`

Parquet file with 40 columns and approximately `max_satellites × 97` rows.
Columns are stored as float32 for ML feature columns (not the intermediate
orbital computations, which remain float64 throughout the pipeline).

### `data/processed/orbital_features_metadata.json`

JSON sidecar containing:
- `build_info`: build timestamp, layer name
- `input`: GP CSV path, SHA-256 hash, file size
- `config`: all pipeline parameters that produced this dataset
- `output`: row count, column count, satellite count, SGP4 error statistics, split counts
- `schema`: column names and types
- `summary_statistics`: min/max/mean/null count for key physical features
- `notes`: dataset usage notes and caveats

---

## Reproducibility

Given the same GP CSV file and the same `PipelineConfig`, the pipeline produces
a dataset with identical:
- Satellite selection (sorted by NORAD_CAT_ID, capped by max_satellites)
- Timestamps for each satellite
- Feature values
- Row ordering
- Schema and split assignments

The SHA-256 hash of the GP CSV is embedded in the metadata so that any dataset
artefact can be traced back to the exact GP snapshot that produced it.

> **Note:** Parquet file bytes may differ across pyarrow versions or platforms due
> to internal encoding differences.  Reproducibility is at the DataFrame level
> (schema, values, row order), not at the byte level.

---

## Limitations

- **No space-weather features**: Atmospheric drag indices (F10.7, Kp) and other
  space-weather parameters are not included.  Aligning them correctly to per-satellite
  timestamps without introducing leakage requires careful design and is deferred to a
  future layer.

- **No pairwise conjunction features**: Conjunction features require O(N²)
  propagation across the catalogue.  They are excluded from the primary dataset and
  may be provided as an optional separate pipeline in future.

- **No synthetic anomalies**: All data in this dataset comes from SGP4 propagation
  of public CelesTrak GP orbital elements.  If synthetic anomalies are introduced
  in a future layer, they must be clearly labelled as simulated and kept separate
  from the real propagated data.

- **SGP4 limitations**: SGP4 is a simplified perturbation model.  Accuracy depends
  on the quality of the element set, the orbital regime, and physical conditions.
  This dataset is suitable for prototype anomaly detection but is not a substitute
  for high-precision astrodynamic propagators.

---

## Future Extensions (Layer 8+)

- Anomaly detection model training (Isolation Forest or similar)
- Unsupervised per-satellite baseline profiles
- SHAP-based feature importance
- Optional space-weather feature alignment
- Optional conjunction proximity features

# Layer 8 — Orbital Behaviour Anomaly Detection

## Purpose and Scope

Layer 8 introduces **unsupervised machine learning anomaly detection** for satellite orbital behaviour using the 40-column feature dataset constructed in Layer 7.

The primary objective is to detect unusual or unexpected orbital behaviour—such as unannounced maneuvers, sudden orbit decay, or energetic perturbations—using **Isolation Forest** on physics-grounded dynamic state and temporal difference features.

Layer 8 operates strictly within the ML package (`ml/models/`) and CLI. It does not introduce FastAPI endpoints or frontend UI components (reserved for Layer 9).

---

## Architecture

```
data/processed/orbital_features.parquet   ← Layer 7 feature dataset
        │
        ▼
ml/models/trainer.py                       ← Training pipeline & CLI
        │
        ├── ml/models/config.py            ← Hyperparameters & feature lists
        ├── ml/models/anomaly_detector.py  ← IsolationForest wrapper
        └── ml/models/synthetic_anomalies.py ← Physically consistent synthetic benchmarks
        │
        ▼
models/
  isolation_forest.joblib                 ← Serialized model binary
  isolation_forest_metadata.json          ← Model metadata & benchmark metrics
```

---

## Feature Selection Rationale

### The 12 Dynamic & Temporal Behavioural Features

The primary Isolation Forest detector inputs are restricted to **12 dynamic state magnitudes and temporal difference features**:

| Category | Feature Name | Unit | Description |
|----------|--------------|------|-------------|
| **Dynamic State** | `orbital_radius_km` | km | Instantaneous distance from Earth center |
| | `altitude_km` | km | Instantaneous altitude above mean Earth radius |
| | `speed_km_s` | km/s | Total scalar velocity magnitude |
| | `radial_vel_km_s` | km/s | Velocity component along radial position vector |
| | `cross_track_vel_km_s` | km/s | Velocity component perpendicular to orbital plane |
| | `angular_momentum_km2_s` | km²/s | Magnitude of specific orbital angular momentum ($\vec{r} \times \vec{v}$) |
| | `specific_energy_km2_s2` | km²/s² | Specific orbital energy ($v^2/2 - \mu/r$) |
| **Temporal Differences** | `d_altitude_km` | km | Change in altitude over preceding 15-minute step |
| | `d_orbital_radius_km` | km | Change in orbital radius over preceding 15-minute step |
| | `d_speed_km_s` | km/s | Change in speed over preceding 15-minute step |
| | `d_specific_energy_km2_s2` | km²/s² | Change in specific energy over preceding 15-minute step |
| | `d_angular_momentum_km2_s` | km²/s | Change in angular momentum over preceding 15-minute step |

### Exclusion of Static GP Orbital Elements

Static orbital elements (`semi_major_axis_km`, `inclination_deg`, `eccentricity`, `perigee_km`, `apogee_km`, `mean_motion_rev_day`, `orbital_period_min`) are **intentionally excluded** from detector input:

- **Reasoning**: Static GP elements define the broad orbital regime (LEO vs MEO vs GEO). Including them in decision tree splits causes Isolation Forest to partition satellites by regime—flagging ordinary GEO satellites as "anomalous" simply because their altitude differs from LEO satellites.
- **Outcome**: By training exclusively on dynamic magnitudes and temporal differences, the model detects **behavioural deviations** (e.g. unexpected rate of change or state vector anomaly for a given trajectory) regardless of whether the satellite orbits in LEO, MEO, or GEO.
- **Context Preservation**: Static elements remain in the dataset rows as regime context for auditing and downstream display.

---

## Preprocessing & Missing Data (NaN) Handling

1. **Physical Feature Values (No Scaling)**:
   - Isolation Forest builds axis-aligned decision trees using monotonic scalar splits (`feature > threshold`).
   - Physical feature values are passed directly to `IsolationForest` without normalization or `StandardScaler`.
2. **SGP4 Failed Propagations (`sgp4_error != 0`)**:
   - Rows where SGP4 propagation failed are filtered out prior to model input.
3. **Initial Observation NaNs**:
   - The first observation of each satellite (`t_offset_minutes = -720` min) has `NaN` for temporal difference features (`d_*`).
   - `prepare_features()` automatically imputes `d_*` temporal differences with `0.0` (representing zero initial change) for initial observations.

---

## Temporal Leakage Prevention

- **Train Split**: Model is fitted strictly on `split == "train"` (`IsolationForest.fit(X_train)`).
- **Validation Split**: Used for baseline score distribution checks and threshold tuning (`split == "val"`).
- **Test Split**: Held out for synthetic anomaly benchmark evaluation (`split == "test"`).
- Per-satellite chronological splitting (assigned in Layer 7) guarantees that future observations never inform past model training.

---

## Decision Threshold Calibration & Regime-Aware Analysis

- `contamination=0.02` is an initial hyperparameter for tree partition depth in scikit-learn's `IsolationForest`.
- To avoid threshold mismatch and arbitrary contamination-based cutoffs, the binary `is_anomaly` decision uses an explicit validation-selected cutoff on continuous `normalized_anomaly_score`:
  - `decision_threshold = 0.65`: Calibrated strictly on the validation split (`val_df`). Observations with `normalized_anomaly_score >= 0.65` are classified as `is_anomaly = True`.
  - `warning_threshold = 0.65`: Warning severity flag.
  - `critical_threshold = 0.85`: Critical severity flag.
- **Regime & Fleet Composition Insights**:
  - In a fleet comprising predominantly LEO satellites and a single GEO satellite (NORAD 2866), dynamic state magnitudes (`altitude_km`, `speed_km_s`, `angular_momentum_km2_s`) naturally separate the GEO satellite at tree roots.
  - In operational deployments with diverse orbital classes, regime-conditioned stratification or per-satellite baseline normalization allows evaluating satellites against their own nominal orbital envelopes.

---

## Score Output Schema

`OrbitalAnomalyDetector.predict()` appends four prediction columns to input DataFrames:

| Column | Type | Description |
|--------|------|-------------|
| `decision_score_raw` | float32 | Raw Isolation Forest path-length score from `score_samples()` |
| `normalized_anomaly_score` | float32 | Score mapped to $[0.0, 1.0]$ via logistic transformation. Higher score indicates higher degree of anomaly |
| `is_anomaly` | bool | `True` if predicted as an anomaly by decision boundary, `False` otherwise |
| `anomaly_severity` | string | `"normal"`, `"warning"`, or `"critical"` |

*Note*: `normalized_anomaly_score` is a continuous anomaly severity index in $[0.0, 1.0]$, not a probability. A score of 0.85 indicates high anomaly severity, not an "85% probability".

---

## Physically Consistent Synthetic Anomaly Evaluation

Unsupervised models are evaluated using controlled synthetic anomaly injection:

1. **Physical Consistency Requirement**:
   - Perturbations do not modify single features in isolation (which would create unphysical state vectors).
   - `inject_velocity_impulse_anomaly()` applies a velocity impulse $\Delta \vec{v}$ to state vectors and recomputes all dependent features (`speed`, `energy`, `angular_momentum`, `radial_vel`, and `d_*` differences).
   - `inject_altitude_step_anomaly()` applies an altitude step $\Delta h$ and recomputes vis-viva speed, energy, angular momentum, and `d_*` differences.
2. **Empirical Metrics**:
   - Models are evaluated on synthetic benchmark sets reporting: **ROC-AUC**, **PR-AUC**, **Precision**, **Recall**, and **F1 Score**.

---

## Scope Limitations & Scientific Integrity

- **SGP4 Propagation Baseline**: The training and evaluation dataset is generated via SGP4 analytical propagation from Space-Track General Perturbations (GP) element sets. SGP4 inherently simplifies real-world orbital dynamics, omitting higher-order non-spherical gravity terms, relativistic corrections, and unmodeled atmospheric density spikes.
- **Synthetic Benchmark**: All evaluation metrics are derived from controlled synthetic anomalies (simulated velocity impulses and circular decay steps). These benchmarks measure the algorithm's mathematical ability to detect sudden state and energetic deviations under simulated physics.
- **Disclaimer on Operational Readiness**: Layer 8 does **not** claim detection of real-world operational satellite maneuvers or operational flight readiness. True operational deployment requires real sensor tracking data (e.g., radar range/range-rate and optical astrometry), empirical maneuver ground truth catalogs, and multi-orbit diurnal baselines (> 24 hours for GEO/MEO satellites).

---

## Serialization & Artifacts

- **Model Binary**: `models/isolation_forest.joblib`
- **Metadata JSON**: `models/isolation_forest_metadata.json`

---

## CLI Usage

Train the model and run evaluation:

```bash
python -m ml.models.trainer
```

# Layer 14 — Advanced Operational Features: CAM Simulation, Event Intelligence, Collision Probability (Pc), and Containerization

## 1. Overview

Layer 14 completes the advanced operational capabilities of the **ADITI 4.0 PS24 SSA Platform** by introducing:
1. **Collision Avoidance Maneuver (CAM) Simulation**: Impulsive velocity-change ($\Delta V$) model propagated via an RK4 numerical integrator incorporating Earth's geopotential $J_2$ perturbation.
2. **Event Intelligence & Timeline**: Rule-based maneuver classification (`STATION_KEEPING`, `ORBIT_RAISE`, `ORBIT_DECAY`, `UNKNOWN`) backed by persistent SQLite storage with SHA-256 deduplication.
3. **Collision Probability ($P_c$) & Conjunction Data Message (CDM) Ingestion**: CCSDS-compliant CDM parser with covariance positive-semidefinite (PSD) validation and Foster's 2D encounter-plane collision probability calculation.
4. **Full Containerization**: Multi-stage Dockerfiles (`Dockerfile.backend`, `Dockerfile.frontend`) and orchestration (`docker-compose.yml`) for production deployment.

---

## 2. Feature 1: Collision Avoidance Maneuver (CAM) Simulation

### 2.1 Problem & Mathematical Formulation
When a conjunction is detected between a primary (protected) satellite and a secondary (debris/satellite), satellite operators plan a collision avoidance maneuver (CAM). Because applying a $\Delta V$ immediately changes the orbital state, mean-element TLE/SGP4 propagation is physically invalid post-maneuver. Layer 14 implements a numerical propagation engine:

- **Impulsive Model**:
  $$\mathbf{r}^+ = \mathbf{r}^-, \quad \mathbf{v}^+ = \mathbf{v}^- + \Delta\mathbf{v}$$
  where $\Delta\mathbf{v} = (\Delta v_x, \Delta v_y, \Delta v_z)$ in the inertial frame (km/s). Inputs are bounded to $\le 2.0\text{ km/s}$ to prevent unphysical inputs.
- **Equations of Motion (Two-Body + $J_2$ Perturbation)**:
  $$\ddot{\mathbf{r}} = -\frac{\mu}{r^3}\mathbf{r} + \mathbf{a}_{J_2}$$
  where:
  $$\mathbf{a}_{J_2} = -\frac{3\mu J_2 R_e^2}{2 r^5} \begin{bmatrix} x(1 - 5 z^2/r^2) \\ y(1 - 5 z^2/r^2) \\ z(3 - 5 z^2/r^2) \end{bmatrix}$$
  Constants: $\mu = 398600.4418\text{ km}^3/\text{s}^2$, $J_2 = 1.08263 \times 10^{-3}$, $R_e = 6378.137\text{ km}$.
- **Numerical Integration**: Explicit 4th-order Runge-Kutta (RK4) with fixed time steps ($\le 30\text{ s}$).
- **Comparison Metrics**:
  - Original vs. Modified Miss Distance ($d_\text{orig}$ vs $d_\text{mod}$).
  - Improvement: $\Delta d = d_\text{mod} - d_\text{orig} > 0 \implies \text{IMPROVED}$, else $\text{DEGRADED}$.

### 2.2 Disclaimer & Limitations
All simulated CAM outputs include mandatory operational caveats:
> *CAM simulation uses an idealized impulsive velocity change and two-body + $J_2$ numerical propagation. Results are advisory and must not be used as the sole basis for operational orbital maneuvers.*

---

## 3. Feature 2: Event Intelligence & Persistent Timeline

### 3.1 Maneuver Classifier
Isolation Forest detects general statistical anomalies in orbital time series but does not classify operational intent. Layer 14 introduces `backend.events.classifier.EventClassifier`, an interpretable rule-based classifier evaluating physical feature deviations:

| Classification | Primary Physical Criteria |
| :--- | :--- |
| `ORBIT_RAISE` | $\Delta a > +0.5\text{ km}$ OR $\Delta n < -0.001\text{ rev/day}$ with low eccentricity drift |
| `ORBIT_DECAY` | $\Delta a < -0.5\text{ km}$ OR $\Delta n > +0.001\text{ rev/day}$ with high drag parameter $B^*$ |
| `STATION_KEEPING` | Periodic small adjustments: $|\Delta a| < 0.5\text{ km}$, $|\Delta i| > 0.005^\circ$, $|\Delta e| < 0.0005$ |
| `UNKNOWN` | Anomaly confirmed but evidence insufficient to conclusively classify |

### 3.2 Persistent Event Store
- **Database**: SQLite (`data/events.db`) with automatic schema initialization.
- **Deduplication**: SHA-256 hash derived from `(norad_id, event_type, epoch_iso)`.
- **Query APIs**: Filter by `norad_id`, `event_type`, `classification`, and ISO time ranges.

---

## 4. Feature 3: Collision Probability ($P_c$) & CDM Parsing

### 4.1 CCSDS Conjunction Data Message (CDM) Parser
- Parses standard CCSDS CDM files (KVN format) capturing:
  - Relative miss distance, relative speed, TCA.
  - Primary & Secondary Cartesian states $(\mathbf{r}, \mathbf{v})$ in ICRF/EME2000.
  - $6 \times 6$ or $3 \times 3$ state covariance matrices in RTN / UVW coordinates.
- **Covariance Validation**: Verifies symmetric positive semi-definite (PSD) structure ($\lambda_i \ge 0$). If invalid, $P_c$ computation safely falls back or flags unavailable covariance.

### 4.2 Foster's 2D Encounter Plane Algorithm
- Projects relative position and combined covariance $\mathbf{C} = \mathbf{C}_1 + \mathbf{C}_2$ onto the 2D encounter plane (plane perpendicular to relative velocity $\mathbf{v}_\text{rel}$).
- Combined hard-body radius $R = R_1 + R_2$ (default $10\text{ m}$).
- Computes collision probability $P_c$:
  $$P_c = \frac{1}{2\pi \sigma_\xi \sigma_\eta \sqrt{1 - \rho^2}} \iint_{x^2 + y^2 \le R^2} \exp\left(-\frac{1}{2} \mathbf{x}^T \mathbf{C}_\text{enc}^{-1} \mathbf{x}\right) dx dy$$
  using rotated principal axes and high-order series approximation / adaptive numerical quadrature.

---

## 5. Feature 4: Containerization & Deployment

- **Backend**: Containerized via Python 3.12-slim with curl health check at `/health`.
- **Frontend**: Multi-stage build with Node 20 alpine + Nginx reverse proxying `/api` to the backend service.
- **Compose**: `docker-compose.yml` ties both services into a zero-config local deployment.

---

## 6. Verification & Test Suite Summary

- **Total Tests**: 219 passed, 0 failed, 1 warning (deprecation).
  - 186 original test cases (Layers 1–13).
  - 8 CAM simulation tests (`tests/test_maneuver_simulator.py`).
  - 11 Event intelligence & store tests (`tests/test_event_intelligence.py`).
  - 14 Collision probability & CDM parser tests (`tests/test_collision_probability.py`).
- **Frontend Build**: Vite production build succeeded (66 modules transformed, 0 errors).


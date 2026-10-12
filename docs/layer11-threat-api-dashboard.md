# Layer 11 — Threat Prioritization API & Dashboard Integration

## Purpose and Scope

Layer 11 exposes the **Layer 9 Threat Prioritization Engine** through the FastAPI backend and visualizes prioritized conjunction threats in the React/TypeScript dashboard.

Key objectives:
1. Provide structured REST API endpoints (`POST /threats/screen` and `GET /threats/screen`) consuming the Layer 10 `UnifiedCatalog` and invoking `screen_threats_from_catalog()`.
2. Support configurable candidate screening bounds, close approach thresholds, propagation windows, and data freshness policies.
3. Integrate an interactive, responsive threat prioritization dashboard component into the primary dashboard view (`DashboardPage`).
4. Faithfully preserve and visibly display data freshness warnings (stale orbital elements) and unverified classification provenance.
5. Strictly adhere to the scientific disclaimer: threat scores are heuristic prioritization indices, **NOT** collision probabilities ($P_c$).

> [!IMPORTANT]
> **Scientific & Operational Disclaimer:**
> Calculated threat scores represent analytical urgency and proximity ranking based on SGP4 propagation and catalogue metadata. They are **NOT** collision probabilities ($P_c$) and do not represent verified collision predictions. Public TLE/GP data without covariance matrices cannot determine operational collision probabilities. Analytical close approaches are not confirmed collisions.

---

## Backend API Specification

### 1. Endpoints

| Method | Path | Description | Tags |
|---|---|---|---|
| `POST` | `/threats/screen` | Primary screening endpoint accepting JSON body. | `threats` |
| `GET` | `/threats/screen` | Query-string adapter for lightweight screening and browser inspection. | `threats` |

### 2. Request Parameters (`ThreatScreeningRequest`)

| Field | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `protected_norad_ids` | `list[int] \| null` | `null` | Max 50 IDs, positive ints | Specific NORAD IDs to protect. If omitted, the first `max_protected_targets` active satellites from the catalogue are screened. |
| `protect_all_active` | `bool` | `false` | Boolean | If `true`, evaluates active satellites against candidate threats. |
| `max_protected_targets` | `int` | `5` | `1 <= n <= 50` | Maximum number of protected targets evaluated when `protected_norad_ids` is omitted. |
| `screening_threshold_km` | `float` | `50.0` | `0 < n <= 1000.0` | Close-approach distance screening threshold in kilometers. |
| `screening_window_hours` | `float` | `48.0` | `0 < n <= 168.0` | Forward propagation window from epoch in hours. |
| `max_threat_candidates` | `int` | `20` | `1 <= n <= 200` | Maximum candidate threat objects evaluated against each protected target. |
| `max_ranked_results` | `int` | `50` | `1 <= n <= 200` | Maximum ranked threat events returned. |
| `coarse_step_sec` | `float` | `60.0` | `10.0 <= n <= 3600.0` | Layer 3 coarse conjunction step size in seconds. |
| `fine_step_sec` | `float` | `1.0` | `0.1 <= n <= 60.0` | Layer 3 fine conjunction step size in seconds. |
| `max_epoch_age_days` | `float \| null` | `null` | `n > 0` | Optional maximum epoch age threshold in days for staleness detection. |
| `stale_data_policy` | `str` | `"flag"` | `"flag"` or `"exclude"` | Policy when encountering stale orbital data. `"flag"` includes events with visible warnings; `"exclude"` omits stale candidates. |

### 3. Example Request & Response

#### Request (`POST /threats/screen`)
```json
{
  "protected_norad_ids": [25544],
  "screening_threshold_km": 150.0,
  "screening_window_hours": 24.0,
  "max_threat_candidates": 20,
  "max_ranked_results": 10,
  "stale_data_policy": "flag"
}
```

#### Response (`200 OK`)
```json
{
  "events": [
    {
      "protected_norad_id": 25544,
      "protected_name": "ISS (ZARYA)",
      "protected_classification": "ACTIVE_SATELLITE",
      "threat_norad_id": 48274,
      "threat_name": "ONEWEB-0182",
      "threat_classification": "ACTIVE_SATELLITE",
      "threat_source_provenance": "active_satellites_gp (source_group_hint, no SATCAT)",
      "time_of_closest_approach": "2026-09-18T04:12:30+00:00",
      "minimum_separation_km": 112.45,
      "relative_speed_km_s": 14.821,
      "hours_to_tca": 16.2,
      "threat_anomaly_score": null,
      "threat_anomaly_severity": "unavailable",
      "risk_score": 0.584,
      "risk_severity": "warning",
      "risk_explanation": {
        "risk_score": 0.584,
        "risk_severity": "warning",
        "anomaly_data_available": false,
        "factors": {
          "separation": {
            "description": "Geometric proximity indicator — closer miss distance raises priority.",
            "raw_value_km": 112.45,
            "normalised": 0.775,
            "weight": 0.40,
            "contribution": 0.310
          },
          "relative_velocity": {
            "description": "Encounter consequence indicator — higher relative speed implies greater kinetic energy.",
            "raw_value_km_s": 14.821,
            "normalised": 0.988,
            "weight": 0.25,
            "contribution": 0.247
          },
          "time_to_tca": {
            "description": "Urgency indicator — sooner TCA means less time to respond.",
            "raw_value_hours": 16.2,
            "normalised": 0.135,
            "weight": 0.20,
            "contribution": 0.027
          },
          "anomaly_score": {
            "description": "Supplementary behavioural context from Layer 8.",
            "raw_value": "unavailable",
            "normalised": 0.0,
            "weight": 0.15,
            "contribution": 0.0
          }
        },
        "disclaimer": "Risk scores are heuristic priority indices based on SGP4-propagated geometry and unsupervised anomaly scores. They are NOT collision probabilities and must not be used for operational collision-avoidance decisions."
      },
      "screening_notes": [
        "STALE ORBITAL DATA: Threat object ONEWEB-0182 (NORAD 48274) epoch is 25.4 days old. Prediction reliability degraded."
      ]
    }
  ],
  "summary": {
    "protected_count": 1,
    "candidates_screened": 20,
    "pairs_evaluated": 20,
    "events_within_threshold": 1,
    "data_source_notes": [
      "Screening active satellites against active_satellites_gp.csv (active-only; no debris/RB data)."
    ],
    "config_summary": {
      "screening_threshold_km": 150.0,
      "screening_window_hours": 24.0,
      "max_threat_candidates": 20,
      "weights": {
        "separation": 0.40,
        "relative_velocity": 0.25,
        "anomaly_score": 0.15,
        "time_to_tca": 0.20
      }
    },
    "disclaimer": "Risk scores are heuristic priority indices based on SGP4-propagated geometry and unsupervised anomaly scores. They are NOT collision probabilities and must not be used for operational collision-avoidance decisions."
  }
}
```

---

## Frontend Dashboard Integration

### 1. Architecture & Components
- **API Client Module** (`frontend/src/api/threats.ts`):
  - `screenThreats(params?: ThreatScreeningRequest): Promise<ThreatScreeningResponse>`
  - Utilizes existing `apiFetch()` with standard error mapping and HTTP status tracking.
- **Vite Proxy** (`frontend/vite.config.ts`):
  - Adds `/threats` proxy targeting backend `http://localhost:8000` to prevent CORS issues in development.
- **Threat Prioritization Panel** (`frontend/src/components/threats/ThreatPrioritizationPanel.tsx`):
  - Embedded into `frontend/src/pages/DashboardPage.tsx`.
  - Provides screening controls, disclaimer banner, summary metric cards, ranked events list, expandable factor breakdown, visible stale-data warnings, and unverified classification badges.
- **Type Definitions** (`frontend/src/types/api.ts`):
  - Strict TypeScript interfaces for `ThreatEvent`, `ThreatFactorBreakdown`, `ThreatFactorItem`, `ThreatScreeningRequest`, `ThreatScreeningResponse`, and `ThreatScreeningSummary`.

### 2. User Interface Features
- **Controls & Actions**:
  - Distance threshold selector (km).
  - Maximum candidates selector (10, 20, 50).
  - Stale data policy selector (`flag` vs `exclude`).
  - Refresh button triggering real-time re-screening with loading spinner.
- **Ranked Events List**:
  - Sorted descending by composite `risk_score`.
  - Color-coded severity badges: `Critical` (red), `Warning` (amber), `Low` (slate).
  - Highlighting protected satellite and candidate threat NORAD IDs and object names.
  - Normalized object classifications (`ACTIVE_SATELLITE`, `INACTIVE_SATELLITE`, `ROCKET_BODY`, `DEBRIS`, `UNKNOWN`).
  - Conjunction metrics: minimum separation (km), relative velocity (km/s), time to TCA (hours & ISO UTC).
- **Factor Decomposition Accordion**:
  - Interactive "Inspect Contributing Factors" button expanding factor breakdown:
    - Separation proximity factor raw value, weight, and contribution.
    - Relative velocity encounter consequence raw value, weight, and contribution.
    - Encounter urgency (TCA) raw value, weight, and contribution.
    - Anomaly context (or explicit note when Layer 8 detector is unconfigured).
- **Data Quality & Provenance Visibility**:
  - Yellow/amber alert pills for stale orbital elements with degradation warning.
  - Provenance badge distinguishing SATCAT-verified records from `source_group_hint`.
- **States Handled**:
  - Loading: animated spinner while orbital propagation is in progress.
  - Empty: informative message when 0 events fall within the threshold.
  - Error: prominent error alert with retry button.

---

## Operational Constraints & Safeguards

1. **Unbounded Pairwise Screening Prevention**:
   - Evaluating all pairs between 16,000 satellites would require $>1.28 \times 10^8$ propagation calculations, leading to request timeouts.
   - The backend enforces `max_protected_targets <= 50`, `max_threat_candidates <= 200`, and `protected_norad_ids <= 50`.
   - Default screening evaluates 5 protected targets against 20 candidates, completing in seconds while maintaining interactive responsiveness.
2. **Caching Strategy**:
   - The default `UnifiedCatalog` is cached in memory and invalidated automatically if `active_satellites_gp.csv` modification time changes.
   - Non-default requests (e.g. custom `max_epoch_age_days` or `stale_data_policy="exclude"`) build an isolated configured catalogue instance.
3. **Data Freshness Enforcement**:
   - Stale data cannot be presented as reliable current predictions. If `stale_data_policy="flag"`, explicit warnings are prepended to `screening_notes`.
   - If `stale_data_policy="exclude"`, stale objects are filtered out before propagation.

---

## Verification & Test Results

### 1. Test Suite (`tests/test_threat_api.py`)
18 targeted test cases covering:
- Explicit protected NORAD ID POST screening.
- GET query-string adapter with aliases (`threshold_km`, `max_candidates`, `max_targets`, `stale_policy`).
- Empty result handling with 200 status code and `events: []`.
- Parameter validation: negative thresholds, out-of-range windows, candidate limits, invalid policies, negative NORAD IDs, and oversized target lists (422 status code).
- 404 response for unknown protected NORAD IDs.
- 422 response when an explicit protected NORAD ID has stale orbital data and `stale_data_policy="exclude"`.
- 200 empty summary response when default sampling has no non-stale objects under `stale_data_policy="exclude"`.
- 503 response when underlying GP datasets are unavailable.
- Metadata and classification preservation in event payloads.
- Stale data warning preservation in `screening_notes`.
- Stale data exclusion policy verification.

### 2. Full Regression Suite
- Total tests: **161 passed, 0 failures** (`python -m pytest`).
- Frontend typecheck and production build: **Passed with 0 errors** (`npm run build`).

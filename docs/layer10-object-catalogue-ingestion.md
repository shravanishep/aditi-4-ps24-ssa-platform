# Layer 10 — Broader Object Catalogue & Orbital-Data Ingestion

## 1. Purpose and Scope

Layer 10 expands the platform's space object catalogue and orbital-data ingestion architecture beyond active-only satellite records.

The primary objective is to enable the platform to ingest, validate, classify, and deduplicate multiple orbital data sources alongside SATCAT metadata. This allows the threat-prioritization engine (Layer 9) to evaluate protected active satellites against a broader population of Earth-orbiting objects—including inactive satellites, rocket bodies, and debris—whenever suitable orbital records are provided.

> [!IMPORTANT]
> **Operational & Certification Disclaimer:**
> The catalogue data processed by this platform originates from unclassified public sources (such as CelesTrak) and simplified SGP4 general perturbations (GP). Downloading or assembling this catalogue does **not** make orbital records real-time or certified for operational flight safety. The platform is an educational and research prototype.

---

## 2. Architecture & Data Flow

```
Data Sources:
  ├── data/raw/active_satellites_gp.csv (Local Active GP CSV, 16,047 objects)
  ├── Local Debris / Rocket Body GP CSVs (Configurable via GPSourceConfig)
  ├── Local SATCAT CSV (Configurable, e.g. data/raw/satcat.csv)
  └── Remote CelesTrak Endpoints (Optional, configurable, mockable)
          │
          ▼
backend/catalog/source_adapter.py     ← Local reader & optional remote fetcher with atomic cache
          │
          ├── backend/catalog/satcat_parser.py  ← CelesTrak SATCAT parser & classification mapper
          ├── backend/catalog/validator.py      ← GP row validation & deterministic deduplication
          │
          ▼
backend/catalog/catalog_builder.py    ← Unified catalogue assembly pipeline
          │
          ▼
backend/catalog/models.py (UnifiedCatalog)
          │
          ├── Objects lookup & filtering (CatalogObject)
          ├── Summary statistics & Freshness tracking (CatalogSummary)
          └── Export to SGP4/Layer 9 DataFrame (to_gp_dataframe)
                  │
                  ▼
ml/models/threat_prioritization.py    ← screen_threats_from_catalog()
```

---

## 3. Data Sources Supported and Current Environment Status

### Supported Sources
1. **Local General Perturbations (GP) CSVs**:
   - Primary: `data/raw/active_satellites_gp.csv` (16,047 active satellites, present in local workspace).
   - Additional: Any GP-format CSV supplied via `GPSourceConfig` for rocket bodies, debris, or inactive payloads.
2. **CelesTrak SATCAT CSV**:
   - Local: `data/raw/satcat.csv` (if present or cached).
   - Remote: `https://celestrak.org/pub/satcat.csv` (optional remote fetch).
3. **Public CelesTrak GP Endpoints**:
   - Configurable remote GP CSV endpoints (e.g. `https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=csv`).

### Genuinely Available vs. Configurable Categories
- **Currently available in workspace without network access**:
  - `ACTIVE_SATELLITE`: 16,047 objects from `data/raw/active_satellites_gp.csv`.
- **Configurable / Verified via Ingestion Architecture**:
  - `INACTIVE_SATELLITE`, `ROCKET_BODY`, `DEBRIS`, and `UNKNOWN` are fully supported by the parser, validator, and classification mapping pipeline.
  - To screen active satellites against real debris or rocket bodies in an operational run, the user/operator supplies corresponding GP CSV files (or enables optional remote retrieval).

---

## 4. Object Classification Mapping

Raw SATCAT fields (`OBJECT_TYPE`, `OPS_STATUS_CODE`, `DECAY_DATE`) are mapped to five normalized enum values:

| Normalized Category | Raw `OBJECT_TYPE` | Raw `OPS_STATUS_CODE` | Decay Date Condition | Description |
|---|---|---|---|---|
| `ACTIVE_SATELLITE` | `PAY`, `PAYLOAD` | `+`, `P`, `B`, `S`, `X` | Empty / None | Verified operational payload. |
| `INACTIVE_SATELLITE` | `PAY`, `PAYLOAD` | `-`, `D` | Any, or decayed date set | Defunct, non-operational, or decayed payload. |
| `ROCKET_BODY` | `R/B`, `RB`, `ROCKET BODY` | Any | Any | Spent upper stage or rocket booster. |
| `DEBRIS` | `DEB`, `DEBRIS` | Any | Any | Fragmentation, mission-related, or collision debris. |
| `UNKNOWN` | `UNK` or missing, or `PAY` without operational status (`?` or blank) | `?` or blank | Empty / None | Operational status or object type unestablished by source. |

### Provenance and Verification Distinction
The catalogue strictly differentiates classification source provenance:
- **`classification_verified: True` (`classification_source: "satcat"`):** Explicitly confirmed by authoritative SATCAT metadata records.
- **`classification_verified: False` (`classification_source: "source_group_hint"`):** Inferred only from the input file grouping (e.g. `active_satellites_gp.csv`) when SATCAT metadata is unavailable. The provenance string explicitly records `"(source_group_hint, no SATCAT)"`.
- **`classification_verified: False` (`classification_source: "unverified"`):** Assigned `UNKNOWN` when neither SATCAT nor a source group hint provides an operational designation.

> [!NOTE]
> **No Presumed Status Rule:**
> A payload record is **not** assumed to be operational simply because it appears in a general perturbations dataset. If SATCAT metadata is missing or does not confirm operational status (`+`, `P`, `B`, `S`, `X`), operational status remains unestablished and cannot be presented as verified.

---

## 5. Validation, Deduplication, and Orbital-Data Freshness Policy

### Validation Rules
Every GP row is checked against strict numeric and physical bounds:
1. `NORAD_CAT_ID`: Positive integer $> 0$.
2. `MEAN_MOTION`: Strictly positive $> 0.0$ rev/day.
3. `ECCENTRICITY`: Bounded in $[0.0, 1.0)$ for closed orbits.
4. `INCLINATION`: Bounded in $[0.0, 180.0]^\circ$.
5. `EPOCH`: Valid ISO-8601 or standard GP datetime, parsed to timezone-aware UTC.
6. Epoch freshness: Tracked as `epoch_age_days = (reference_time - epoch) / 86400.0`.

### Configurable Freshness & Stale-Data Policy
Orbital state prediction accuracy degrades over time due to atmospheric drag, solar radiation pressure, and unmodeled maneuvers. Layer 10 implements an explicit, configurable freshness policy:
- **`max_epoch_age_days`**: Threshold in days beyond which an orbital record is marked `is_stale = True` (freshness status: `"stale"`). Configurable because acceptable freshness depends on orbit regime and mission context.
- **`stale_data_policy = "flag"` (Default)**: Stale objects are retained in the catalogue and evaluated during screening, but are **visibly flagged** with a prominent `STALE ORBITAL DATA` warning in `ThreatEvent.screening_notes`, preventing stale records from silently being treated as current.
- **`stale_data_policy = "exclude"`**: Stale objects exceeding `max_epoch_age_days` are excluded from the screening DataFrame, with exclusions logged in catalogue summaries and screening notes.
- **Catalogue Summary Freshness Tracking**: `CatalogSummary` reports exact counts for `fresh_records_count`, `stale_records_count`, `missing_epoch_count`, `freshest_epoch`, `oldest_epoch`, and `median_epoch_age_days`.

### Deduplication Policy
When the same NORAD catalogue ID appears across multiple GP sources or duplicate rows within a file:
- **Rule**: **Latest valid epoch wins**. The record with the newer epoch is preserved.
- If epochs are identical: The first valid record encountered is preserved.
- Superseded and discarded records are logged into `UnifiedCatalog.rejections` with reasons.

### Non-Destructive Raw Data Rule
Raw input files in `data/raw/` are treated as read-only. Atomic temporary file operations ensure remote downloads or cache writes never overwrite existing files upon network failure.

---

## 6. How to Run the Pipeline

### Basic Execution (Python API)
```python
from backend.catalog import CatalogConfig, GPSourceConfig, build_unified_catalog
from ml.models.threat_config import ThreatConfig
from ml.models.threat_prioritization import screen_threats_from_catalog

# 1. Configure sources (local active GP + custom debris GP + local SATCAT)
config = CatalogConfig(
    gp_sources=[
        GPSourceConfig(source_name="active", path="data/raw/active_satellites_gp.csv"),
        GPSourceConfig(source_name="debris", path="data/raw/debris_gp.csv"),  # optional
    ],
    satcat_path="data/raw/satcat.csv",
    allow_remote_fetch=False,
)

# 2. Build unified catalogue
catalog = build_unified_catalog(config=config)
print(f"Total objects: {len(catalog)}")
print(catalog.summary().counts_by_classification)

# 3. Screen threats against protected active satellites
threat_config = ThreatConfig(
    protected_norad_ids=[25544],  # e.g., ISS
    screening_threshold_km=50.0,
    screening_window_hours=48.0,
)
results = screen_threats_from_catalog(catalog=catalog, config=threat_config)

for event in results.events:
    print(
        f"Protected: {event.protected_name} ({event.protected_classification}) vs "
        f"Threat: {event.threat_name} ({event.threat_classification}) | "
        f"Risk: {event.risk_score:.3f} [{event.risk_severity}]"
    )
```

---

## 7. Example Output Schema

### Catalogue Summary (`CatalogSummary`)
```json
{
  "total_objects": 16047,
  "counts_by_classification": {
    "ACTIVE_SATELLITE": 16047,
    "INACTIVE_SATELLITE": 0,
    "ROCKET_BODY": 0,
    "DEBRIS": 0,
    "UNKNOWN": 0
  },
  "counts_by_source": {
    "active_satellites_gp (no SATCAT)": 16047
  },
  "objects_with_orbital_data": 16047,
  "objects_without_orbital_data": 0,
  "rejected_records_count": 0,
  "freshest_epoch": "2026-09-16T06:18:25.786080+00:00",
  "oldest_epoch": "2026-09-15T19:25:28.581312+00:00",
  "median_epoch_age_days": 26.37
}
```

### Threat Event with Layer 10 Metadata (`ThreatEvent`)
```json
{
  "protected_norad_id": 25544,
  "protected_name": "ISS (ZARYA)",
  "protected_classification": "ACTIVE_SATELLITE",
  "threat_norad_id": 33504,
  "threat_name": "IRIDIUM 33 DEB",
  "threat_classification": "DEBRIS",
  "threat_source_provenance": "debris_gp+satcat",
  "minimum_separation_km": 14.8,
  "relative_speed_km_s": 12.1,
  "hours_to_tca": 18.5,
  "risk_score": 0.684,
  "risk_severity": "warning"
}
```

---

## 8. Test Coverage

The ingestion pipeline is tested in [`tests/test_catalog_ingestion.py`](file:///c:/Users/shrav/OneDrive/Third%20Year%20Lab%20and%20TUt/ml_cp/aditi-4-ps24-ssa-platform/tests/test_catalog_ingestion.py):
- Full classification mapping across active, inactive, rocket body, debris, unknown.
- Validation bounds and rejection audits (negative NORAD ID, negative mean motion, malformed epoch).
- Deterministic deduplication (latest epoch wins).
- Multi-source GP and SATCAT joins.
- Mocked remote HTTP downloads, timeouts, HTTP 404, and network failure atomic cache protection.
- Layer 9 integration via `screen_threats_from_catalog()`.

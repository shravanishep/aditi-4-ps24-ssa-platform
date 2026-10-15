# Layer 12 — Automated Data Refresh & End-to-End Validation

## Purpose & Scope

Layer 12 introduces a robust, configurable **Automated Data Refresh & Synchronization Engine** to maintain catalogue currency, validate downloaded orbital elements, enforce strict data provenance, and expose freshness metrics to the API and frontend dashboard.

This capability bridges the offline research snapshot with real-world public orbital feeds while ensuring that:
1. Malformed or partial downloads never overwrite or corrupt the existing local catalogue.
2. Retrieval timestamps are strictly distinguished from orbital epoch dates.
3. Automated polling avoids aggressive request rates, adhering to public CelesTrak availability guidelines.
4. Downstream threat screening and conjunction analysis pipelines continue operating smoothly on refreshed data.

> [!IMPORTANT]
> **Research & Prototyping Disclaimer:**
> This platform is an educational and research prototype developed for Space Situational Awareness exploration. It utilizes public general perturbations (GP) data without full error-covariance matrices. Downloaded orbital elements and calculated threat indices are advisory heuristics for research prioritization and must **NOT** be used for operational collision warning or avoidance maneuvers.

---

## Architecture Overview

```
+-----------------------------------------------------------------------------------+
|                            CelesTrak Remote Feeds                                 |
|  - Active GP: https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=csv |
|  - SATCAT:    https://celestrak.org/pub/satcat.csv                                |
+----------------------------------------+------------------------------------------+
                                         | HTTP GET (with retries & backoff)
                                         v
+-----------------------------------------------------------------------------------+
|                      DataRefreshService (backend.refresh.service)                 |
|  1. Fetch with timeout & exponential backoff                                      |
|  2. In-memory validation (CSV format, minimum rows, required headers)             |
|  3. Physical bounds validation (MEAN_MOTION > 0, 0 <= ECC < 1, valid EPOCH)       |
|  4. Orbital freshness evaluation (oldest/newest epoch, epoch age in days)        |
+----------------------------------------+------------------------------------------+
                                         | Atomic Replace (tempfile.replace)
                                         v
+----------------------------------------+------------------------------------------+
|                     Local Snapshots & Metadata Storage                            |
|  - data/raw/active_satellites_gp.csv (Atomic overwrite only upon full validation) |
|  - data/raw/satcat.csv               (Optional metadata verification)             |
|  - data/catalog_refresh_metadata.json (Persistent sync history & epoch metrics)   |
+----------------------------------------+------------------------------------------+
                                         | Cache Invalidation
                                         v
+----------------------------------------+------------------------------------------+
|                       FastAPI Backend & React Dashboard                           |
|  - GET /catalog/status              (Read-only freshness metrics & warnings)     |
|  - POST /threats/screen             (Screens directly against refreshed data)     |
|  - CatalogFreshnessCard             (Glassmorphism status card in Dashboard UI)   |
+-----------------------------------------------------------------------------------+
```

---

## Core Components

### 1. `DataRefreshService` (`backend.refresh.service`)
The central orchestrator for data retrieval, validation, and persistence:
- **Resilient Retrieval**: Configurable `http_timeout_seconds` (default: 15.0s), `max_retries` (default: 3), and exponential backoff (`backoff_factor * 2^attempt`).
- **Pre-Commit Validation**:
  - Validates CSV syntax before touching the filesystem.
  - Rejects empty or whitespace-only bodies.
  - Enforces `min_expected_records` (default: 50) to catch partial or truncated transfer anomalies.
  - Confirms mandatory orbital headers (`NORAD_CAT_ID`, `EPOCH`, `MEAN_MOTION`, `ECCENTRICITY`, `INCLINATION`, `RA_OF_ASC_NODE`, `ARG_OF_PERICENTER`, `MEAN_ANOMALY`).
  - Evaluates individual rows with physical bounds checks (`validate_gp_row`).
- **Atomic Replacement**:
  - Incoming content is written to a temporary file (`NamedTemporaryFile`) within the target directory.
  - Upon successful validation, the file is atomically renamed to the target destination (`temp_path.replace(dest)`).
  - If validation fails at any point, the temporary file is discarded, and the existing dataset snapshot remains 100% intact.
- **Cache Invalidation**: Triggers `invalidate_catalog_cache()` on success so active API instances immediately serve updated orbits.

### 2. Freshness & Provenance Tracking (`backend.refresh.metadata`)
Distinguishes retrieval time from orbital element age:
- `retrieved_at`: UTC timestamp of the HTTP download.
- `oldest_epoch` & `newest_epoch`: Min/max orbital state timestamps recorded in the TLEs.
- `max_epoch_age_days`: Time elapsed between current UTC time and the oldest element in the dataset.
- `stale_records_count`: Number of objects exceeding `max_epoch_age_days` (default threshold: 30 days).
- `classification_source`: Tracks whether records are `satcat` verified or derived from `source_group_hint`.

Metadata is atomically persisted to `data/catalog_refresh_metadata.json`.

### 3. In-Process & OS-Level Scheduling (`backend.refresh.scheduler`)
Designed with **zero heavy dependencies** (no Celery, Airflow, or Redis):
- **In-Process**: `PeriodicRefreshScheduler` operates on a background Python daemon thread, using `threading.Event.wait()` for responsive start/stop control and configurable intervals (e.g., 24 hours).
- **OS-Level Alternative (Recommended for Production)**:
  - **Linux / macOS `cron`**:
    ```bash
    0 2 * * * cd /path/to/platform && python -m backend.refresh.cli >> /var/log/aditi_refresh.log 2>&1
    ```
  - **Windows Task Scheduler**:
    ```powershell
    schtasks /create /tn "AditiDataRefresh" /tr "python -m backend.refresh.cli" /sc daily /st 02:00
    ```

---

## Command-Line Interface (CLI)

The refresh service includes a command-line interface for development, manual sync, and staging:

```bash
# 1. Inspect current catalogue freshness and sync metadata
python -m backend.refresh.cli --status

# 2. Dry-run validation of active satellites (verifies remote download without overwriting local files)
python -m backend.refresh.cli --sources active_satellites_gp --dry-run

# 3. Full manual refresh of all enabled sources
python -m backend.refresh.cli

# 4. Download into a staging directory for manual review
python -m backend.refresh.cli --output-dir data/staging

# 5. Run the in-process periodic scheduler in the foreground (24-hour cycle)
python -m backend.refresh.cli --schedule --interval-hours 24.0
```

---

## API & Dashboard Integration

### 1. Read-Only API Endpoint (`GET /catalog/status`)
Exposes catalogue health, epoch age, and sync history:

```json
{
  "last_refresh_attempt": "2026-10-12T15:30:00Z",
  "last_successful_refresh": "2026-10-12T15:30:00Z",
  "refresh_status": "success",
  "total_objects": 16047,
  "active_satellites": 16047,
  "with_orbital_data": 16047,
  "stale_objects": 0,
  "oldest_epoch": "2026-08-18T01:47:07.105920+00:00",
  "newest_epoch": "2026-09-21T14:50:11.752512+00:00",
  "max_epoch_age_days": 55.45,
  "sources": {
    "active_satellites_gp": {
      "source_name": "active_satellites_gp",
      "url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=csv",
      "dest_path": "data/raw/active_satellites_gp.csv",
      "retrieved_at": "2026-10-12T15:30:00Z",
      "success": true,
      "bytes_downloaded": 2410605,
      "total_records": 16047,
      "valid_records": 16047,
      "rejected_records": 0,
      "max_epoch_age_days": 55.45,
      "stale_records_count": 0,
      "classification_source": "source_group_hint"
    }
  },
  "warnings": [
    "Data retrieval timestamp reflects file download time, NOT orbital element generation epoch.",
    "Orbital elements have an epoch age of 55.5 days. Propagation accuracy degrades over time; predictions are advisory."
  ],
  "data_source_notes": [
    "Catalogue currently contains active satellites from CelesTrak GP dataset.",
    "Classification is based on SATCAT metadata where available, or source group hints."
  ],
  "disclaimer": "Calculated threat scores and conjunction analyses are heuristic priority indices. They are NOT certified collision probabilities and must not be used for operational avoidance maneuvers."
}
```

### 2. Frontend UI (`CatalogFreshnessCard.tsx`)
Embedded in the main `DashboardPage`:
- **Live Sync Badge**: Visual indicators for `Fresh` (emerald), `Partial` (amber), `Failed` (rose), or `Local Snapshot` (slate).
- **Metric Cards**: Total catalogued objects, active satellites count, oldest orbital epoch age in days, and last sync timestamp.
- **Propagation Warning Banner**: Highlights advisory notices when orbital elements exceed acceptable age limits.
- **Manual Status Refresh Button**: Allows operators to re-query catalogue status without re-downloading remote files.

---

## Verification & Test Results

### 1. Targeted Layer 12 Suite (`tests/test_data_refresh.py`)
17 automated tests covering:
- Resilient HTTP retrieval with retries and exponential backoff.
- In-memory CSV validation and detection of corrupted or non-CSV payloads.
- Atomic file replacement and preservation of last-known-good datasets on network/timeout failure.
- Rejection of empty bodies and suspiciously incomplete downloads.
- Epoch age calculation and stale record counting.
- Dry-run validation without file mutations.
- Cache invalidation callback invocation.
- Refresh metadata serialization, persistence, and recovery from missing files.
- In-process scheduler lifecycle (`start`, `stop`, `is_running`, `trigger_now`).
- CLI commands (`--status`, `--dry-run`, `--sources`).
- Read-only `/catalog/status` API endpoint response semantics.
- End-to-end threat screening on refreshed catalogue cache.

### 2. Regression & Build Status
- **Targeted Tests**: 17 passed, 0 failures.
- **Full Backend Regression Suite**: **178 passed, 0 failures** (`python -m pytest`).
- **Frontend Production Build**: **Passed with 0 errors** (`npm run build`).
- **Git Tree Check**: `git diff --check` clean.

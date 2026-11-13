# Docker Containerization & Deployment Guide

This document describes how to build, run, and deploy the **ADITI 4.0 Space Situational Awareness (SSA) Platform** using Docker and Docker Compose.

---

## 1. Architecture Overview

The containerized deployment consists of two cooperating services:

```
[ Browser Client ]
       │
       ▼ (Port 80)
┌──────────────────────────────────────────────┐
│  aditi-frontend (Nginx container)            │
│  - Serves compiled React + Vite + Cesium     │
│  - Proxies /health, /satellites, /events ... │
└──────────────────────┬───────────────────────┘
                       │ Internal Docker Network (backend:8000)
                       ▼
┌──────────────────────────────────────────────┐
│  aditi-backend (FastAPI / Python 3.12)       │
│  - SGP4 orbit propagation                    │
│  - Conjunction assessment & CAM simulation   │
│  - Isolation Forest anomaly detection        │
│  - SQLite event persistence                  │
│  - Foster 2D collision probability (Pc)      │
└──────────────────────┬───────────────────────┘
                       │ Persistent Volume Mounts
                       ▼
            [ ./data ] & [ ./models ]
```

---

## 2. Prerequisites

- **Docker Engine**: version 24.0+
- **Docker Compose**: version 2.20+
- **Host Memory**: 4 GB RAM recommended for CesiumJS and pandas in-memory data processing.

---

## 3. Quick Start (Single Command)

### Step 1: Clone and Configure Environment

```bash
git clone <repo-url>
cd aditi-4-ps24-ssa-platform

# Copy the environment template
cp .env.example .env
```

*(Optional)* Fill in your `SPACE_TRACK_USERNAME` and `SPACE_TRACK_PASSWORD` in `.env` if you wish to run remote automated data refreshes. The system functions out-of-the-box using the bundled baseline dataset without credentials.

### Step 2: Build and Start Containers

```bash
docker compose up --build -d
```

### Step 3: Verify Service Health

```bash
docker compose ps
```

Expected output:
```
NAME             IMAGE                       STATUS                   PORTS
aditi-backend    aditi-platform-backend     Up (healthy)             0.0.0.0:8000->8000/tcp
aditi-frontend   aditi-platform-frontend    Up (healthy)             0.0.0.0:80->80/tcp
```

### Step 4: Access the Platform

- **Web Dashboard**: [http://localhost](http://localhost)
- **FastAPI Interactive Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check Endpoint**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 4. Persistent Storage & Volumes

Two directories on the host are mounted into the containers:

| Host Directory | Container Path | Purpose |
|---|---|---|
| `./data` | `/app/data` | Ingested TLE CSVs, SATCAT metadata, and SQLite `events.db` |
| `./models` | `/app/models` | Trained Isolation Forest `.joblib` model artifacts |

Because SQLite writes directly to `./data/events.db`, your event timeline and CAM simulation records survive container restarts and rebuilds.

---

## 5. Operations & Maintenance

### Viewing Live Logs

```bash
# View combined logs
docker compose logs -f

# View backend logs only
docker compose logs -f backend

# View frontend logs only
docker compose logs -f frontend
```

### Running Manual Orbital Data Refresh inside Container

```bash
docker compose exec backend python -m backend.refresh.cli --sources active_satellites_gp
```

### Automated Orbital Data Refresh Configuration

The backend container automatically initializes the Layer 12 periodic refresh scheduler on startup using FastAPI's lifespan events. Configure its behavior via environment variables in `.env` or `docker-compose.yml`:

| Variable | Default | Description |
|---|---|---|
| `SSA_REFRESH_ENABLED` | `true` | Enables or disables the in-process background refresh scheduler. |
| `SSA_REFRESH_INTERVAL_HOURS` | `6.0` | Refresh cycle interval in hours (default: every 6 hours). |
| `SSA_REFRESH_RUN_IMMEDIATELY` | `false` | If `true`, executes a refresh immediately on container startup. |

Per CelesTrak usage guidelines, an internal 2-hour minimum cooldown is enforced between remote downloads to prevent upstream rate limiting.

### Running Test Suite inside Container

```bash
docker compose exec backend python -m pytest -q --tb=short
```

### Stopping and Cleaning Up

```bash
# Stop containers without removing persistent data
docker compose down

# Stop and remove containers and local volumes
docker compose down -v
```

---

## 6. Troubleshooting

1. **Port 80 Conflict**:
   If another web server (Apache, IIS, or existing Nginx) is listening on port 80, modify `docker-compose.yml` to map to an alternate port, e.g. `"8080:80"`, and access at `http://localhost:8080`.

2. **Backend Slow to Report Healthy**:
   On initial startup, pandas loads the baseline orbital CSV into memory. The healthcheck includes a 10s grace period (`start_period: 10s`). Inspect logs with `docker compose logs backend` if healthcheck fails.


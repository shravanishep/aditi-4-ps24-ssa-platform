# Layer 4: FastAPI Service Layer

## Purpose
Layer 4 exposes the completed orbital analysis capabilities (Layers 1-3) through a clean RESTful HTTP API built with FastAPI. It does not contain orbital logic—it acts exclusively as an adapter between the HTTP layer and the existing Python functions.

## Endpoints

### `GET /health`
Returns a simple backend health status.

### `GET /satellites?limit=100`
Returns a limited list of satellites from the GP dataset. The `limit` parameter is constrained to `[1, 1000]` (default 100). Limits are applied at the API layer.

### `GET /satellites/{norad_id}`
Returns the full GP orbital information for a specific NORAD catalog ID.
- **404** if the NORAD ID is not found.

### `GET /satellites/{norad_id}/orbit?timestamp=...`
Propagates the satellite to the requested timestamp using Layer 1 SGP4 propagation. Returned positions are in km (TEME frame), velocities in km/s.
- **Timestamps must be timezone-aware** (e.g. `2026-09-20T10:00:00Z` or `2026-09-20T15:30:00+05:30`).
- Timezone-naive timestamps are rejected with HTTP 422.
- Timestamps are normalized to UTC before propagation.
- **404** if the NORAD ID is not found.

### `POST /conjunction/analyze`
Accepts two NORAD IDs, a time window, and a configurable threshold. Delegates to Layer 3 `find_closest_approach()` and returns a structured `CloseApproachResult`.

> **Important**: The result is an analytical prototype based on SGP4 propagation and public orbital data. It is **not** a collision probability or operational collision-avoidance output.

**Request body example:**
```json
{
  "norad1": 25544,
  "norad2": 20580,
  "start_time": "2026-09-20T10:00:00Z",
  "end_time": "2026-09-20T16:00:00Z",
  "threshold_km": 100.0,
  "coarse_step_sec": 60.0,
  "fine_step_sec": 1.0
}
```

## Error Codes
| Code | Meaning |
|------|---------|
| 400  | Logically invalid orbital operation (e.g. identical NORAD IDs, invalid time window) |
| 404  | NORAD ID not found in dataset |
| 422  | Request schema validation failure (e.g. timezone-naive timestamp, invalid limit) |

## Dependencies Added
- `fastapi`: HTTP framework
- `uvicorn`: ASGI server
- `httpx`: Test client transport

## Running the Server
```bash
uvicorn backend.main:app --reload
```

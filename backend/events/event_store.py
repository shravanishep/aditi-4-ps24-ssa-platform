"""
Event Intelligence — SQLite persistence layer.

Stores detected anomaly, conjunction, and threat events for the ADITI 4.0
SSA Platform persistent timeline feature.

Data source note: orbital data originates from CelesTrak GP CSV.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Database path — project_root/data/events.db
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent.parent  # backend/events/ → project root
DB_PATH = _PROJECT_ROOT / "data" / "events.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id                       TEXT PRIMARY KEY,
    norad_id                 INTEGER NOT NULL,
    object_name              TEXT,
    event_type               TEXT NOT NULL,
    classification           TEXT,
    classification_explanation TEXT,
    detected_at              TEXT NOT NULL,
    orbital_epoch            TEXT,
    anomaly_score            REAL,
    threat_score             REAL,
    tca                      TEXT,
    miss_distance_km         REAL,
    rel_speed_km_s           REAL,
    data_source              TEXT DEFAULT 'CelesTrak GP CSV',
    created_at               TEXT NOT NULL
)
"""

_INSERT_OR_IGNORE_SQL = """
INSERT OR IGNORE INTO events (
    id, norad_id, object_name, event_type, classification,
    classification_explanation, detected_at, orbital_epoch,
    anomaly_score, threat_score, tca, miss_distance_km,
    rel_speed_km_s, data_source, created_at
) VALUES (
    :id, :norad_id, :object_name, :event_type, :classification,
    :classification_explanation, :detected_at, :orbital_epoch,
    :anomaly_score, :threat_score, :tca, :miss_distance_km,
    :rel_speed_km_s, :data_source, :created_at
)
"""


def _make_event_id(norad_id: int, detected_at: str, event_type: str) -> str:
    """Deterministic 16-hex-char ID: sha256(norad_id|detected_at|event_type)[:16]."""
    raw = f"{norad_id}|{detected_at}|{event_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EventStore:
    """
    Thread-unsafe SQLite-backed store for orbital events.

    For production multi-threaded deployments, wrap in a connection pool or
    use a proper RDBMS.  This implementation is suitable for research prototypes.
    """

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                isolation_level=None,  # autocommit
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Create the events table if it does not already exist."""
        self._get_conn().execute(_CREATE_TABLE_SQL)

    def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert_event(self, event: dict) -> str:
        """
        Insert event into the DB; silently ignore duplicate IDs.

        The ``id`` field is derived from (norad_id, detected_at, event_type)
        so calling this method twice with the same logical event is idempotent.

        Returns the computed event id.
        """
        norad_id = int(event["norad_id"])
        detected_at = str(event["detected_at"])
        event_type = str(event["event_type"])

        event_id = _make_event_id(norad_id, detected_at, event_type)

        row = {
            "id": event_id,
            "norad_id": norad_id,
            "object_name": event.get("object_name"),
            "event_type": event_type,
            "classification": event.get("classification"),
            "classification_explanation": event.get("classification_explanation"),
            "detected_at": detected_at,
            "orbital_epoch": event.get("orbital_epoch"),
            "anomaly_score": event.get("anomaly_score"),
            "threat_score": event.get("threat_score"),
            "tca": event.get("tca"),
            "miss_distance_km": event.get("miss_distance_km"),
            "rel_speed_km_s": event.get("rel_speed_km_s"),
            "data_source": event.get("data_source", "CelesTrak GP CSV"),
            "created_at": event.get("created_at", _now_utc_iso()),
        }

        self._get_conn().execute(_INSERT_OR_IGNORE_SQL, row)
        return event_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_events(
        self,
        norad_id: Optional[int] = None,
        event_type: Optional[str] = None,
        classification: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Return events matching the given filters, ordered by detected_at DESC.

        Parameters
        ----------
        norad_id      : filter to a single NORAD ID (optional)
        event_type    : 'ANOMALY' | 'CONJUNCTION' | 'THREAT' (optional)
        classification: 'ORBIT_RAISE' | 'ORBIT_DECAY' | 'STATION_KEEPING' | 'UNKNOWN' (optional)
        since         : ISO-8601 lower bound on detected_at (inclusive, optional)
        until         : ISO-8601 upper bound on detected_at (inclusive, optional)
        limit         : maximum rows to return (default 100)
        """
        clauses: list[str] = []
        params: list[Any] = []

        if norad_id is not None:
            clauses.append("norad_id = ?")
            params.append(norad_id)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if classification is not None:
            clauses.append("classification = ?")
            params.append(classification)
        if since is not None:
            clauses.append("detected_at >= ?")
            params.append(since)
        if until is not None:
            clauses.append("detected_at <= ?")
            params.append(until)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM events {where} ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)

        rows = self._get_conn().execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_event_by_id(self, event_id: str) -> Optional[dict]:
        """Return a single event by its primary key, or None if not found."""
        row = self._get_conn().execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        return dict(row) if row else None

    def count_events(self) -> int:
        """Return total number of rows in the events table."""
        result = self._get_conn().execute("SELECT COUNT(*) FROM events").fetchone()
        return result[0] if result else 0

    def stats_by_type_and_classification(self) -> dict:
        """Return counts broken down by event_type and classification."""
        by_type_rows = self._get_conn().execute(
            "SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type"
        ).fetchall()
        by_class_rows = self._get_conn().execute(
            "SELECT classification, COUNT(*) as cnt FROM events GROUP BY classification"
        ).fetchall()
        return {
            "total": self.count_events(),
            "by_type": {r["event_type"]: r["cnt"] for r in by_type_rows},
            "by_classification": {
                (r["classification"] or "UNCLASSIFIED"): r["cnt"]
                for r in by_class_rows
            },
        }

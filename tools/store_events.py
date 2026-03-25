"""
Tool: store_events.py
Layer: 3 — Execution
SOP: architecture/storage_sop.md

Reads analyzed CompetitorEvent dicts and persists them to SQLite (data/events.db).
Skips events below MIN_SEVERITY threshold and events with duplicate source_url.

Input:  .tmp/analyzed_signals.json  (or list passed directly)
Output: data/events.db              (SQLite)
"""

import os
import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger(__name__)

TMP_DIR = ROOT / ".tmp"
INPUT_FILE = TMP_DIR / "analyzed_signals.json"
DB_PATH = ROOT / os.getenv("DB_PATH", "data/events.db")

MIN_SEVERITY = os.getenv("MIN_SEVERITY", "Medium")
SEVERITY_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set for dict-like access."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the events table and indexes if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id               TEXT PRIMARY KEY,
            timestamp        TEXT NOT NULL,
            competitor       TEXT NOT NULL,
            category         TEXT NOT NULL,
            severity         TEXT NOT NULL,
            headline         TEXT NOT NULL,
            summary          TEXT,
            source_url       TEXT UNIQUE NOT NULL,
            strategic_impact TEXT,
            tags             TEXT,
            archived         INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_timestamp  ON events(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_competitor ON events(competitor);
        CREATE INDEX IF NOT EXISTS idx_category   ON events(category);
        CREATE INDEX IF NOT EXISTS idx_severity   ON events(severity);
    """)
    conn.commit()


def _meets_threshold(severity: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(MIN_SEVERITY, 2)


def store_events(events: list[dict] | None = None) -> int:
    """
    Persist CompetitorEvent dicts to SQLite.
    Returns count of newly inserted records.
    """
    if events is None:
        if not INPUT_FILE.exists():
            logger.error(f"store_events.py: {INPUT_FILE} not found")
            return 0
        events = json.loads(INPUT_FILE.read_text(encoding='utf-8'))

    conn = get_connection()
    init_db(conn)

    inserted = 0
    skipped_severity = 0
    skipped_duplicate = 0

    for event in events:
        severity = event.get("severity", "Low")

        if not _meets_threshold(severity):
            skipped_severity += 1
            continue

        try:
            conn.execute(
                """
                INSERT INTO events
                    (id, timestamp, competitor, category, severity, headline,
                     summary, source_url, strategic_impact, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["id"],
                    event["timestamp"],
                    event["competitor"],
                    event["category"],
                    event["severity"],
                    event["headline"],
                    event.get("summary", ""),
                    event["source_url"],
                    event.get("strategic_impact", ""),
                    event.get("tags", "[]"),
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            # UNIQUE constraint on source_url — already stored
            skipped_duplicate += 1
        except Exception as e:
            logger.error(f"  store_events: failed to insert '{event.get('headline', '')}': {e}")

    conn.commit()
    conn.close()

    logger.info(
        f"store_events.py: {inserted} inserted, "
        f"{skipped_duplicate} duplicate, "
        f"{skipped_severity} below threshold"
    )
    return inserted


def query_events(
    competitor: str | None = None,
    category: str | None = None,
    severity: list[str] | None = None,
    limit: int = 50,
    since_hours: int | None = None,
) -> list[dict]:
    """
    Query stored events. Used by api_server.py.
    Returns a list of dicts ordered by timestamp DESC.
    """
    conn = get_connection()
    init_db(conn)

    clauses = ["archived = 0"]
    params: list = []

    if competitor:
        clauses.append("competitor = ?")
        params.append(competitor)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if severity:
        placeholders = ",".join("?" * len(severity))
        clauses.append(f"severity IN ({placeholders})")
        params.extend(severity)
    if since_hours:
        clauses.append("timestamp >= datetime('now', ?)")
        params.append(f"-{since_hours} hours")

    where = " AND ".join(clauses)
    params.append(limit)

    rows = conn.execute(
        f"SELECT * FROM events WHERE {where} ORDER BY timestamp DESC LIMIT ?",
        params,
    ).fetchall()

    conn.close()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Smoke test: insert a mock event
    mock = [{
        "id": "test-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "competitor": "Scaleway",
        "category": "Product Launch",
        "severity": "High",
        "headline": "Scaleway launches H100 cluster in Paris-2",
        "summary": "Scaleway announced GA of H100 GPU instances.",
        "source_url": "https://example.com/scaleway-h100-test",
        "strategic_impact": "Direct GPU competition in EU-West. Aleph must respond with pricing clarity.",
        "tags": '["GPU", "EU", "H100"]',
    }]
    count = store_events(mock)
    print(f"Inserted {count} test event(s) into {DB_PATH}")

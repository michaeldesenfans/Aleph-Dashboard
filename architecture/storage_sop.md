# SOP: Storage Layer

## Goal
Define how `CompetitorEvent` records are persisted, queried, and maintained in the local SQLite database.

## Technology Choice
**SQLite** — chosen for in-office, single-machine deployment. No server process, no credentials, zero ops overhead. File lives at `data/events.db` (gitignored).

## Schema: `events` Table

```sql
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,       -- UUID v4
    timestamp       TEXT NOT NULL,          -- ISO8601, UTC
    competitor      TEXT NOT NULL,          -- enum: see gemini.md
    category        TEXT NOT NULL,          -- enum: Outage|Funding|Product Launch|News|Policy
    severity        TEXT NOT NULL,          -- enum: Critical|High|Medium|Low
    headline        TEXT NOT NULL,
    summary         TEXT,                   -- LLM-generated
    source_url      TEXT UNIQUE NOT NULL,   -- dedup key
    strategic_impact TEXT,                 -- LLM-generated Aleph-specific analysis
    tags            TEXT                    -- JSON array stored as string
);
```

## Indexes
```sql
CREATE INDEX IF NOT EXISTS idx_timestamp  ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_competitor ON events(competitor);
CREATE INDEX IF NOT EXISTS idx_category   ON events(category);
CREATE INDEX IF NOT EXISTS idx_severity   ON events(severity);
```

## Retention Policy
- Events older than **90 days** are soft-deleted (flagged `archived=1`, not removed)
- Hard delete after **180 days** — run via a weekly maintenance cron

## Query Patterns (used by api_server.py)
- **Live feed:** `SELECT * FROM events ORDER BY timestamp DESC LIMIT 50`
- **Filtered:** `WHERE competitor = ? AND category = ? AND severity IN (?,?)`
- **Daily digest:** `WHERE timestamp >= date('now', '-1 day')`

## Migration Rule
Any schema change requires:
1. Update this SOP
2. Write a migration script in `tools/migrations/`
3. Test against a copy of `data/events.db` before applying to production

"""SQLite schema definition for the normalized V2 backend."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS competitors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    provider_type   TEXT NOT NULL DEFAULT 'cloud',
    display_order   INTEGER NOT NULL DEFAULT 100,
    is_pinned       INTEGER NOT NULL DEFAULT 1,
    track_outages   INTEGER NOT NULL DEFAULT 1,
    track_news      INTEGER NOT NULL DEFAULT 1,
    track_strategy  INTEGER NOT NULL DEFAULT 1,
    active          INTEGER NOT NULL DEFAULT 1,
    metadata_json   TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS source_endpoints (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id         INTEGER NOT NULL REFERENCES competitors(id),
    source_kind           TEXT NOT NULL,
    purpose               TEXT NOT NULL,
    endpoint_url          TEXT NOT NULL,
    adapter_type          TEXT NOT NULL,
    trust_tier            INTEGER NOT NULL DEFAULT 1,
    poll_interval_seconds INTEGER NOT NULL DEFAULT 300,
    enabled               INTEGER NOT NULL DEFAULT 1,
    is_primary            INTEGER NOT NULL DEFAULT 0,
    parser_config_json    TEXT DEFAULT '{}',
    last_checked_at       TEXT,
    last_success_at       TEXT,
    last_error_at         TEXT,
    last_error_msg        TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_se_competitor ON source_endpoints(competitor_id);
CREATE INDEX IF NOT EXISTS idx_se_purpose ON source_endpoints(purpose);
CREATE UNIQUE INDEX IF NOT EXISTS idx_se_unique
    ON source_endpoints(competitor_id, source_kind, purpose, endpoint_url);

CREATE TABLE IF NOT EXISTS discovery_queries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id     INTEGER REFERENCES competitors(id),
    provider          TEXT NOT NULL DEFAULT 'brave',
    query_family      TEXT NOT NULL,
    endpoint_type     TEXT NOT NULL DEFAULT 'news',
    query_template    TEXT NOT NULL,
    freshness_window  TEXT DEFAULT 'pw',
    count             INTEGER NOT NULL DEFAULT 5,
    cadence_minutes   INTEGER NOT NULL DEFAULT 60,
    cooldown_minutes  INTEGER NOT NULL DEFAULT 30,
    priority          INTEGER NOT NULL DEFAULT 2,
    trigger_only      INTEGER NOT NULL DEFAULT 0,
    enabled           INTEGER NOT NULL DEFAULT 1,
    max_monthly_calls INTEGER DEFAULT 200,
    calls_this_month  INTEGER NOT NULL DEFAULT 0,
    month_reset       TEXT,
    last_run_at       TEXT,
    last_result_count INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dq_competitor ON discovery_queries(competitor_id);
CREATE INDEX IF NOT EXISTS idx_dq_family ON discovery_queries(query_family);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dq_unique
    ON discovery_queries(COALESCE(competitor_id, -1), provider, query_family, endpoint_type, query_template);

CREATE TABLE IF NOT EXISTS discovery_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type      TEXT NOT NULL,
    trigger_type  TEXT NOT NULL DEFAULT 'scheduled',
    status        TEXT NOT NULL DEFAULT 'running',
    started_at    TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at   TEXT,
    stats_json    TEXT DEFAULT '{}',
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_endpoint_id  INTEGER REFERENCES source_endpoints(id),
    discovery_query_id  INTEGER REFERENCES discovery_queries(id),
    external_id         TEXT,
    url                 TEXT NOT NULL,
    canonical_url       TEXT,
    title_raw           TEXT,
    snippet_raw         TEXT,
    content_raw         TEXT,
    content_clean       TEXT,
    published_at        TEXT,
    fetched_at          TEXT NOT NULL DEFAULT (datetime('now')),
    content_hash        TEXT,
    language            TEXT DEFAULT 'en',
    author              TEXT,
    source_name         TEXT,
    metadata_json       TEXT DEFAULT '{}',
    processing_status   TEXT NOT NULL DEFAULT 'pending',
    rejection_reason    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_url ON documents(url);
CREATE INDEX IF NOT EXISTS idx_doc_status ON documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_doc_fetched ON documents(fetched_at DESC);

CREATE TABLE IF NOT EXISTS events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key           TEXT UNIQUE,
    event_type          TEXT NOT NULL,
    competitor_id       INTEGER REFERENCES competitors(id),
    title               TEXT NOT NULL,
    summary             TEXT,
    strategic_impact    TEXT,
    severity_score      INTEGER NOT NULL DEFAULT 3,
    severity_label      TEXT NOT NULL DEFAULT 'Medium',
    confidence          REAL DEFAULT 0.5,
    lifecycle_status    TEXT NOT NULL DEFAULT 'active',
    started_at          TEXT,
    detected_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at         TEXT,
    primary_region      TEXT,
    metadata_json       TEXT DEFAULT '{}',
    tags_json           TEXT DEFAULT '[]',
    extraction_version  TEXT DEFAULT 'v2.0',
    synthesis_version   TEXT DEFAULT 'v2.0'
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_competitor ON events(competitor_id);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity_label);
CREATE INDEX IF NOT EXISTS idx_events_detected ON events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_lifecycle ON events(lifecycle_status);

CREATE TABLE IF NOT EXISTS event_evidence (
    event_id              INTEGER NOT NULL REFERENCES events(id),
    document_id           INTEGER NOT NULL REFERENCES documents(id),
    evidence_role         TEXT NOT NULL DEFAULT 'source',
    extraction_confidence REAL DEFAULT 0.5,
    PRIMARY KEY (event_id, document_id)
);

CREATE TABLE IF NOT EXISTS incidents (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id        INTEGER NOT NULL REFERENCES competitors(id),
    event_id             INTEGER REFERENCES events(id),
    external_incident_id TEXT,
    title                TEXT NOT NULL,
    summary              TEXT,
    status               TEXT NOT NULL DEFAULT 'active',
    severity             TEXT DEFAULT 'minor',
    region_label         TEXT,
    affected_services    TEXT DEFAULT '[]',
    incident_url         TEXT,
    first_seen_at        TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at         TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at          TEXT,
    source_endpoint_id   INTEGER REFERENCES source_endpoints(id),
    metadata_json        TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_incidents_competitor ON incidents(competitor_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_incidents_external
    ON incidents(competitor_id, external_incident_id);

CREATE TABLE IF NOT EXISTS provider_status_current (
    competitor_id           INTEGER PRIMARY KEY REFERENCES competitors(id),
    overall_state           TEXT NOT NULL DEFAULT 'unknown',
    region_label            TEXT,
    active_incident_count   INTEGER NOT NULL DEFAULT 0,
    latest_incident_title   TEXT,
    latest_incident_url     TEXT,
    source_coverage         TEXT DEFAULT 'none',
    freshness_seconds       INTEGER DEFAULT 0,
    last_checked_at         TEXT,
    last_changed_at         TEXT,
    display_rank            INTEGER NOT NULL DEFAULT 100,
    payload_json            TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS provider_status_history (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id         INTEGER NOT NULL REFERENCES competitors(id),
    overall_state         TEXT NOT NULL,
    region_label          TEXT,
    active_incident_count INTEGER NOT NULL DEFAULT 0,
    observed_at           TEXT NOT NULL DEFAULT (datetime('now')),
    source_endpoint_id    INTEGER REFERENCES source_endpoints(id),
    payload_json          TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_psh_competitor ON provider_status_history(competitor_id);
CREATE INDEX IF NOT EXISTS idx_psh_observed ON provider_status_history(observed_at DESC);

CREATE TABLE IF NOT EXISTS trend_snapshots (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    title              TEXT NOT NULL,
    narrative          TEXT NOT NULL,
    confidence         REAL DEFAULT 0.5,
    impact_level       TEXT DEFAULT 'medium',
    window_start       TEXT,
    window_end         TEXT,
    generated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    evidence_event_ids TEXT DEFAULT '[]',
    model_version      TEXT DEFAULT 'gpt-4o'
);

CREATE TABLE IF NOT EXISTS strategic_signals (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type          TEXT NOT NULL,
    title                TEXT NOT NULL,
    analysis             TEXT NOT NULL,
    confidence           REAL DEFAULT 0.5,
    detected_at          TEXT NOT NULL DEFAULT (datetime('now')),
    competitor_id        INTEGER REFERENCES competitors(id),
    supporting_event_ids TEXT DEFAULT '[]',
    model_version        TEXT DEFAULT 'gpt-4o'
);
CREATE INDEX IF NOT EXISTS idx_ss_type ON strategic_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_ss_detected ON strategic_signals(detected_at DESC);
"""

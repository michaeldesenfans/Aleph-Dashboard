# Progress Log — Aleph Dashboard V2

> Current version: **V2.2** | Last updated: **2026-03-24**

---

## V2.2 — 2026-03-24

### What Changed

**Frontend — fully live, zero demo data**
- Removed ~385 lines of hardcoded demo content (momentum cards, signal cards, watchlist rows, macro trend text)
- All 5 right-panel sections now populated exclusively by `/api/v2/*` live data
- Inline carousel `<script>` removed — carousel logic lives entirely in `v2_enhanced.js`
- Macro Trend card now shows "AI Generated: Xh ago" timestamp tag

**Outage bar (left rail)**
- Horizontal scrollbar visible (cyan-tinted thin scrollbar, cross-browser)
- All 17 providers rendered with colored dot indicators
- Incident rows with URLs rendered as `<a>` tags — full row is clickable, opens source status page in new tab

**Strategic Signals**
- SVG icons per signal type (threat/opportunity/regulatory/market_shift)
- Source links rendered below each signal analysis (`signal-sources` CSS class)
- Fallback source resolution added: when GPT-generated `supporting_event_ids` don't match real DB rows (GPT returns prompt-position indices, not real IDs), `_fallback_signal_sources()` queries the most recent high-severity events for that competitor
- `safeHostname()` helper prevents `new URL()` throw on empty/invalid URLs

**Momentum Themes**
- Each theme card now includes source links from real events matching that event type
- `_enrich_theme_sources()` queries up to 3 source URLs per theme type within the selected window
- Sources were blocked by stale `__pycache__` on first restart — cleared on clean restart

**Bug fixes**
- `__pycache__` stale bytecode caused source enrichment to silently return empty arrays through the API even though direct Python calls returned correct data — fixed by clearing caches before restart
- `new URL(s.url).hostname` threw TypeError when `s.name` was empty string — wrapped in `safeHostname(url)` helper
- `python server/api_server.py` failed with `ModuleNotFoundError` — always use `python -m server.api_server`

### API State (verified 2026-03-24)
- 17 providers polled, 5 active outages (Scaleway, Akamai/Linode, Hetzner, IBM Cloud, AWS)
- 76+ events in DB, all with `source_url` in `metadata_json`
- GPT-4o trend: confidence 0.85, generated 2026-03-24 20:29
- 5 strategic signals with 1–3 source links each
- 6 momentum themes with 1–3 source links each

---

## V2.1 — 2026-03-23 to 2026-03-24

### What Was Built (Codex + Claude session)

**Backend — full rebuild from V1**

| Component | Notes |
|-----------|-------|
| `server/models/schema.py` | 12-table normalized SQLite schema |
| `server/seeds/competitors.py` | 17 competitors, source endpoints, discovery queries |
| `server/repositories/db.py` | `init_db()` idempotent, dedupes before unique indexes |
| `server/repositories/events.py` | Event CRUD + aggregations (`get_momentum`, `get_headlines`, etc.) |
| `server/repositories/status.py` | Provider status current + history |
| `server/repositories/synthesis.py` | Trend snapshot + strategic signal storage |
| `server/adapters/status_adapters.py` | 5 parser types: Atlassian, GCP, RSS, AWS Health, StatusJSON |
| `server/adapters/brave_adapter.py` | Brave Search news + web queries |
| `server/adapters/feed_adapter.py` | RSS/Atom feed ingestion |
| `server/services/extraction.py` | GPT-4o document → structured event extraction |
| `server/services/synthesis.py` | GPT-4o trend + signal synthesis + heuristic fallback |
| `server/services/budget.py` | Brave monthly budget manager with cooldowns |
| `server/pipelines/status_pipeline.py` | Fast 12-min status polling |
| `server/pipelines/discovery_pipeline.py` | RSS + Brave + extraction pipeline |
| `server/pipelines/orchestrator.py` | Full pipeline orchestration |
| `server/read_models/v2.py` | Widget-shaped response builders (all 7 widgets) |
| `server/api/v2.py` | Flask Blueprint `/api/v2/*` |
| `server/api_server.py` | Main entry point + APScheduler |

**Frontend — V2.1**
- `dashboard/v2_enhanced.html` — Palantir Gotham + Web3 theme, two-pane layout
- `dashboard/v2_enhanced.js` — Full API wiring for all 7 widgets

**Fixes applied in this session**
- `sqlite3.IntegrityError: UNIQUE constraint failed` on `init_db()` — split schema execution: tables first, dedupe, then unique indexes
- GPT-4o returned `"confidence": "High"` string — added conf_map normalization in `synthesis.py`
- `.env` model was `gpt-5.2` (typo) → corrected to `gpt-4o`

---

## V1 — Pre-2026-03-23 (Archived)

Original V1 toolchain (`tools/`, `architecture/`) used a flat pipeline: NewsAPI + RSS → deduplicate → GPT-4o scoring → SQLite. Served a single-page HTML dashboard.

V2 replaced this entirely with a normalized schema, multi-source discovery (status pages + RSS + Brave Search), and a widget-shaped read model layer. V1 files remain in `tools/` and `architecture/` for reference but are not part of the active system.

---

## Known Gaps / Next Work

| Issue | Priority |
|-------|----------|
| GPT signal `supporting_event_ids` are prompt-position indices, not real DB IDs — synthesis prompt should be updated to skip the ID field entirely | Medium |
| `unknown` status providers (CoreWeave, Alibaba, IONOS etc.) — status adapters not yet returning data for these | Medium |
| Synthesis confidence label normalization only covers heuristic fallback — should also normalize on save | Low |
| No authentication on `/api/run` POST endpoint | Low |

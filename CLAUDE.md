# CLAUDE.md — Aleph Dashboard V2

> **Read this file at the start of every conversation to understand the project state.**

## What This Is

Aleph is a **CEO-facing competitive intelligence dashboard** for Aleph Cloud. It monitors 17 cloud service providers via live status pages, RSS feeds, and Brave Search, then uses GPT-4o to extract and synthesize strategic intelligence.

**Target user:** Jonathan Schemoul, CEO of Aleph Cloud.
**Purpose:** Real-time competitive awareness — outages, product launches, capital moves, regulatory shifts — synthesized into actionable strategic recommendations.

## Current State (Updated 2026-03-24) — V2.2

### Architecture: Evidence → Intelligence → Widget

```
Status Pages (RSS/JSON) ──→ Incidents ──→ Provider Status Current/History
RSS/Atom Feeds ──→ Documents ──→ GPT-4o Extraction ──→ Events ──→ Widget Read Models
Brave Search   ──→ Documents ──→ GPT-4o Extraction ──→ Events ──→ Widget Read Models
                                                                   ↕
Events ──→ GPT-4o Synthesis ──→ Trend Snapshots + Strategic Signals
```

### What's Built & Working

| Component | Status | Location |
|-----------|--------|----------|
| Normalized SQLite schema (12 tables) | Working | `server/models/schema.py` |
| 17 pinned competitors + seed registry | Working | `server/seeds/competitors.py` |
| DB init with idempotent sync | Working | `server/repositories/db.py` |
| Repository layer (7 repos) | Working | `server/repositories/` |
| Status pipeline (fast, authoritative) | Working | `server/pipelines/status_pipeline.py` |
| Discovery pipeline (RSS + Brave) | Working | `server/pipelines/discovery_pipeline.py` |
| Status adapters (5 types) | Working | `server/adapters/status_adapters.py` |
| Brave Search adapter | Working | `server/adapters/brave_adapter.py` |
| RSS/Atom feed adapter | Working | `server/adapters/feed_adapter.py` |
| GPT-4o extraction service | Working | `server/services/extraction.py` |
| Synthesis service (trend + signals) | Working | `server/services/synthesis.py` |
| Brave budget manager | Working | `server/services/budget.py` |
| Widget read models (with source enrichment) | Working | `server/read_models/v2.py` |
| Flask API (`/api/v2/*`) | Working | `server/api/v2.py` |
| Main server + scheduler | Working | `server/api_server.py` |
| **V2.2 Frontend — fully live, no demo data** | **Working** | `dashboard/v2_enhanced.html` + `v2_enhanced.js` |

### Frontend: V2.2 Enhanced

**Live at** `http://localhost:8080` when server is running. Wired to `/api/v2/*` endpoints. **All sections are populated entirely by live API data — no hardcoded demo content anywhere.**

**Theme:** Palantir Gotham + Web3 flair
- Canvas: `#060709` (true OLED black), surfaces: `#0b0e14` / `#111827`
- Borders: cyan-tinted (`rgba(0,212,255,*)`)
- Brand gradient: cyan → violet → magenta (`#00d4ff → #8b5cf6 → #d946ef`)
- Glow system: neon text-shadow and box-shadow on indicators/badges
- Typography: `Share Tech Mono` (HUD), `Fira Code` (data), `Inter` (body)
- Border radius: sharp (2–6px)

**Layout — Two Pane:**
- Left (46%): Server Outages Rail (horizontal scroll, clickable rows → source) → Headlines Carousel → Tactical Feed
- Right (54%): Macro Trend (AI-generated, with timestamp) → Momentum Synthesis (thematic cards + source links) → Strategic Signals (SVG icons + sources + confidence) → Watchlist

**Key V2.2 JS functions (`v2_enhanced.js`):**
- `renderStatus()` — outage rows as `<a>` tags when URL exists
- `renderTrend()` — macro card with AI Generated timestamp
- `renderMomentum()` — themes with `renderSources()` source links
- `renderSignals()` — cards with SVG icons per type + source links
- `safeHostname(url)` — safe `new URL()` wrapper (no throw on bad URLs)
- `_fallback_signal_sources()` (backend) — resolves sources for signals whose GPT-generated event IDs don't match DB IDs

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Start everything (dashboard + API + schedulers)
python -m server.api_server    # http://localhost:8080
```

> **Important:** Always use `python -m server.api_server` (module syntax), NOT `python server/api_server.py`. The module syntax ensures the project root is on `sys.path`.

> **If you see stale API responses after editing backend files:** Delete `__pycache__` directories in `server/` before restarting. Flask doesn't auto-reload in production mode.

The server initializes the DB, seeds competitors, registers all routes, and starts three background schedulers:
- **Status pipeline** every 12 minutes (authoritative status page polling)
- **Discovery pipeline** every 45 minutes (RSS + Brave queries + extraction)
- **Synthesis pipeline** every 60 minutes (trend + signals generation)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI (v2_enhanced.html) |
| `/api/v2/stats` | GET | KPI counters (events/critical/high/24h) |
| `/api/v2/csp-status` | GET | All 17 provider statuses with incident details |
| `/api/v2/headlines` | GET | Top 3 Critical/High headlines |
| `/api/v2/events` | GET | Filtered events (`?competitor=&event_type=&severity=&limit=&hours=`) |
| `/api/v2/momentum` | GET | Thematic momentum cards + watchlist (`?window=30d`) |
| `/api/v2/synthesis/trend` | GET | Macro trend synthesis with `generated_at` timestamp |
| `/api/v2/synthesis/signals` | GET | Strategic signal cards with `sources` array |
| `/api/v2/health` | GET | Pipeline health + Brave budget |
| `/api/run` | POST | Trigger full pipeline manually |

## Competitors Tracked (17)

**Tier 1:** AWS, Azure, GCP, Oracle Cloud, CoreWeave
**Tier 2:** Alibaba Cloud, OVHcloud, Scaleway, IONOS Cloud, DigitalOcean, Hetzner
**Tier 3:** Open Telekom Cloud, Akamai/Linode, Vultr, IBM Cloud, Crusoe, Lambda Labs

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `BRAVE_SEARCH_API_KEY` | Yes | — |
| `OPENAI_API_KEY` | Yes | — |
| `OPENAI_MODEL` | No | `gpt-4o` |
| `SERVER_PORT` | No | `8080` |
| `STATUS_POLL_SECONDS` | No | `720` |
| `DISCOVERY_INTERVAL_MINUTES` | No | `45` |
| `BRAVE_MAX_MONTHLY_CALLS` | No | `2000` |

## File Structure

```
├── CLAUDE.md                      # THIS FILE — read first every session
├── progress.md                    # Changelog and current build state
├── .env                           # API keys (BRAVE_SEARCH_API_KEY, OPENAI_API_KEY)
├── .env.example                   # Template
├── requirements.txt               # Python dependencies
├── Context/                       # Reference material (strategy deck)
├── server/
│   ├── api_server.py              # Main Flask app + scheduler entry point
│   ├── config.py                  # Central config from environment
│   ├── api/
│   │   └── v2.py                  # /api/v2/* Blueprint
│   ├── models/
│   │   └── schema.py              # SQLite schema (12 tables)
│   ├── seeds/
│   │   └── competitors.py         # 17 competitors + endpoints + discovery queries
│   ├── repositories/
│   │   ├── db.py                  # Connection manager + init_db
│   │   ├── competitors.py         # Competitor/endpoint queries
│   │   ├── documents.py           # Document CRUD
│   │   ├── events.py              # Event/incident CRUD + aggregations
│   │   ├── status.py              # Provider status current/history
│   │   ├── discovery.py           # Discovery query scheduling + budget
│   │   └── synthesis.py           # Trend/signal storage
│   ├── adapters/
│   │   ├── status_adapters.py     # 5 status page parsers (Atlassian, GCP, RSS, AWS, StatusJSON)
│   │   ├── brave_adapter.py       # Brave Search news/web
│   │   └── feed_adapter.py        # RSS/Atom feed parser
│   ├── services/
│   │   ├── extraction.py          # GPT-4o document → event extraction
│   │   ├── synthesis.py           # GPT-4o trend + signal generation + heuristic fallback
│   │   └── budget.py              # Brave API budget manager
│   ├── pipelines/
│   │   ├── status_pipeline.py     # Fast status polling (all providers)
│   │   ├── discovery_pipeline.py  # RSS + Brave + extraction
│   │   └── orchestrator.py        # Full pipeline orchestration
│   └── read_models/
│       └── v2.py                  # Widget-shaped API response builders + source enrichment
├── dashboard/
│   ├── v2_enhanced.html           # Active frontend — V2.2 (Gotham theme, fully live)
│   └── v2_enhanced.js             # Frontend JS (API wiring, all render functions)
└── data/
    └── aleph_v2.db                # SQLite database (auto-created at startup)
```

## Rules for Editing

1. **Read this file first** every conversation.
2. **`v2_enhanced.html` + `v2_enhanced.js` are the active frontend.** Do not edit other HTML/JS files.
3. **Theme: Palantir Gotham + Web3** — maintain dark OLED canvas, cyan borders, neon glows, Share Tech Mono HUD typography, sharp angular radii.
4. **No business logic in LLM prompts** — all logic in Python.
5. **Idempotent DB init** — `init_db()` must be safe to run repeatedly.
6. **Budget-aware discovery** — Brave queries respect monthly limits and cooldowns.
7. **Evidence → Intelligence → Widget** — documents are evidence, events are intelligence, read models shape widgets.
8. **Always start with `python -m server.api_server`** — never the direct file path.
9. **After editing backend Python files, clear `__pycache__`** before restarting to avoid stale bytecode serving.
10. **Source enrichment pattern** — `_enrich_theme_sources()` for momentum themes; `_fallback_signal_sources()` for signals where GPT event IDs don't resolve to real DB rows.

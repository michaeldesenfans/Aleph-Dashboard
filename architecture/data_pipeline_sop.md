# SOP: Data Pipeline & AI Integration

## 🎯 Goal
Build a deterministic, automated pipeline that ingests raw market signals, filters them using AI, and serves them to the Strategic Dashboard.

## 📡 The Discovery Layer: Detailed Spec

This layer is responsible for "scanning" the market for signals. It uses three primary discovery vectors:

### 1. Competitive Health (Real-Time Status)
- **AWS:** Polling the [AWS Health Dashboard](https://health.aws.amazon.com/health/status) via JSON/RSS. (Note: API requires Business support).
- **Hetzner:** RSS polling from `https://status.hetzner.com/rss`.
- **OVHcloud:** REST API polling from `https://status-ovhcloud.com/api/v2/summary.json`.
- **Scaleway:** Monitoring `https://status.scaleway.com/` for active incidents.
- **DigitalOcean:** StatusPage.io API integration: `https://status.digitalocean.com/api/v2/summary.json`.

## 📡 The Discovery Layer: Dynamic Search Vectors

Instead of anchoring to static RSS feeds, the system performs **Active Search Sweeps** using a Search API (e.g., Serper.dev, Google Search API, or Tavily). This ensures discovery of "black swan" events from any source.

### 🔍 Search Vector Specification (Daily Refreshes)
The orchestrator (`tools/discover_signals.py`) executes these specific thematic sweeps:

| Vector | Search Query Pattern | Focus |
| --- | --- | --- |
| **Reliability** | `"{Competitor}" cloud (outage OR "service disruption" OR "SLA breach")` | Incident detection across secondary news/social. |
| **Velocity** | `"{Competitor}" (launch OR "now available" OR "GA") AND ("H100" OR "Confidential AI")` | High-spec hardware and product positioning. |
| **Capital** | `"{Competitor}" (funding OR "Series" OR acquisition OR investment)` | Financial momentum and M&A. |
| **Sovereignty** | `("Sovereign Cloud" OR "NIS2" OR "AI Act") AND ("EU" OR "Residency")` | Regulatory landscape shifts impacting Aleph. |

### 🧠 The AI Sieve (Filtering Logic)
Raw search results are passed through a mandatory LLM filter before DB ingestion:
1.  **Relevance Check:** Is the content specifically about the Aleph competitive landscape?
2.  **Strategic Scoring:** Rate impact 1-10. Discard anything < 5 (Signal-vs-Noise).
3.  **Deduplication:** Fuzzy-match headlines against the last 7 days of DB entries.

## ⚙️ 3-Layer Implementation

### Layer 1: Architecture (The "How")
- **Database:** SQLite (`data/competitive_intel.db`). Simple, file-based, and easy for local AIs (Claude/Codex) to read/write.
- **AI Integration:** 
    - **API:** OpenAI (GPT-4o) or Gemini Pro.
    - **Role 1 (Impact):** For every new signal, judge severity (1-10) and strategic impact on Aleph.
    - **Role 2 (Synthesis):** Once daily, analyze the last 30 days of "High" impact events to generate the "Monthly Thesis."
- **Ingestion Frequency:** Hourly for news/outages; Daily for synthesis.

### Layer 2: Navigation (The Backend)
- **API Server:** FastAPI. It will expose three endpoints:
    - `GET /api/outages`: Returns latest competitor health states.
    - `GET /api/signals`: Returns filterable news feed.
    - `GET /api/thesis`: Returns the latest AI-generated synthesis.

### Layer 3: Tools (The Engines)
1.  **`tools/ingest_news.py`**:
    - Uses `feedparser` for RSS feeds.
    - Targets: TechCrunch (Enterprise), Google News ("Sovereign Cloud"), etc.
2.  **`tools/check_status.py`**:
    - Calls Atlassian Statuspage APIs for competitors.
3.  **`tools/analyze_impact.py`**:
    - The LLM bridge. Filters out "noise" and writes "Signal" to DB.
4.  **`tools/db_manager.py`**:
    - Handles CRUD operations for the `CompetitorEvent` schema.

## 📊 Database Schema (SQLite)

### Table: `events`
| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Unique event ID |
| `timestamp` | DATETIME | ISO8601 |
| `competitor` | TEXT | AWS, Azure, etc. |
| `category` | TEXT | Outage, Funding, etc. |
| `severity` | TEXT | Critical, High, Medium |
| `headline` | TEXT | Raw headline |
| `summary` | TEXT | AI summary |
| `strategic_impact`| TEXT | AI "So What?" for Aleph |
| `source_url` | TEXT | URL |
| `is_archived` | BOOLEAN | For cleanup |

## 🤖 AI Prompt Blueprints

### Prompt: Signal Impact (analyze_impact.py)
> "Analyze this headline: {headline}. You are a strategic advisor for Aleph Cloud (EU-native, decentralized). Categorize it into [Funding/Launch/Policy] and score its impact on Aleph from 1-10. Provide a 1-sentence 'So What' for the executive team."

### Prompt: Monthly Thesis (generate_thesis.py)
> "Review the following {N} events from the last 30 days. Identify the top 3 dominant market trends. Synthesize a 3-sentence 'Strategic Thesis' and list 3 actionable insights for the Aleph leadership team."

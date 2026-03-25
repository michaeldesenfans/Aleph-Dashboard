# Aleph Dashboard V2

Backend is now organized as:

- `server/seeds`: canonical competitor/source/query registries
- `server/repositories`: normalized persistence layer
- `server/pipelines/status_pipeline.py`: authoritative provider health polling
- `server/pipelines/discovery_pipeline.py`: feed + Brave discovery
- `server/services/extraction.py`: OpenAI post-retrieval extraction
- `server/services/synthesis.py`: macro trend and strategic signal generation
- `server/read_models/v2.py`: widget-shaped payload builders
- `server/api/v2.py`: `/api/v2/*` routes

## Environment

Required for full capability:

- `OPENAI_API_KEY`
- `BRAVE_SEARCH_API_KEY`

Optional:

- `OPENAI_MODEL` default `gpt-4o`
- `DB_PATH` default `data/aleph_v2.db`
- `SERVER_PORT` default `8080`
- `STATUS_POLL_SECONDS` default `720`
- `DISCOVERY_INTERVAL_MINUTES` default `45`
- `SYNTHESIS_INTERVAL_MINUTES` default `60`

## Run

Install:

```bash
pip install -r requirements.txt
```

Initialize and run the server:

```bash
python server/api_server.py
```

Manual full refresh:

```bash
python tools/run_pipeline.py
```

## API

Primary frontend endpoints:

- `GET /api/v2/stats`
- `GET /api/v2/csp-status`
- `GET /api/v2/headlines`
- `GET /api/v2/events`
- `GET /api/v2/momentum?window=30d`
- `GET /api/v2/synthesis/trend`
- `GET /api/v2/synthesis/signals`
- `GET /api/v2/health`

Compatibility endpoints kept:

- `GET /api/events`
- `POST /api/run`
- `GET /api/status`

"""Central configuration loaded from environment."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# --- Paths ---
_db_path_raw = os.getenv("DB_PATH", "").strip()
_legacy_db_path_raw = os.getenv("LEGACY_DB_PATH", "data/events.db").strip()
if not _db_path_raw or _db_path_raw == "data/events.db":
    DB_PATH = ROOT / "data/aleph_v2.db"
    LEGACY_DB_PATH = ROOT / "data/events.db"
else:
    DB_PATH = ROOT / _db_path_raw
    LEGACY_DB_PATH = ROOT / _legacy_db_path_raw
TMP_DIR = ROOT / ".tmp"
DASHBOARD_DIR = ROOT / "dashboard"

# --- Server ---
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = _env_int("SERVER_PORT", 8080)

# --- CORS ---
# Comma-separated list of allowed origins, e.g. "https://marketwatch.aleph.im,https://admin.aleph.im"
# Set to "*" to allow all origins (not recommended for production).
# If unset, CORS is disabled (same-origin only).
_cors_raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
CORS_ALLOWED_ORIGINS: list[str] | None = (
    None if not _cors_raw
    else ["*"] if _cors_raw == "*"
    else [origin.strip() for origin in _cors_raw.split(",") if origin.strip()]
)

# --- API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

# --- Pipeline ---
STATUS_POLL_SECONDS = _env_int("STATUS_POLL_SECONDS", 720)
DISCOVERY_INTERVAL_MINUTES = _env_int("DISCOVERY_INTERVAL_MINUTES", 45)
SYNTHESIS_INTERVAL_MINUTES = _env_int("SYNTHESIS_INTERVAL_MINUTES", 60)
MIN_SEVERITY = os.getenv("MIN_SEVERITY", "Medium")
DOCUMENT_BATCH_SIZE = _env_int("DOCUMENT_BATCH_SIZE", 40)
STATUS_MAX_INCIDENTS_PER_PROVIDER = _env_int("STATUS_MAX_INCIDENTS_PER_PROVIDER", 8)
SYNTHESIS_MAX_EVENTS = _env_int("SYNTHESIS_MAX_EVENTS", 60)

# --- Brave Budget ---
BRAVE_MAX_MONTHLY_CALLS = _env_int("BRAVE_MAX_MONTHLY_CALLS", 2000)
BRAVE_DEFAULT_COUNT = _env_int("BRAVE_DEFAULT_COUNT", 5)
BRAVE_QUERY_LIMIT_PER_RUN = _env_int("BRAVE_QUERY_LIMIT_PER_RUN", 10)

# --- Widget freshness / health ---
TREND_MAX_AGE_MINUTES = _env_int("TREND_MAX_AGE_MINUTES", 180)
SIGNALS_MAX_AGE_MINUTES = _env_int("SIGNALS_MAX_AGE_MINUTES", 180)
HEALTH_STALE_MINUTES = _env_int("HEALTH_STALE_MINUTES", 90)

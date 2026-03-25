"""Budget and limiter helpers for query-aware discovery."""

from __future__ import annotations

from server.config import BRAVE_MAX_MONTHLY_CALLS
from server.repositories.discovery import get_budget_snapshot


class BraveBudgetManager:
    def __init__(self, max_monthly_calls: int = BRAVE_MAX_MONTHLY_CALLS):
        self.max_monthly_calls = max_monthly_calls

    def can_run_query(self) -> bool:
        snapshot = get_budget_snapshot()
        used = int(snapshot.get("total_calls") or 0)
        return used < self.max_monthly_calls

    def remaining(self) -> int:
        snapshot = get_budget_snapshot()
        used = int(snapshot.get("total_calls") or 0)
        return max(self.max_monthly_calls - used, 0)

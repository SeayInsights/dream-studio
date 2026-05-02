"""API routes - FastAPI routers for all endpoints"""

from . import metrics, insights, reports, exports, schedules, realtime, alerts, ml, analytics, frontend

__all__ = ["metrics", "insights", "reports", "exports", "schedules", "realtime", "alerts", "ml", "analytics", "frontend"]

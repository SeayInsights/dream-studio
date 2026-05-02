"""API routes - FastAPI routers for all endpoints"""

from . import metrics, insights, reports, exports, schedules, realtime, alerts, ml

__all__ = ["metrics", "insights", "reports", "exports", "schedules", "realtime", "alerts", "ml"]

"""FastAPI application for dream-studio analytics"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
import uvicorn

from .routes import (
    metrics,
    insights,
    alerts,
    analytics,
    project_intelligence,
    discovery_internal,
    discovery_research,
    hooks,
    security,
    audits,
    intelligence,
    telemetry,
    shared_intelligence,
)
from .routes.guard_metrics import router as guard_metrics_router
from .routes.aggregate_metrics_route import router as aggregate_metrics_router
from .routes.extensions_api import router as extensions_api_router
from .routes.evals import router as evals_router, registry_router as eval_registry_router
from .safety import localhost_origins, SAFE_DEFAULT_HOST


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control headers to all API responses.

    Events are immutable (append-only), so caching is safe.
    5-minute cache improves response times for repeated queries.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Apply caching to all API routes
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "public, max-age=300"
        return response


# Create FastAPI app
app = FastAPI(
    title="Dream-Studio Analytics API",
    description="Enterprise analytics API for dream-studio AI agent platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS middleware — restricted to localhost origins only (Phase 5.6A PD-1)
app.add_middleware(
    CORSMiddleware,
    allow_origins=localhost_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Cache-Control middleware (immutable events, 5-minute cache)
app.add_middleware(CacheControlMiddleware)

# Include routers
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["metrics"])
app.include_router(insights.router, prefix="/api/v1/insights", tags=["insights"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(project_intelligence.router, prefix="/api/v1/projects", tags=["projects"])

app.include_router(discovery_internal.router, prefix="/api/discovery/internal", tags=["discovery"])
app.include_router(discovery_research.router, prefix="/api/discovery/research", tags=["discovery"])
app.include_router(hooks.router, prefix="/api/v1", tags=["hooks"])
app.include_router(security.router, prefix="/api/v1", tags=["security"])
app.include_router(audits.router, prefix="/api/v1", tags=["audits"])
app.include_router(intelligence.router, prefix="/api/v1/intelligence", tags=["intelligence"])
app.include_router(telemetry.router, prefix="/api/telemetry", tags=["telemetry"])
app.include_router(
    shared_intelligence.router, prefix="/api/shared-intelligence", tags=["shared-intelligence"]
)
app.include_router(guard_metrics_router, prefix="/api/v1/guard", tags=["guard"])
app.include_router(aggregate_metrics_router, prefix="/api/v1/metrics", tags=["aggregate-metrics"])
app.include_router(extensions_api_router, prefix="/api/v1/intelligence", tags=["extensions"])
app.include_router(evals_router, prefix="/api/v1/evals", tags=["evals"])
app.include_router(eval_registry_router, prefix="/api/v1/eval", tags=["evals"])


# Frontend routes
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/")
async def root():
    """Root endpoint - serve intelligence dashboard"""
    dashboard_path = FRONTEND_DIR / "dashboard.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path, media_type="text/html")
    return {
        "name": "Dream-Studio Analytics API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/api/docs",
    }


@app.get("/dashboard")
async def dashboard():
    """Serve intelligence dashboard"""
    dashboard_path = FRONTEND_DIR / "dashboard.html"
    if not dashboard_path.exists():
        return JSONResponse(
            status_code=404, content={"error": "Dashboard not found", "path": str(dashboard_path)}
        )
    return FileResponse(dashboard_path, media_type="text/html")


@app.get("/frontend/{file_path:path}")
async def frontend_assets(file_path: str):
    """Serve frontend static assets (CSS, JS, images)"""
    if ".." in file_path or file_path.startswith("/"):
        return JSONResponse(status_code=400, content={"error": "Invalid path"})

    asset_path = FRONTEND_DIR / file_path
    if not asset_path.exists() or not asset_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Asset not found"})

    # Ensure path is within FRONTEND_DIR
    try:
        asset_path.resolve().relative_to(FRONTEND_DIR.resolve())
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid path"})

    return FileResponse(asset_path)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}


@app.exception_handler(Exception)
async def global_exception_handler(_request, exc):
    """Global exception handler"""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "message": str(exc), "type": type(exc).__name__},
    )


def start_api(host: str = SAFE_DEFAULT_HOST, port: int = 8000, reload: bool = False):
    """Start the API server.

    Default host is 127.0.0.1 (localhost only). Pass host="0.0.0.0" explicitly
    to bind on all interfaces — this exposes the dashboard to the network.
    """
    if host == "0.0.0.0":
        import sys

        print(
            "[dashboard] WARNING: binding to 0.0.0.0 exposes the dashboard "
            "to all network interfaces. Use 127.0.0.1 for local-only access.",
            file=sys.stderr,
        )
    uvicorn.run("projections.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    start_api(host=SAFE_DEFAULT_HOST, reload=True)

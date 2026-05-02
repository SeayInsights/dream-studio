"""FastAPI application for dream-studio analytics"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .routes import metrics, insights, reports, exports, realtime, alerts, ml, schedules, frontend, analytics

# Create FastAPI app
app = FastAPI(
    title="Dream-Studio Analytics API",
    description="Enterprise analytics API for dream-studio AI agent platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["metrics"])
app.include_router(insights.router, prefix="/api/v1/insights", tags=["insights"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(exports.router, prefix="/api/v1/export", tags=["export"])
app.include_router(schedules.router, prefix="/api/v1/schedules", tags=["schedules"])
app.include_router(realtime.router, prefix="/api/v1", tags=["realtime"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])
app.include_router(ml.router, prefix="/api/v1/ml", tags=["ml"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(frontend.router, tags=["frontend"])


@app.get("/")
async def root():
    """Root endpoint - API status"""
    return {
        "name": "Dream-Studio Analytics API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/api/docs"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}


@app.exception_handler(Exception)
async def global_exception_handler(_request, exc):
    """Global exception handler"""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "type": type(exc).__name__
        }
    )


def start_api(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Start the API server"""
    uvicorn.run(
        "analytics.api.main:app",
        host=host,
        port=port,
        reload=reload
    )


if __name__ == "__main__":
    start_api(reload=True)

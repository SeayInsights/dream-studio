"""FastAPI application for dream-studio analytics"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pathlib import Path
import uvicorn

from .routes import metrics, insights, reports, exports, realtime, alerts, ml, schedules

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


@app.get("/dashboard")
async def dashboard():
    """Serve interactive analytics dashboard"""
    try:
        from analytics.generators.production_dashboard import ProductionDashboard
        import tempfile
        from fastapi.responses import HTMLResponse

        # Generate dashboard in memory
        dashboard_gen = ProductionDashboard()

        # Create temp file for HTML
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as tmp:
            temp_path = tmp.name

        # Generate dashboard HTML
        html_path = dashboard_gen.generate(days=30, output_path=temp_path)

        # Read HTML content
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Clean up temp file
        import os
        os.unlink(html_path)

        return HTMLResponse(content=html_content)

    except Exception as e:
        return HTMLResponse(
            content=f"""
            <html>
                <body>
                    <h1>Dashboard Error</h1>
                    <p>Failed to generate dashboard: {str(e)}</p>
                    <p>Check server logs for details.</p>
                </body>
            </html>
            """,
            status_code=500
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
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

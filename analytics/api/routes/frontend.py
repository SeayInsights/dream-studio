"""Frontend routes - serves static dashboard files"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter()

# Get the frontend directory path
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"


@router.get("/dashboard")
async def serve_dashboard():
    """Serve the main dashboard HTML file"""
    dashboard_path = FRONTEND_DIR / "dashboard.html"

    if not dashboard_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Dashboard file not found. The dashboard is not yet available."
        )

    return FileResponse(dashboard_path, media_type="text/html")


@router.get("/dashboard/{file_path:path}")
async def serve_dashboard_assets(file_path: str):
    """Serve static assets for the dashboard (CSS, JS, images, etc.)"""
    # Prevent directory traversal attacks
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file path")

    asset_path = FRONTEND_DIR / file_path

    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    # Ensure the resolved path is within FRONTEND_DIR
    try:
        asset_path.resolve().relative_to(FRONTEND_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")

    return FileResponse(asset_path)

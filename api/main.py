"""
main.py — FastAPI application entry point for the Storage Tracker dashboard API.

Run with:
    uvicorn api.main:app --reload --port 8000
or from inside api/:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import storage, real_estate, database as db_router

app = FastAPI(
    title="Self-Storage Market Tracker API",
    version="1.0.0",
    description="REST API backend for the Self-Storage Market Tracker dashboard.",
)

# ---------------------------------------------------------------------------
# CORS — allow all origins for local development
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(storage.router)
app.include_router(real_estate.router)
app.include_router(db_router.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health", tags=["health"])
def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Serve React Frontend (SPA) if dist/ exists
# ---------------------------------------------------------------------------
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

DIST_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        target = DIST_DIR / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST_DIR / "index.html")


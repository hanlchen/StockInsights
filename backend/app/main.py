import logging
import os 
import subprocess
from datetime import datetime
from fastapi import HTTPException, Query
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import market, stock
from app.config import settings
from app.db.init_db import init_db

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Stock Insights API",
    version="0.1.0",
    description="US equities (NYSE/NASDAQ) insights -- personal MVP, SaaS-ready architecture.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/api/admin/refresh-cache")
async def trigger_refresh(token: str = Query(...)):
    """
    Trigger cache refresh from Render cron job.
    Protected by REFRESH_TOKEN environment variable.
    """
    expected_token = os.getenv("REFRESH_TOKEN", "")
    if not expected_token:
        raise HTTPException(status_code=500, detail="REFRESH_TOKEN not configured")
    
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    try:
        print(f"[{datetime.now().isoformat()}] Starting cache refresh...")
        
        result = subprocess.run(
            ["python", "scripts/refresh_cache.py"],
            timeout=900,
            capture_output=True,
            text=True,
            cwd="/opt/render/project/src/backend"  # Run from backend directory
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            print(f"[ERROR] Refresh failed: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Refresh failed: {error_msg}")
        
        print(f"[{datetime.now().isoformat()}] Refresh complete")
        return {"status": "success", "timestamp": datetime.now().isoformat()}
    
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Refresh timeout (15 minutes)")
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
app.include_router(stock.router, prefix=settings.api_v1_prefix)
app.include_router(market.router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

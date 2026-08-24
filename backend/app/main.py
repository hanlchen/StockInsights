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
from fastapi import BackgroundTasks
import asyncio

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
async def trigger_refresh(token: str = Query(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    """Trigger cache refresh in background"""
    expected_token = os.getenv("REFRESH_TOKEN", "")
    if not expected_token:
        raise HTTPException(status_code=500, detail="REFRESH_TOKEN not configured")
    
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Add task to run in background
    background_tasks.add_task(run_refresh)
    
    return {"status": "started", "message": "Refresh running in background"}

def run_refresh():
    """Run refresh in background"""
    try:
        print(f"[{datetime.now().isoformat()}] Starting cache refresh...")
        result = subprocess.run(
            ["python", "scripts/refresh_cache.py"],
            timeout=7200,  # 2 hours
            capture_output=True,
            text=True
        )
        print(f"[{datetime.now().isoformat()}] Refresh complete")
    except Exception as e:
        print(f"[ERROR] {str(e)}")
app.include_router(stock.router, prefix=settings.api_v1_prefix)
app.include_router(market.router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

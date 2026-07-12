import logging

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

app.include_router(stock.router, prefix=settings.api_v1_prefix)
app.include_router(market.router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

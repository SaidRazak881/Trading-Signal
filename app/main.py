"""
Crypto Trading Signal System — FastAPI entrypoint.
Single-link mobile-ready dashboard + API.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import STATIC_DIR
from app.db.database import init_db
from app.services import exchange
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("trading-signal")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Booting Trading Signal System…")
    init_db()
    start_scheduler(run_initial_scan=True)
    yield
    logger.info("Shutting down…")
    stop_scheduler()
    await exchange.close_client()


app = FastAPI(
    title="Crypto Trading Signal",
    description="15m confluence scanner with live TP/SL tracking",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Static frontend
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    index_path = STATIC_DIR / "index.html"
    return FileResponse(str(index_path))


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(str(STATIC_DIR / "manifest.webmanifest"))

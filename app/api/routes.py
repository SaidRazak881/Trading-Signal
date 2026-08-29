"""REST API routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Query

from app.db import database as db
from app.services import signal_engine, tracker

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    from app.services import exchange

    return {
        "status": "ok",
        "service": "trading-signal",
        "data_mode": exchange.data_mode(),
        "demo": exchange.is_demo_mode(),
    }


@router.get("/signals")
async def list_signals(
    status: Optional[str] = Query("all"),
    direction: Optional[str] = Query("all"),
    symbol: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    items = db.get_signals(
        status=status, direction=direction, symbol=symbol, limit=limit, offset=offset
    )
    return {"count": len(items), "signals": items}


@router.get("/signals/active")
async def active_signals():
    items = db.get_active_signals()
    return {"count": len(items), "signals": items}


@router.get("/signals/{signal_id}")
async def one_signal(signal_id: int):
    sig = db.get_signal(signal_id)
    if not sig:
        return {"error": "not_found"}
    events = db.get_events(signal_id)
    return {"signal": sig, "events": events}


@router.get("/stats")
async def stats():
    from app.services import exchange

    s = db.get_stats()
    s["data_mode"] = exchange.data_mode()
    s["demo"] = exchange.is_demo_mode()
    return s


@router.post("/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    """Manually trigger a full market scan (async background)."""
    background_tasks.add_task(signal_engine.run_scan)
    return {"status": "started", "message": "Scan started in background"}


@router.post("/track")
async def trigger_track():
    """Manually run TP/SL tracker once."""
    result = await tracker.track_active_signals()
    return result

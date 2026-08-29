"""Background scheduler for scan + track jobs."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import SCAN_INTERVAL_MINUTES, TRACK_INTERVAL_SECONDS
from app.services import signal_engine, tracker

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def _scan_job() -> None:
    logger.info("── Scheduled scan starting ──")
    result = await signal_engine.run_scan()
    logger.info("── Scan done: %s ──", result)


async def _track_job() -> None:
    result = await tracker.track_active_signals()
    if result.get("closed"):
        logger.info("Tracker closed %s signals", result["closed"])


def start_scheduler(run_initial_scan: bool = True) -> None:
    from datetime import datetime, timedelta, timezone

    from app.services import exchange

    # Align to candle closes: every 15m at :00, :15, :30, :45 + 25s buffer
    scheduler.add_job(
        _scan_job,
        CronTrigger(minute="0,15,30,45", second=25),
        id="market_scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _track_job,
        IntervalTrigger(seconds=TRACK_INTERVAL_SECONDS),
        id="signal_tracker",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started (scan every %sm candle close, track every %ss)",
        SCAN_INTERVAL_MINUTES,
        TRACK_INTERVAL_SECONDS,
    )

    async def _boot() -> None:
        await exchange.probe_live()
        await _scan_job()
        # Populate a bit of closed history for first-run UX (no-op if already present)
        try:
            from app.services.seed import seed_demo_history_if_empty

            seed_demo_history_if_empty()
        except Exception as e:
            logger.debug("Seed skipped: %s", e)

    if run_initial_scan:
        # Slight delay so uvicorn finishes startup cleanly
        run_at = datetime.now(timezone.utc) + timedelta(seconds=1)
        scheduler.add_job(
            _boot,
            "date",
            run_date=run_at,
            id="initial_scan",
            replace_existing=True,
        )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

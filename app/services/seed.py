"""Optional demo history seed so the Stats tab isn't empty on first boot."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from app.db import database as db

logger = logging.getLogger(__name__)

SAMPLES = [
    ("BTCUSDT", "LONG", 88, 97000, 99000, 96000, "win", 99120),
    ("ETHUSDT", "LONG", 81, 3500, 3620, 3440, "win", 3625),
    ("SOLUSDT", "SHORT", 79, 180, 170, 185, "loss", 185.2),
    ("DOGEUSDT", "SHORT", 74, 0.29, 0.27, 0.30, "win", 0.269),
    ("LINKUSDT", "LONG", 85, 18.0, 19.0, 17.5, "expired", 18.2),
    ("AVAXUSDT", "SHORT", 77, 33.0, 31.0, 34.0, "win", 30.9),
    ("BNBUSDT", "LONG", 72, 690, 710, 680, "loss", 679.5),
    ("XRPUSDT", "LONG", 80, 2.40, 2.55, 2.32, "win", 2.56),
]


def seed_demo_history_if_empty() -> int:
    """Insert a handful of closed sample signals when DB has no closed rows."""
    stats = db.get_stats()
    if (stats.get("wins", 0) + stats.get("losses", 0) + stats.get("expired", 0)) > 0:
        return 0
    if stats.get("total_signals", 0) == 0:
        return 0  # wait until a real scan has run

    now = datetime.now(timezone.utc)
    n = 0
    with db.get_conn() as conn:
        for i, (sym, direction, score, entry, tp, sl, status, close_px) in enumerate(SAMPLES):
            detected = (now - timedelta(hours=6 + i)).isoformat()
            closed = (now - timedelta(hours=1 + i * 0.4)).isoformat()
            expires = (now - timedelta(hours=3 + i)).isoformat()
            rr = abs(tp - entry) / max(abs(entry - sl), 1e-12)
            reasons = json.dumps(
                ["Seeded demo history", "1H trend aligned", "Volume confirmation"]
            )
            cur = conn.execute(
                """
                INSERT INTO signals (
                    symbol, timeframe, direction, strategy_type, signal_score,
                    trigger_price, tp_price, sl_price, current_price, atr,
                    risk_reward, reasons, snapshot_json, detected_at, expires_at,
                    status, close_price, closed_at, notes
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sym,
                    "15m",
                    direction,
                    "trend_pullback",
                    score,
                    entry,
                    tp,
                    sl,
                    close_px,
                    abs(entry - sl) / 1.2,
                    round(rr, 2),
                    reasons,
                    "{}",
                    detected,
                    expires,
                    status,
                    close_px,
                    closed,
                    "Demo history sample",
                ),
            )
            sid = cur.lastrowid
            conn.execute(
                """
                INSERT INTO signal_events (signal_id, event_type, event_time, price, meta_json)
                VALUES (?,?,?,?,?)
                """,
                (sid, "created", detected, entry, reasons),
            )
            conn.execute(
                """
                INSERT INTO signal_events (signal_id, event_type, event_time, price, meta_json)
                VALUES (?,?,?,?,?)
                """,
                (sid, status, closed, close_px, json.dumps({"seed": True})),
            )
            n += 1
    logger.info("Seeded %d demo history rows", n)
    return n

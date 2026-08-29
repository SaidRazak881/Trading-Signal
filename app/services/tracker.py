"""Realtime TP/SL tracker for active signals."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db import database as db
from app.services import exchange

logger = logging.getLogger(__name__)


def _parse_ts(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


async def track_active_signals() -> dict:
    """
    Update prices for active signals and resolve win / loss / expired.
    Conservative rule: if both TP and SL would be hit at same tick, mark SL first
    (we only have last price here; full candle resolution is deferred).
    """
    active = db.get_active_signals()
    if not active:
        return {"checked": 0, "closed": 0}

    symbols = list({s["symbol"] for s in active})
    try:
        prices = await exchange.fetch_prices(symbols)
    except Exception as e:
        logger.warning("Price fetch failed: %s", e)
        return {"checked": 0, "closed": 0, "error": str(e)}

    now = datetime.now(timezone.utc)
    closed = 0

    for sig in active:
        price = prices.get(sig["symbol"])
        if price is None:
            continue

        db.update_signal_price(sig["id"], price)

        direction = sig["direction"]
        tp = float(sig["tp_price"])
        sl = float(sig["sl_price"])

        hit_tp = False
        hit_sl = False

        if direction == "LONG":
            hit_tp = price >= tp
            hit_sl = price <= sl
        else:
            hit_tp = price <= tp
            hit_sl = price >= sl

        # expiry check
        expires = _parse_ts(sig["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        if hit_sl and hit_tp:
            # conservative: SL wins
            db.close_signal(sig["id"], "loss", price, "Both TP/SL reachable — SL priority")
            closed += 1
            logger.info("LOSS (ambiguous) %s %s @ %s", direction, sig["symbol"], price)
        elif hit_sl:
            db.close_signal(sig["id"], "loss", price, "SL hit")
            closed += 1
            logger.info("LOSS %s %s @ %s", direction, sig["symbol"], price)
        elif hit_tp:
            db.close_signal(sig["id"], "win", price, "TP hit")
            closed += 1
            logger.info("WIN %s %s @ %s", direction, sig["symbol"], price)
        elif now >= expires:
            db.close_signal(sig["id"], "expired", price, "Signal expired without TP/SL")
            closed += 1
            logger.info("EXPIRED %s %s @ %s", direction, sig["symbol"], price)

    return {"checked": len(active), "closed": closed}

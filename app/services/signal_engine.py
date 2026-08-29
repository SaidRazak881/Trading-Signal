"""
Trend Pullback Momentum signal engine.

Strategy (MVP):
  Higher-timeframe trend (1h) + 15m pullback momentum + volume + ATR risk mgmt.
  Score >= threshold → emit signal with TP/SL.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from app.config import (
    ATR_SL_MULT,
    HTF_TIMEFRAME,
    MAX_ATR_PCT,
    MIN_ATR_PCT,
    MIN_RR,
    RR_RATIO,
    SCORE_MOMENTUM,
    SCORE_STRUCTURE,
    SCORE_TREND,
    SCORE_VOLATILITY,
    SCORE_VOLUME,
    SIGNAL_EXPIRY_CANDLES,
    SIGNAL_SCORE_THRESHOLD,
    TIMEFRAME,
)
from app.db import database as db
from app.services import exchange
from app.services.indicators import enrich, swing_high, swing_low

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _score_long(df15: pd.DataFrame, df1h: pd.DataFrame) -> tuple[float, list[str], dict]:
    """Evaluate LONG setup. Returns (score, reasons, snapshot)."""
    reasons: list[str] = []
    score = 0.0
    i = -2  # last CLOSED candle (avoid forming candle)
    c = df15.iloc[i]
    prev = df15.iloc[i - 1]
    c1h = df1h.iloc[-2]

    snap = {
        "close": float(c["close"]),
        "ema20": float(c["ema20"]),
        "ema50": float(c["ema50"]),
        "ema200": float(c.get("ema200", c["ema50"])),
        "rsi": float(c["rsi"]) if pd.notna(c["rsi"]) else None,
        "macd_hist": float(c["macd_hist"]) if pd.notna(c["macd_hist"]) else None,
        "adx": float(c["adx"]) if pd.notna(c["adx"]) else None,
        "atr": float(c["atr"]) if pd.notna(c["atr"]) else None,
        "atr_pct": float(c["atr_pct"]) if pd.notna(c["atr_pct"]) else None,
        "volume": float(c["volume"]),
        "sma_vol20": float(c["sma_vol20"]) if pd.notna(c["sma_vol20"]) else None,
        "htf_close": float(c1h["close"]),
        "htf_ema50": float(c1h["ema50"]) if pd.notna(c1h["ema50"]) else None,
        "htf_ema200": float(c1h.get("ema200", c1h["ema50"])) if pd.notna(c1h.get("ema200", c1h["ema50"])) else None,
    }

    # ── Trend (25) ──
    trend_pts = 0.0
    htf_bull = (
        pd.notna(c1h.get("ema200"))
        and c1h["close"] > c1h["ema200"]
        and pd.notna(c1h["ema50"])
        and c1h["ema50"] > c1h.get("ema200", c1h["ema50"])
    )
    ltf_bull = (
        pd.notna(c["ema20"])
        and pd.notna(c["ema50"])
        and c["ema20"] > c["ema50"]
        and c["close"] > c["ema50"]
    )
    adx_ok = pd.notna(c["adx"]) and c["adx"] >= 18

    if htf_bull:
        trend_pts += 12
        reasons.append("1H uptrend (price > EMA200)")
    if ltf_bull:
        trend_pts += 8
        reasons.append("15m bullish EMA stack")
    if adx_ok:
        trend_pts += 5
        reasons.append(f"ADX {c['adx']:.0f} (trending)")
    score += min(trend_pts, SCORE_TREND)

    # ── Momentum (20) ──
    mom_pts = 0.0
    rsi_v = c["rsi"] if pd.notna(c["rsi"]) else 50
    rsi_prev = prev["rsi"] if pd.notna(prev["rsi"]) else rsi_v
    hist = c["macd_hist"] if pd.notna(c["macd_hist"]) else 0
    hist_prev = prev["macd_hist"] if pd.notna(prev["macd_hist"]) else hist

    if 42 <= rsi_v <= 62 and rsi_v > rsi_prev:
        mom_pts += 10
        reasons.append(f"RSI rebound {rsi_v:.0f}")
    elif rsi_v > 55:
        mom_pts += 5
        reasons.append(f"RSI bullish {rsi_v:.0f}")

    if hist > hist_prev and hist > 0:
        mom_pts += 10
        reasons.append("MACD hist rising+")
    elif hist > hist_prev:
        mom_pts += 5
        reasons.append("MACD hist rising")
    score += min(mom_pts, SCORE_MOMENTUM)

    # ── Volume (20) ──
    vol_pts = 0.0
    if pd.notna(c["sma_vol20"]) and c["sma_vol20"] > 0:
        ratio = c["volume"] / c["sma_vol20"]
        if ratio >= 1.5:
            vol_pts += 20
            reasons.append(f"Volume spike {ratio:.1f}x")
        elif ratio >= 1.2:
            vol_pts += 14
            reasons.append(f"Volume above avg {ratio:.1f}x")
        elif ratio >= 1.0:
            vol_pts += 8
            reasons.append("Volume ≥ average")
    score += min(vol_pts, SCORE_VOLUME)

    # ── Structure / pullback entry (20) ──
    struct_pts = 0.0
    # pullback toward EMA20/50 in last 3 closed candles then bounce
    window = df15.iloc[i - 3 : i + 1]
    touched_ema = False
    if len(window) >= 3:
        for _, row in window.iloc[:-1].iterrows():
            if pd.notna(row["ema20"]) and row["low"] <= row["ema20"] * 1.005:
                touched_ema = True
            if pd.notna(row["ema50"]) and row["low"] <= row["ema50"] * 1.01:
                touched_ema = True
    bullish_candle = c["close"] > c["open"] and c["close"] >= prev["high"]
    not_extended = pd.notna(c["ema20"]) and c["close"] < c["ema20"] * 1.025

    if touched_ema:
        struct_pts += 10
        reasons.append("Pullback to EMA")
    if bullish_candle:
        struct_pts += 7
        reasons.append("Bullish confirmation candle")
    if not_extended:
        struct_pts += 3
        reasons.append("Not overextended")
    score += min(struct_pts, SCORE_STRUCTURE)

    # ── Volatility suitability (15) ──
    vola_pts = 0.0
    atr_pct = c["atr_pct"] if pd.notna(c["atr_pct"]) else 0
    if MIN_ATR_PCT <= atr_pct <= MAX_ATR_PCT:
        vola_pts += 15
        reasons.append(f"ATR% healthy {atr_pct:.2f}")
    elif atr_pct > 0 and atr_pct < MIN_ATR_PCT:
        vola_pts += 0
        reasons.append("ATR too low")
    elif atr_pct > MAX_ATR_PCT:
        vola_pts += 3
        reasons.append("ATR elevated")
    score += min(vola_pts, SCORE_VOLATILITY)

    # Hard filters — zero out if broken
    if not htf_bull and not ltf_bull:
        score = min(score, 40)
    if atr_pct > 0 and (atr_pct < MIN_ATR_PCT * 0.5 or atr_pct > MAX_ATR_PCT * 1.5):
        score = 0
        reasons.append("Volatility filter fail")

    return score, reasons, snap


def _score_short(df15: pd.DataFrame, df1h: pd.DataFrame) -> tuple[float, list[str], dict]:
    """Evaluate SHORT setup."""
    reasons: list[str] = []
    score = 0.0
    i = -2
    c = df15.iloc[i]
    prev = df15.iloc[i - 1]
    c1h = df1h.iloc[-2]

    snap = {
        "close": float(c["close"]),
        "ema20": float(c["ema20"]),
        "ema50": float(c["ema50"]),
        "ema200": float(c.get("ema200", c["ema50"])),
        "rsi": float(c["rsi"]) if pd.notna(c["rsi"]) else None,
        "macd_hist": float(c["macd_hist"]) if pd.notna(c["macd_hist"]) else None,
        "adx": float(c["adx"]) if pd.notna(c["adx"]) else None,
        "atr": float(c["atr"]) if pd.notna(c["atr"]) else None,
        "atr_pct": float(c["atr_pct"]) if pd.notna(c["atr_pct"]) else None,
        "volume": float(c["volume"]),
        "sma_vol20": float(c["sma_vol20"]) if pd.notna(c["sma_vol20"]) else None,
        "htf_close": float(c1h["close"]),
        "htf_ema50": float(c1h["ema50"]) if pd.notna(c1h["ema50"]) else None,
        "htf_ema200": float(c1h.get("ema200", c1h["ema50"])) if pd.notna(c1h.get("ema200", c1h["ema50"])) else None,
    }

    trend_pts = 0.0
    htf_bear = (
        pd.notna(c1h.get("ema200"))
        and c1h["close"] < c1h["ema200"]
        and pd.notna(c1h["ema50"])
        and c1h["ema50"] < c1h.get("ema200", c1h["ema50"])
    )
    ltf_bear = (
        pd.notna(c["ema20"])
        and pd.notna(c["ema50"])
        and c["ema20"] < c["ema50"]
        and c["close"] < c["ema50"]
    )
    adx_ok = pd.notna(c["adx"]) and c["adx"] >= 18

    if htf_bear:
        trend_pts += 12
        reasons.append("1H downtrend (price < EMA200)")
    if ltf_bear:
        trend_pts += 8
        reasons.append("15m bearish EMA stack")
    if adx_ok:
        trend_pts += 5
        reasons.append(f"ADX {c['adx']:.0f} (trending)")
    score += min(trend_pts, SCORE_TREND)

    mom_pts = 0.0
    rsi_v = c["rsi"] if pd.notna(c["rsi"]) else 50
    rsi_prev = prev["rsi"] if pd.notna(prev["rsi"]) else rsi_v
    hist = c["macd_hist"] if pd.notna(c["macd_hist"]) else 0
    hist_prev = prev["macd_hist"] if pd.notna(prev["macd_hist"]) else hist

    if 38 <= rsi_v <= 58 and rsi_v < rsi_prev:
        mom_pts += 10
        reasons.append(f"RSI reject {rsi_v:.0f}")
    elif rsi_v < 45:
        mom_pts += 5
        reasons.append(f"RSI bearish {rsi_v:.0f}")

    if hist < hist_prev and hist < 0:
        mom_pts += 10
        reasons.append("MACD hist falling-")
    elif hist < hist_prev:
        mom_pts += 5
        reasons.append("MACD hist falling")
    score += min(mom_pts, SCORE_MOMENTUM)

    vol_pts = 0.0
    if pd.notna(c["sma_vol20"]) and c["sma_vol20"] > 0:
        ratio = c["volume"] / c["sma_vol20"]
        if ratio >= 1.5:
            vol_pts += 20
            reasons.append(f"Volume spike {ratio:.1f}x")
        elif ratio >= 1.2:
            vol_pts += 14
            reasons.append(f"Volume above avg {ratio:.1f}x")
        elif ratio >= 1.0:
            vol_pts += 8
            reasons.append("Volume ≥ average")
    score += min(vol_pts, SCORE_VOLUME)

    struct_pts = 0.0
    window = df15.iloc[i - 3 : i + 1]
    touched_ema = False
    if len(window) >= 3:
        for _, row in window.iloc[:-1].iterrows():
            if pd.notna(row["ema20"]) and row["high"] >= row["ema20"] * 0.995:
                touched_ema = True
            if pd.notna(row["ema50"]) and row["high"] >= row["ema50"] * 0.99:
                touched_ema = True
    bearish_candle = c["close"] < c["open"] and c["close"] <= prev["low"]
    not_extended = pd.notna(c["ema20"]) and c["close"] > c["ema20"] * 0.975

    if touched_ema:
        struct_pts += 10
        reasons.append("Pullback to EMA")
    if bearish_candle:
        struct_pts += 7
        reasons.append("Bearish confirmation candle")
    if not_extended:
        struct_pts += 3
        reasons.append("Not overextended")
    score += min(struct_pts, SCORE_STRUCTURE)

    vola_pts = 0.0
    atr_pct = c["atr_pct"] if pd.notna(c["atr_pct"]) else 0
    if MIN_ATR_PCT <= atr_pct <= MAX_ATR_PCT:
        vola_pts += 15
        reasons.append(f"ATR% healthy {atr_pct:.2f}")
    elif atr_pct > MAX_ATR_PCT:
        vola_pts += 3
        reasons.append("ATR elevated")
    score += min(vola_pts, SCORE_VOLATILITY)

    if not htf_bear and not ltf_bear:
        score = min(score, 40)
    if atr_pct > 0 and (atr_pct < MIN_ATR_PCT * 0.5 or atr_pct > MAX_ATR_PCT * 1.5):
        score = 0
        reasons.append("Volatility filter fail")

    return score, reasons, snap


def _build_levels(direction: str, df15: pd.DataFrame) -> Optional[dict]:
    """ATR + structure based TP/SL. Returns None if RR too poor."""
    i = -2
    c = df15.iloc[i]
    trigger = float(c["close"])
    atr_v = float(c["atr"]) if pd.notna(c["atr"]) else trigger * 0.01

    if direction == "LONG":
        sw = swing_low(df15["low"].iloc[: i + 1], 6)
        sl_atr = trigger - ATR_SL_MULT * atr_v
        sl = min(sw, sl_atr)
        # ensure SL is below trigger
        if sl >= trigger:
            sl = trigger - ATR_SL_MULT * atr_v
        risk = trigger - sl
        if risk <= 0:
            return None
        tp = trigger + RR_RATIO * risk
        rr = (tp - trigger) / risk
    else:
        sw = swing_high(df15["high"].iloc[: i + 1], 6)
        sl_atr = trigger + ATR_SL_MULT * atr_v
        sl = max(sw, sl_atr)
        if sl <= trigger:
            sl = trigger + ATR_SL_MULT * atr_v
        risk = sl - trigger
        if risk <= 0:
            return None
        tp = trigger - RR_RATIO * risk
        rr = (trigger - tp) / risk

    if rr < MIN_RR:
        return None

    return {
        "trigger_price": round(trigger, 8),
        "tp_price": round(tp, 8),
        "sl_price": round(sl, 8),
        "atr": round(atr_v, 8),
        "risk_reward": round(rr, 2),
    }


def analyze_pair(
    symbol: str, df15: pd.DataFrame, df1h: pd.DataFrame
) -> list[dict]:
    """Return 0–2 signal dicts (long and/or short) if thresholds met."""
    if df15 is None or df1h is None or len(df15) < 60 or len(df1h) < 50:
        return []

    try:
        df15 = enrich(df15)
        df1h = enrich(df1h)
    except Exception as e:
        logger.warning("Indicator fail %s: %s", symbol, e)
        return []

    results: list[dict] = []
    now = _utcnow()
    expires = now + timedelta(minutes=15 * SIGNAL_EXPIRY_CANDLES)

    for direction, scorer in (("LONG", _score_long), ("SHORT", _score_short)):
        try:
            score, reasons, snap = scorer(df15, df1h)
        except Exception as e:
            logger.debug("Score error %s %s: %s", symbol, direction, e)
            continue

        if score < SIGNAL_SCORE_THRESHOLD:
            continue

        levels = _build_levels(direction, df15)
        if not levels:
            continue

        results.append(
            {
                "symbol": symbol,
                "timeframe": TIMEFRAME,
                "direction": direction,
                "strategy_type": "trend_pullback",
                "signal_score": round(score, 1),
                "trigger_price": levels["trigger_price"],
                "tp_price": levels["tp_price"],
                "sl_price": levels["sl_price"],
                "current_price": levels["trigger_price"],
                "atr": levels["atr"],
                "risk_reward": levels["risk_reward"],
                "reasons": reasons,
                "snapshot": snap,
                "detected_at": now.isoformat(),
                "expires_at": expires.isoformat(),
            }
        )
    return results


async def run_scan() -> dict:
    """Full market scan — called by scheduler every 15 minutes."""
    log_id = db.start_scan_log()
    found = 0
    scanned = 0
    try:
        pairs = await exchange.fetch_usdt_pairs()
        logger.info("Scanning %d liquid pairs…", len(pairs))

        # Process in small concurrent batches to respect rate limits
        batch_size = 5
        for start in range(0, len(pairs), batch_size):
            batch = pairs[start : start + batch_size]
            import asyncio

            bundles = await asyncio.gather(
                *[exchange.fetch_pair_bundle(p["symbol"]) for p in batch],
                return_exceptions=True,
            )
            for item in bundles:
                if isinstance(item, Exception):
                    logger.warning("Bundle error: %s", item)
                    continue
                symbol, df15, df1h = item
                scanned += 1
                signals = analyze_pair(symbol, df15, df1h)
                for sig in signals:
                    try:
                        db.insert_signal(sig)
                        found += 1
                        logger.info(
                            "SIGNAL %s %s score=%.0f RR=%.1f",
                            sig["direction"],
                            sig["symbol"],
                            sig["signal_score"],
                            sig["risk_reward"],
                        )
                    except Exception as e:
                        logger.warning("Insert fail: %s", e)

            # gentle pacing between batches
            import asyncio as _aio
            await _aio.sleep(0.35)

        db.finish_scan_log(log_id, scanned, found, "ok", f"scanned {scanned}")
        return {"scanned": scanned, "found": found, "status": "ok"}
    except Exception as e:
        logger.exception("Scan failed")
        db.finish_scan_log(log_id, scanned, found, "error", str(e))
        return {"scanned": scanned, "found": found, "status": "error", "error": str(e)}

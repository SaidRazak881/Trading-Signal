"""
Deterministic demo market data.

Used automatically when live exchange APIs are unreachable (e.g. sandboxed
networks). Produces realistic OHLCV with seeded randomness so the signal
engine, tracker, and dashboard can be fully exercised offline.
"""
from __future__ import annotations

import hashlib
import math
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

# Liquid-ish demo universe
DEMO_PAIRS: list[tuple[str, float, float]] = [
    # symbol, base_price, daily_vol_scale
    ("BTCUSDT", 97500.0, 0.012),
    ("ETHUSDT", 3550.0, 0.018),
    ("BNBUSDT", 695.0, 0.02),
    ("SOLUSDT", 178.0, 0.028),
    ("XRPUSDT", 2.45, 0.025),
    ("ADAUSDT", 0.82, 0.03),
    ("DOGEUSDT", 0.28, 0.035),
    ("AVAXUSDT", 32.5, 0.03),
    ("DOTUSDT", 6.8, 0.028),
    ("LINKUSDT", 18.4, 0.026),
    ("MATICUSDT", 0.55, 0.032),
    ("LTCUSDT", 98.0, 0.022),
    ("ATOMUSDT", 8.2, 0.03),
    ("UNIUSDT", 12.1, 0.03),
    ("NEARUSDT", 5.4, 0.035),
    ("APTUSDT", 9.8, 0.032),
    ("ARBUSDT", 0.72, 0.035),
    ("OPUSDT", 1.65, 0.034),
    ("SUIUSDT", 3.4, 0.04),
    ("PEPEUSDT", 0.0000125, 0.05),
    ("WIFUSDT", 1.85, 0.045),
    ("AAVEUSDT", 245.0, 0.028),
    ("FILUSDT", 4.9, 0.03),
    ("INJUSDT", 22.0, 0.035),
    ("TIAUSDT", 5.1, 0.038),
    ("SEIUSDT", 0.48, 0.04),
    ("RENDERUSDT", 7.2, 0.035),
    ("FETUSDT", 1.35, 0.036),
    ("IMXUSDT", 1.22, 0.033),
    ("STXUSDT", 1.55, 0.032),
]


def _seed_for(symbol: str, interval: str, bucket: int) -> int:
    h = hashlib.sha256(f"{symbol}|{interval}|{bucket}".encode()).hexdigest()
    return int(h[:16], 16) % (2**31 - 1)


def _interval_ms(interval: str) -> int:
    return {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
    }.get(interval, 900_000)


def _base_meta(symbol: str) -> tuple[float, float]:
    for s, px, vol in DEMO_PAIRS:
        if s == symbol:
            return px, vol
    # fallback hash price
    h = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
    return 10 + (h % 5000) / 10.0, 0.03


def generate_klines(
    symbol: str,
    interval: str = "15m",
    limit: int = 100,
    now_ms: Optional[int] = None,
) -> pd.DataFrame:
    """Synthetic OHLCV ending at the current (or given) time."""
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    step = _interval_ms(interval)
    # align to candle open
    last_open = (now_ms // step) * step
    base_px, vol_scale = _base_meta(symbol)

    # slow regime drift keyed by day so trends persist across refreshes
    day_bucket = now_ms // 86_400_000
    rng_regime = np.random.default_rng(_seed_for(symbol, "regime", day_bucket))
    # bias: -1 bear, 0 flat, +1 bull — weighted slightly random
    regime = float(rng_regime.choice([-1.0, -0.5, 0.0, 0.5, 1.0], p=[0.15, 0.2, 0.2, 0.25, 0.2]))
    # some symbols forced into clearer trends for demo signal density
    force = {
        "BTCUSDT": 0.7,
        "ETHUSDT": 0.55,
        "SOLUSDT": 0.8,
        "DOGEUSDT": -0.6,
        "XRPUSDT": 0.4,
        "PEPEUSDT": -0.5,
        "LINKUSDT": 0.65,
        "AVAXUSDT": -0.45,
        "SUIUSDT": 0.75,
        "WIFUSDT": -0.7,
    }
    if symbol in force:
        regime = force[symbol]

    rng = np.random.default_rng(_seed_for(symbol, interval, last_open // step))

    # build path backwards then reverse
    n = limit
    rets = rng.normal(loc=regime * vol_scale * 0.15, scale=vol_scale * 0.55, size=n)
    # inject a few pullback / impulse moves near the end so setups appear
    if n >= 20:
        if regime > 0.2:
            # dip then bounce in last ~8 bars
            rets[-10:-6] = -abs(rng.normal(vol_scale * 0.8, vol_scale * 0.2, 4))
            rets[-4:] = abs(rng.normal(vol_scale * 1.1, vol_scale * 0.25, 4))
        elif regime < -0.2:
            rets[-10:-6] = abs(rng.normal(vol_scale * 0.8, vol_scale * 0.2, 4))
            rets[-4:] = -abs(rng.normal(vol_scale * 1.1, vol_scale * 0.25, 4))

    # start price so that end ≈ base_px * (1 + slow sine)
    phase = (now_ms / 3_600_000) * 0.15 + (hash(symbol) % 100) / 100
    target = base_px * (1 + 0.03 * math.sin(phase) + regime * 0.02)
    # walk forward from a start chosen so last close ~ target
    log_path = np.cumsum(rets)
    path = target * np.exp(log_path - log_path[-1])

    rows = []
    for i in range(n):
        open_t = last_open - (n - 1 - i) * step
        o = float(path[i - 1]) if i else float(path[0] * (1 - rets[0] * 0.3))
        c = float(path[i])
        wick = abs(float(rng.normal(0, vol_scale * c * 0.35)))
        h = max(o, c) + wick
        l = min(o, c) - wick
        # volume higher on impulse bars
        base_vol = 5000 + (hash(symbol) % 8000)
        vol_mult = 1.0 + abs(rets[i]) / max(vol_scale, 1e-6)
        if i >= n - 3:
            vol_mult *= 1.6  # recent volume spike bias
        volume = float(base_vol * vol_mult * (1 + rng.random()))
        rows.append(
            {
                "open_time": pd.to_datetime(open_t, unit="ms", utc=True),
                "open": o,
                "high": h,
                "low": max(l, 1e-12),
                "close": max(c, 1e-12),
                "volume": volume,
                "close_time": pd.to_datetime(open_t + step - 1, unit="ms", utc=True),
                "quote_volume": volume * c,
                "trades": int(1000 * vol_mult),
                "taker_buy_base": volume * 0.5,
                "taker_buy_quote": volume * c * 0.5,
                "ignore": 0,
            }
        )
    return pd.DataFrame(rows)


def list_pairs() -> list[dict]:
    now = datetime.now(timezone.utc)
    out = []
    for i, (sym, px, vol) in enumerate(DEMO_PAIRS):
        # mild live drift
        drift = 1 + 0.01 * math.sin(time.time() / 600 + i)
        last = px * drift
        out.append(
            {
                "symbol": sym,
                "last_price": last,
                "quote_volume": 20_000_000 * (1.5 - i * 0.03),
                "price_change_pct": round(vol * 100 * math.sin(time.time() / 900 + i), 2),
            }
        )
    return out


def last_prices(symbols: list[str]) -> dict[str, float]:
    """Current mark price — walks slightly so TP/SL can eventually resolve."""
    result = {}
    t = time.time()
    for sym in symbols:
        base, vol = _base_meta(sym)
        # Use recent 15m close as anchor, then micro-jitter
        df = generate_klines(sym, "15m", 5)
        anchor = float(df.iloc[-1]["close"]) if len(df) else base
        # progressive drift so active signals eventually hit TP or SL
        # direction biased by symbol hash so some win / some lose over time
        bias = 1 if (hash(sym) % 2 == 0) else -1
        age_factor = ((t // 30) % 200) / 200.0  # slow crawl
        move = bias * vol * 0.08 * age_factor
        jitter = 0.0005 * math.sin(t / 7 + hash(sym) % 50)
        result[sym] = max(anchor * (1 + move + jitter), 1e-12)
    return result

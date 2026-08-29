"""Binance market data client with automatic demo-market fallback."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx
import pandas as pd

from app.config import (
    BINANCE_BASE,
    CANDLE_LIMIT,
    HTF_CANDLE_LIMIT,
    MAX_PAIRS_TO_SCAN,
    MIN_QUOTE_VOLUME_USDT,
)
from app.services import demo_market

logger = logging.getLogger(__name__)

# Prefer live; fall back through mirrors; finally demo
BINANCE_BASES = [
    os.environ.get("BINANCE_BASE", BINANCE_BASE),
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

# Shared state
_client: Optional[httpx.AsyncClient] = None
_live_ok: Optional[bool] = None  # None=unknown, True=live, False=demo
_force_demo = os.environ.get("FORCE_DEMO", "").lower() in ("1", "true", "yes")


def is_demo_mode() -> bool:
    return _force_demo or _live_ok is False


def data_mode() -> str:
    if _force_demo:
        return "demo"
    if _live_ok is True:
        return "live"
    if _live_ok is False:
        return "demo"
    return "unknown"


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=8.0),
            headers={"User-Agent": "TradingSignal/1.0"},
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def _get_live(path: str, params: dict | None = None) -> any:
    """Try each Binance base. Raises on total failure."""
    client = await get_client()
    last_err: Exception | None = None
    for base in BINANCE_BASES:
        if not base:
            continue
        url = f"{base.rstrip('/')}{path}"
        for attempt in range(2):
            try:
                r = await client.get(url, params=params)
                if r.status_code == 429:
                    await asyncio.sleep(1.2 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                logger.debug("Live fail %s via %s: %s", path, base, e)
                await asyncio.sleep(0.25)
    if last_err:
        raise last_err
    raise RuntimeError("No exchange base configured")


async def probe_live() -> bool:
    """One-shot connectivity check."""
    global _live_ok
    if _force_demo:
        _live_ok = False
        return False
    try:
        await _get_live("/api/v3/ping")
        _live_ok = True
        logger.info("Exchange connectivity: LIVE (Binance)")
        return True
    except Exception as e:
        _live_ok = False
        logger.warning(
            "Exchange unreachable (%s) — switching to DEMO market data", e
        )
        return False


async def fetch_usdt_pairs() -> list[dict]:
    """Return liquid USDT spot pairs sorted by 24h quote volume."""
    global _live_ok
    if is_demo_mode():
        pairs = demo_market.list_pairs()
        return pairs[:MAX_PAIRS_TO_SCAN]

    try:
        data = await _get_live("/api/v3/ticker/24hr")
        _live_ok = True
    except Exception as e:
        logger.warning("Live pairs failed (%s) — demo fallback", e)
        _live_ok = False
        return demo_market.list_pairs()[:MAX_PAIRS_TO_SCAN]

    if not data:
        return demo_market.list_pairs()[:MAX_PAIRS_TO_SCAN]

    pairs = []
    for t in data:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        if any(x in base for x in ("UP", "DOWN", "BULL", "BEAR")):
            continue
        if base in ("USDC", "BUSD", "TUSD", "FDUSD", "DAI", "EUR", "GBP", "TRY", "USD"):
            continue
        try:
            qv = float(t.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue
        if qv < MIN_QUOTE_VOLUME_USDT:
            continue
        pairs.append(
            {
                "symbol": sym,
                "last_price": float(t.get("lastPrice", 0)),
                "quote_volume": qv,
                "price_change_pct": float(t.get("priceChangePercent", 0)),
            }
        )
    pairs.sort(key=lambda x: x["quote_volume"], reverse=True)
    return pairs[:MAX_PAIRS_TO_SCAN]


async def fetch_klines(
    symbol: str,
    interval: str = "15m",
    limit: int = CANDLE_LIMIT,
) -> pd.DataFrame:
    """Fetch OHLCV candles as DataFrame."""
    global _live_ok
    if is_demo_mode():
        return demo_market.generate_klines(symbol, interval, limit)

    try:
        data = await _get_live(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        _live_ok = True
    except Exception as e:
        logger.debug("Klines live fail %s: %s — demo", symbol, e)
        _live_ok = False
        return demo_market.generate_klines(symbol, interval, limit)

    if not data:
        return demo_market.generate_klines(symbol, interval, limit)

    cols = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trades",
        "taker_buy_base",
        "taker_buy_quote",
        "ignore",
    ]
    df = pd.DataFrame(data, columns=cols)
    for col in ("open", "high", "low", "close", "volume", "quote_volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df


async def fetch_prices(symbols: list[str]) -> dict[str, float]:
    """Batch fetch last prices for given symbols."""
    global _live_ok
    if not symbols:
        return {}
    if is_demo_mode():
        return demo_market.last_prices(symbols)

    try:
        data = await _get_live("/api/v3/ticker/price")
        _live_ok = True
    except Exception as e:
        logger.debug("Prices live fail: %s — demo", e)
        _live_ok = False
        return demo_market.last_prices(symbols)

    if not data:
        return demo_market.last_prices(symbols)
    wanted = set(symbols)
    return {
        t["symbol"]: float(t["price"])
        for t in data
        if t.get("symbol") in wanted
    }


async def fetch_pair_bundle(symbol: str) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    """Fetch 15m + 1h candles for one symbol concurrently."""
    tf, htf = await asyncio.gather(
        fetch_klines(symbol, "15m", CANDLE_LIMIT),
        fetch_klines(symbol, "1h", HTF_CANDLE_LIMIT),
    )
    return symbol, tf, htf

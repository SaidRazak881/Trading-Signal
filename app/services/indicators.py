"""Technical indicator calculations (pure numpy/pandas, no TA-Lib)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ef = ema(close, fast)
    es = ema(close, slow)
    line = ef - es
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr_atr = atr(high, low, close, period)
    plus_di = 100 * pd.Series(plus_dm, index=close.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean() / tr_atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=close.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean() / tr_atr.replace(0, np.nan)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def swing_low(low: pd.Series, lookback: int = 5) -> float:
    return float(low.iloc[-lookback:].min())


def swing_high(high: pd.Series, lookback: int = 5) -> float:
    return float(high.iloc[-lookback:].max())


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicators used by the signal engine."""
    c = df["close"]
    h = df["high"]
    l = df["low"]
    v = df["volume"]

    df = df.copy()
    df["ema20"] = ema(c, 20)
    df["ema50"] = ema(c, 50)
    df["ema200"] = ema(c, 200) if len(df) >= 200 else ema(c, min(100, len(df)))
    df["sma_vol20"] = sma(v, 20)
    df["rsi"] = rsi(c, 14)
    macd_line, macd_sig, macd_hist = macd(c)
    df["macd"] = macd_line
    df["macd_signal"] = macd_sig
    df["macd_hist"] = macd_hist
    df["atr"] = atr(h, l, c, 14)
    df["adx"] = adx(h, l, c, 14)
    df["atr_pct"] = (df["atr"] / c) * 100
    return df

"""Application configuration."""
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "signals.db"
STATIC_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"

# Exchange
BINANCE_BASE = "https://api.binance.com"
BINANCE_FUTURES = "https://fapi.binance.com"

# Screening
TIMEFRAME = "15m"
HTF_TIMEFRAME = "1h"
CANDLE_LIMIT = 100
HTF_CANDLE_LIMIT = 100
MIN_QUOTE_VOLUME_USDT = 5_000_000  # min 24h volume
MAX_PAIRS_TO_SCAN = 60
SIGNAL_SCORE_THRESHOLD = 65
SIGNAL_EXPIRY_CANDLES = 12  # 12 * 15m = 3 hours
SCAN_INTERVAL_MINUTES = 15
TRACK_INTERVAL_SECONDS = 20

# Risk
ATR_SL_MULT = 1.2
RR_RATIO = 2.0
MIN_RR = 1.5
MIN_ATR_PCT = 0.15  # too quiet
MAX_ATR_PCT = 4.0   # too wild

# Scoring weights (sum = 100)
SCORE_TREND = 25
SCORE_MOMENTUM = 20
SCORE_VOLUME = 20
SCORE_STRUCTURE = 20
SCORE_VOLATILITY = 15

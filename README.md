# Signal Desk — Crypto Trading Signal System

Mobile-first HTML dashboard + FastAPI backend that **screens liquid USDT pairs every 15 minutes**, emits **confluence signal cards** (entry / TP / SL / score), and **tracks win·loss·expired** in realtime.

Open **one link** on your phone — that's it.

## What it does

| Layer | Behaviour |
|---|---|
| **Scanner** | Every 15m candle close → top liquid Binance USDT pairs |
| **Strategy** | HTF trend (1h) + 15m pullback momentum + volume + ATR risk |
| **Scoring** | Trend 25 · Momentum 20 · Volume 20 · Structure 20 · Volatility 15 |
| **Risk** | SL = swing ± 1.2×ATR · TP = 2R · min RR 1.5 |
| **Tracker** | Every 20s price poll → mark TP hit / SL hit / expired (3h) |
| **UI** | Single-page mobile PWA-style dashboard |

## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Then open: **http://\<host\>:8000/** on any phone or desktop.

### Environment

| Var | Default | Meaning |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | HTTP port (Render/Railway/Fly inject this) |
| `RELOAD` | `0` | Uvicorn auto-reload |
| `FORCE_DEMO` | unset | `1` = always use synthetic market data |
| `BINANCE_BASE` | `https://api.binance.com` | Override exchange REST base |

No exchange API key required — public Binance market data only.

If Binance is unreachable (firewall / geo / sandbox), the system **automatically falls back to a realistic demo market** so the dashboard, scanner, and win/loss tracker still work. A **DEMO** badge appears in the header.


## Deploy on Koyeb (1 click — recommended)

You logged into Koyeb with GitHub. Use the same flow as the [official FastAPI guide](https://www.koyeb.com/docs/deploy/fastapi):

[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&builder=buildpack&repository=github.com/SaidRazak881/Trading-Signal&branch=arena/01a04e6d-trading-signal&name=signal-desk&run_command=uvicorn%20app.main%3Aapp%20--host%200.0.0.0%20--port%208000&ports=8000%3Bhttp%3B%2F&instance_type=free&env%5BHOST%5D=0.0.0.0&env%5BFORCE_DEMO%5D=0&env%5BPYTHONUNBUFFERED%5D=1&service_type=web)

**Full guide:** [docs/KOYEB_CLICK.md](docs/KOYEB_CLICK.md)

After deploy opens `*.koyeb.app` on your phone. Health: `/api/health`.

---
## One-click deploy (Koyeb Free)

Login Koyeb with GitHub, then open this link:

**[Deploy Signal Desk to Koyeb](https://app.koyeb.com/deploy?type=git&name=signal-desk&repository=github.com%2FSaidRazak881%2FTrading-Signal&branch=arena%2F01a04e6d-trading-signal&builder=dockerfile&dockerfile=Dockerfile&ports=8000%3Bhttp%3B%2F&instance_type=free&env%5BHOST%5D=0.0.0.0&env%5BFORCE_DEMO%5D=0&env%5BPYTHONUNBUFFERED%5D=1&service_type=web)**

Or paste URL:
```
https://app.koyeb.com/deploy?type=git&name=signal-desk&repository=github.com%2FSaidRazak881%2FTrading-Signal&branch=arena%2F01a04e6d-trading-signal&builder=dockerfile&dockerfile=Dockerfile&ports=8000%3Bhttp%3B%2F&instance_type=free&env%5BHOST%5D=0.0.0.0&env%5BFORCE_DEMO%5D=0&env%5BPYTHONUNBUFFERED%5D=1&service_type=web
```

Pre-filled: branch, Dockerfile, port 8000, Free instance, env. Review → **Deploy** → open `*.koyeb.app` on phone.

Fallback (buildpack if Docker build fails):
```
https://app.koyeb.com/deploy?type=git&name=signal-desk&repository=github.com%2FSaidRazak881%2FTrading-Signal&branch=arena%2F01a04e6d-trading-signal&builder=buildpack&run_command=python%20run.py&ports=8000%3Bhttp%3B%2F&instance_type=free&env%5BHOST%5D=0.0.0.0&env%5BFORCE_DEMO%5D=0&env%5BPYTHONUNBUFFERED%5D=1&service_type=web
```

## Deploy free (one mobile link)

Ready-made configs:

| File | Platform |
|---|---|
| `Dockerfile` | Any container host |
| `fly.toml` | **Fly.io** (recommended always-on) |
| `koyeb.yaml` | Koyeb free nano |
| `render.yaml` | Render free (+ keep-warm ping) |
| `railway.toml` | Railway trial |
| `Procfile` / `runtime.txt` | Generic PaaS |

Full steps: **[docs/DEPLOY.md](docs/DEPLOY.md)**  
Copy-paste brief for another GPT agent: **[docs/GPT_DEPLOY_BRIEF.md](docs/GPT_DEPLOY_BRIEF.md)**  
Malay one-block prompt: **[docs/PROMPT_UNTUK_GPT.txt](docs/PROMPT_UNTUK_GPT.txt)**

**Free host preference:** Fly.io → Koyeb → Render+ping → Railway.  
Avoid Vercel/Netlify/Workers (no long-lived scheduler).

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Dashboard |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/signals` | List signals (`?status=&direction=&symbol=`) |
| `GET` | `/api/signals/active` | Active only |
| `GET` | `/api/signals/{id}` | Detail + events |
| `GET` | `/api/stats` | Win rate, top pairs, last scan |
| `POST` | `/api/scan` | Force full market scan |
| `POST` | `/api/track` | Force TP/SL check |

## Strategy (MVP) — Trend Pullback Momentum

**Long** when:
- 1h close > EMA200 and EMA50 > EMA200
- 15m EMA20 > EMA50, price > EMA50
- Pullback toward EMA in last 3 candles
- RSI rebound ~45–60, MACD histogram rising
- Volume ≥ SMA20, healthy ATR%
- Bullish confirmation candle

**Short** is the mirror.

Signals only fire after the **closed** 15m candle (index `-2`) to cut noise.

## Project layout

```
app/
  main.py              # FastAPI app + static mount
  config.py            # thresholds, intervals
  api/routes.py        # REST endpoints
  db/database.py       # SQLite schema + CRUD
  services/
    exchange.py        # Binance public client
    indicators.py      # EMA RSI MACD ATR ADX
    signal_engine.py   # scoring + TP/SL
    tracker.py         # live win/loss
    scheduler.py       # APScheduler jobs
frontend/
  index.html           # single-page mobile UI
  css/app.css
  js/app.js
data/signals.db        # created at runtime
run.py
```

## Notes & realism

- This is a **signal desk**, not guaranteed alpha. Backtest before sizing real risk.
- Tracker uses last price; if TP and SL both reachable on the same tick, **SL wins** (conservative).
- Pair universe is filtered by 24h quote volume (default ≥ $5M) and capped for rate limits.
- Expired signals (default 12 × 15m = 3h) are not counted as wins or losses.

## License

MIT — use at your own risk. Not financial advice.

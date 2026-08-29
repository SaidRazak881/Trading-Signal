# Deploy guide — Signal Desk (free tier)

Mobile-openable single URL. Long-running Python process. Outbound Binance HTTPS.

## Platform comparison (free)

| Platform | Always-on? | Outbound HTTPS | Persistent disk | Free catch | Recommendation |
|---|---|---|---|---|---|
| **Fly.io** | Yes (allowance) | Yes | Volume | May ask card; free allowance limited | **#1 choice** |
| **Koyeb** | Yes (nano free) | Yes | Ephemeral* | Free instance limits | **#2 choice** |
| **Render** | No — sleeps ~15m | Yes | Ephemeral on free | Needs keep-warm ping | **#3** if no Fly/Koyeb |
| **Railway** | While credits last | Yes | Volume (paid often) | Trial credits burn fast | Short demo only |
| Cloud Run | Cold start | Yes | No | Cold starts break 15m cadence | Last resort |
| Vercel / Netlify | N/A serverless | Limited | No | No APScheduler | **Do not use** |
| GitHub Pages | Static | N/A | No | No backend | **Do not use** |
| PythonAnywhere free | Always | Whitelist only | Yes | Binance often blocked | Avoid |

\*Use external backup or accept history loss on redeploy.

## App contract (all platforms)

| Item | Value |
|---|---|
| Start command | `python run.py` |
| Bind | `0.0.0.0:$PORT` |
| Health | `GET /api/health` |
| UI | `GET /` |
| Force scan | `POST /api/scan` |
| Python | 3.11 |
| Env | `FORCE_DEMO=0`, `HOST=0.0.0.0` |
| Data dir | `./data` → SQLite `signals.db` |

---

## Option 1 — Fly.io (recommended)

```bash
# install flyctl, login
fly auth login

cd Trading-Signal
fly launch --config fly.toml --copy-config --no-deploy
# set unique app name if signal-desk is taken:
# fly apps create signal-desk-YOURNAME

fly volumes create signal_data --region sin --size 1
fly secrets set FORCE_DEMO=0
fly deploy

fly status
fly open
curl -s https://$(fly info -j | jq -r .Hostname)/api/health
```

Notes:
- `auto_stop_machines = "off"` and `min_machines_running = 1` keep scanner alive within free allowance.
- Watch free allowance; scale to 0 if unused for long periods: `fly scale count 0`.

---

## Option 2 — Koyeb free nano

Dashboard (easiest free path without card in many regions):

1. New App → Import GitHub repo `SaidRazak881/Trading-Signal`
2. Branch with app code
3. Build: Dockerfile **or** buildpack Python
4. Run command: `python run.py`
5. Port: `8000`
6. Env: `HOST=0.0.0.0`, `FORCE_DEMO=0`
7. Instance type: **Free**
8. Region: Singapore / Frankfurt

CLI sketch:

```bash
koyeb login
koyeb app create signal-desk
# link GitHub repo in dashboard for continuous deploy
```

---

## Option 3 — Render free + keep-warm ping

`render.yaml` is included.

1. Render → New → Blueprint → connect repo
2. Or New Web Service → Python → build `pip install -r requirements.txt` → start `python run.py`
3. Health check path: `/api/health`
4. Env: `FORCE_DEMO=0`, `PYTHON_VERSION=3.11.9`

**Critical:** free web services spin down after idle.

Keep warm (pick one free ping):

- [cron-job.org](https://cron-job.org) → every 10 minutes → `GET https://YOUR.onrender.com/api/health`
- Better Stack / UptimeRobot free monitor

Without ping, 15-minute scans pause while asleep.

---

## Option 4 — Railway trial

```bash
railway login
railway init
railway up
railway domain
```

Set `FORCE_DEMO=0`. Watch credit balance.

---

## Docker local smoke test

```bash
docker build -t signal-desk .
docker run --rm -p 8000:8000 -e FORCE_DEMO=0 signal-desk
# if no Binance from your network:
docker run --rm -p 8000:8000 -e FORCE_DEMO=1 signal-desk
```

---

## Post-deploy verification

```bash
URL=https://your-app.example
curl -s $URL/api/health
curl -s $URL/api/stats
curl -s -X POST $URL/api/scan
sleep 20
curl -s $URL/api/signals/active | head
```

Phone: open `$URL/` — should show Signal Desk, LIVE/DEMO pill, stats strip.

| health field | meaning |
|---|---|
| `demo: false`, `data_mode: live` | Real Binance data |
| `demo: true` | Synthetic market — change region/host |

---

## Common failures

| Symptom | Fix |
|---|---|
| Deploy OK but `demo:true` | Host blocked Binance → change region or platform |
| UI 502 | Process crashed — check logs; ensure `PORT` honored |
| No signals | Wait for scan or `POST /api/scan`; check score threshold |
| History wiped | No persistent volume — add Fly volume / accept ephemeral |
| Sleeps every 15m | Render free — add cron ping |
| Build fails on pandas | Use Python 3.11 slim / official Dockerfile |

---

## Security notes (MVP)

- Dashboard is public — fine for personal signal desk
- No exchange keys stored
- Do not expose write admin without auth later
- SQLite is not multi-region HA

---

## Merge branch reminder

If `main` still only has the initial README:

```bash
git checkout main
git merge arena/01a04e6d-trading-signal
git push origin main
```

Then point the free host at `main`.

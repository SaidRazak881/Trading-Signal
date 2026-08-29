# Deploy Signal Desk on Koyeb (GitHub login)

You registered Koyeb **with GitHub**. Use the **same 1-click flow** as the
[official FastAPI guide](https://www.koyeb.com/docs/deploy/fastapi).

Koyeb platform status (all OPERATIONAL last check): https://status.koyeb.com/

---

## Step 1 — Click this (primary)

### Buildpack (same style as Koyeb FastAPI docs)

[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&builder=buildpack&repository=github.com/SaidRazak881/Trading-Signal&branch=arena/01a04e6d-trading-signal&name=signal-desk&run_command=uvicorn%20app.main%3Aapp%20--host%200.0.0.0%20--port%208000&ports=8000%3Bhttp%3B%2F&instance_type=free&env%5BHOST%5D=0.0.0.0&env%5BFORCE_DEMO%5D=0&env%5BPYTHONUNBUFFERED%5D=1&service_type=web)

**Raw URL (copy-paste if button fails):**

```
https://app.koyeb.com/deploy?type=git&builder=buildpack&repository=github.com/SaidRazak881/Trading-Signal&branch=arena/01a04e6d-trading-signal&name=signal-desk&run_command=uvicorn%20app.main%3Aapp%20--host%200.0.0.0%20--port%208000&ports=8000%3Bhttp%3B%2F&instance_type=free&env%5BHOST%5D=0.0.0.0&env%5BFORCE_DEMO%5D=0&env%5BPYTHONUNBUFFERED%5D=1&service_type=web
```

### Dockerfile alternative

```
https://app.koyeb.com/deploy?type=git&builder=dockerfile&repository=github.com/SaidRazak881/Trading-Signal&branch=arena/01a04e6d-trading-signal&name=signal-desk&dockerfile=Dockerfile&ports=8000%3Bhttp%3B%2F&instance_type=free&env%5BHOST%5D=0.0.0.0&env%5BFORCE_DEMO%5D=0&env%5BPYTHONUNBUFFERED%5D=1&service_type=web
```

---

## Step 2 — On the Koyeb page

1. Stay logged in with **GitHub** (same account that owns the repo).
2. If asked **Install GitHub App** → Install → allow `Trading-Signal`.
3. Confirm:
   - Repository: `SaidRazak881/Trading-Signal`
   - Branch: **`arena/01a04e6d-trading-signal`** (not empty `main`)
   - Run command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - Port **8000**
   - Instance **Free** / Nano
4. Click **Deploy**.
5. Wait until status is **Healthy**.
6. Open `https://<name>-<id>.koyeb.app` on your phone.

---

## Step 3 — Verify

```bash
curl -sS https://YOUR.koyeb.app/api/health
curl -sS -X POST https://YOUR.koyeb.app/api/scan
```

Phone: open `/` → Signal Desk UI.

---

## Match with official FastAPI docs

| Official example | This project |
|---|---|
| `uvicorn main:app --host 0.0.0.0` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| `requirements.txt` | yes |
| `runtime.txt` / `.python-version` | `3.11` |
| Buildpack | primary path |
| Port 8000 | yes |
| One-click `app.koyeb.com/deploy?...` | links above |

---

## If deploy page looks empty / only “1 click”

That **is** the correct UI. Do **not** search for “Create Web Service”.
Use the deploy URL above — it is the same mechanism as the docs button.

---

## Practice first (optional)

Official tiny FastAPI demo (to learn the UI):

https://app.koyeb.com/deploy?type=git&builder=buildpack&repository=github.com/koyeb/example-fastapi&branch=main&name=fastapi-on-koyeb

When that works, use **Step 1** for Signal Desk.

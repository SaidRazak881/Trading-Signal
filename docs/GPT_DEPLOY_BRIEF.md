# GPT Deploy Brief — Signal Desk

> **How to use this file**
> 1. Open a new GPT / Cursor / Claude chat that can access GitHub + run terminal.
> 2. Paste **SECTION A** (system role) first.
> 3. Paste **SECTION B** (task) second, after connecting the repo.
> 4. If GPT asks clarifying questions, answer using **SECTION C** defaults.
> 5. After deploy, run **SECTION D** verification checklist.

Repo: `https://github.com/SaidRazak881/Trading-Signal`  
Preferred branch to deploy: `main` (merge `arena/01a04e6d-trading-signal` first if needed)  
or deploy branch `arena/01a04e6d-trading-signal` directly.

---

## SECTION A — System role (paste first)

```
You are a senior DevOps + Python engineer. Your job is to deploy the
"Signal Desk" crypto trading signal system from this GitHub repo to a
FREE hosting platform that:

1. Supports a long-running Python web process (FastAPI + Uvicorn)
2. Allows OUTBOUND HTTPS to Binance public API (api.binance.com)
3. Gives a public HTTPS URL accessible from a mobile phone
4. Fits a free / hobby account with no paid card required if possible

Constraints:
- Do NOT rewrite the trading strategy unless deploy is blocked.
- Do NOT require Binance API keys (public market data only).
- Do NOT commit secrets, .venv, or data/*.db.
- Prefer existing deploy files in the repo: Dockerfile, Procfile,
  render.yaml, fly.toml, railway.toml, koyeb.yaml, runtime.txt.
- App entrypoint: `python run.py` (binds HOST=0.0.0.0, PORT from env).
- Health check: GET /api/health
- Dashboard: GET /
- SQLite DB path: ./data/signals.db (create volume/disk if platform supports)
- Env FORCE_DEMO=0 for live market; only set FORCE_DEMO=1 if outbound
  Binance is blocked on that host.

Decision order for free host (try in this order, stop at first success):

1. **Fly.io** (best for always-on free allowance + volume for SQLite)
2. **Koyeb** free nano (always-on free instance)
3. **Render** free web service (works, but SLEEPS after ~15 min idle —
   only accept if you also set up a free external cron ping every 10 min)
4. **Railway** free trial credits (ok short-term)
5. **Google Cloud Run** free tier + min instances 0 (cold starts — last resort)
6. Avoid: Vercel/Netlify serverless (no long-lived scheduler),
   Cloudflare Workers (no APScheduler), GitHub Pages (static only),
   Replit free (flaky always-on), PythonAnywhere free (outbound whitelist
   may block Binance).

After deploy you MUST return:
- Public HTTPS URL (mobile-openable)
- Platform used + plan/tier
- Whether data mode is LIVE or DEMO (from /api/health)
- How to view logs
- How to force a scan: POST /api/scan
- Any free-tier limits / sleep behavior
- Exact commands you ran
```

---

## SECTION B — Task prompt (paste second)

```
Deploy Signal Desk from GitHub repo SaidRazak881/Trading-Signal.

GOAL
- One public HTTPS link I can open on my phone
- Live Binance market data if the host allows outbound HTTPS
- Background scheduler must keep running (scan every 15m, track every 20s)
- SQLite persisted if the platform supports a volume; otherwise document
  that history resets on restart

STEPS (execute, don't just advise)

1. Clone / pull the repo. Prefer branch arena/01a04e6d-trading-signal
   if main has no app code yet. Optionally merge to main first.

2. Read README.md, run.py, app/main.py, docs/DEPLOY.md, and existing
   deploy configs (Dockerfile, fly.toml, render.yaml, etc.).

3. Pick the best FREE platform using the decision order in your system
   role. Check that the account can be created free and that outbound
   HTTPS to https://api.binance.com/api/v3/ping works from that host.

4. Deploy using the matching config file already in the repo.
   Set environment:
     HOST=0.0.0.0
     FORCE_DEMO=0
     PORT=<platform-provided if any>
   Do not set Binance API keys.

5. If the platform sleeps free apps (e.g. Render):
   - Still deploy, AND
   - Configure a free uptime ping (cron-job.org or Better Stack free)
     to hit https://<app>/api/health every 10 minutes
   - Document that scans pause while sleeping if ping fails

6. If Binance is blocked on that host:
   - First try another region (Singapore `sin`, Tokyo `nrt`, Frankfurt `fra`)
   - If still blocked, set FORCE_DEMO=1 temporarily and report clearly
     that LIVE data is unavailable on this host

7. Verify:
     curl -s https://<url>/api/health
     curl -s https://<url>/api/stats
     curl -s -X POST https://<url>/api/scan
     curl -s https://<url>/api/signals/active
   Open / on a mobile user-agent mentally; confirm HTML 200.

8. If health shows demo:true after live deploy, diagnose network and
   fix region / host before accepting DEMO as final.

9. Write a short DEPLOY_RESULT.md in the repo (or PR comment) with:
   - URL
   - Platform
   - LIVE/DEMO
   - Region
   - Persist volume? yes/no
   - Sleep/ping setup
   - Follow-up commands

10. Push any necessary deploy fixes to the same working branch.
    Do not force-push. Do not rewrite git history.

SUCCESS CRITERIA
- [ ] HTTPS URL opens dashboard on phone
- [ ] /api/health returns status=ok
- [ ] data_mode is "live" (preferred) or clearly labeled "demo"
- [ ] POST /api/scan returns started and later signals appear
- [ ] No secrets committed
```

---

## SECTION C — Defaults if GPT asks questions

| Question | Answer |
|---|---|
| Which branch? | `arena/01a04e6d-trading-signal` (or merge it to `main` then deploy `main`) |
| Domain? | Use platform free subdomain (e.g. `*.fly.dev`, `*.onrender.com`) |
| Region? | Prefer **Singapore (`sin`)** then Tokyo, then US East |
| Custom domain? | Not now |
| Database? | Keep SQLite; mount volume at `/app/data` if possible |
| Redis / Postgres? | Not required for MVP |
| API keys? | None |
| FORCE_DEMO? | `0` unless Binance blocked |
| Budget? | **$0** — free tier only |
| Always-on required? | Yes, preferred (scanner every 15m) |
| Auth on dashboard? | Not required for MVP |
| Telegram alerts? | Out of scope for this deploy |
| Docker vs native? | Docker on Fly/Koyeb; native Python on Render/Railway is fine |
| Who owns cloud account? | User will log in / approve OAuth when browser needed; GPT prepares commands |

---

## SECTION D — Verification checklist (after GPT says “done”)

Open on your phone:

1. `https://<url>/` → Signal Desk UI loads, dark mobile layout
2. Header badge: **LIVE** (good) or **DEMO** (fallback)
3. Tap **⌁** (scan) → toast “Market scan started”
4. Within ~30–60s cards appear or “No active signals” with last scan meta
5. Tabs: Live / History / Stats all work
6. `https://<url>/api/health` → `{"status":"ok", ...}`
7. Leave open 20s → prices/stats refresh

If UI loads but always DEMO on a home network, the **server** cannot reach Binance — ask GPT to change region/platform, not your phone.

---

## SECTION E — One-block mega-prompt (optional single paste)

If the GPT chat only accepts one message, paste this:

```
You are a senior DevOps engineer. Deploy the crypto Signal Desk app from
GitHub repo https://github.com/SaidRazak881/Trading-Signal
(branch arena/01a04e6d-trading-signal) to a FREE host.

App facts:
- Python 3.11 FastAPI + Uvicorn + APScheduler + SQLite
- Start: python run.py (HOST=0.0.0.0, PORT from env)
- Health: GET /api/health
- UI: GET /  (mobile single-page)
- Needs outbound HTTPS to Binance public API
- No API keys
- Repo already has Dockerfile, Procfile, fly.toml, render.yaml,
  railway.toml, koyeb.yaml, runtime.txt

Free host preference (first success wins):
1) Fly.io always-on small VM + volume /app/data
2) Koyeb free nano
3) Render free + cron ping every 10m to /api/health
4) Railway trial
Avoid serverless (Vercel/Netlify/Workers) and GitHub Pages.

Do the deploy end-to-end. Set FORCE_DEMO=0. Prefer region Singapore.
Persist SQLite via volume if supported. Verify health, stats, force scan,
and that the public HTTPS URL works on mobile. Return URL, platform,
LIVE vs DEMO, logs command, and any sleep limits. Commit only necessary
deploy fixes; never commit .venv or secrets.
```

---

## SECTION F — What YOU (human) must prepare before GPT runs

Do these once — GPT cannot always create cloud accounts for you:

1. **GitHub**
   - Repo is public OR GPT’s token can read it
   - Branch with full app code is pushed
2. **Cloud account (pick one)**
   - [Fly.io](https://fly.io) → sign up with GitHub, install `flyctl` / use GPT terminal
   - OR [Koyeb](https://www.koyeb.com) → sign up with GitHub
   - OR [Render](https://render.com) → sign up with GitHub
3. **Billing**
   - Prefer platforms that allow free tier without card
   - Fly sometimes asks card for abuse prevention — use Koyeb/Render if you refuse card
4. **Permissions**
   - Give GPT (or the IDE agent) ability to run CLI: `flyctl`, `git`, `curl`
   - You approve browser OAuth / 2FA when prompted
5. **Do NOT give GPT**
   - Bank card numbers in chat
   - Password reuse
   - Binance withdrawal keys (not needed anyway)

---

## SECTION G — Expected final reply format from GPT

```
## Deploy result
- URL: https://….
- Platform: Fly.io / Koyeb / Render / …
- Plan: free
- Region: sin / …
- Data mode: LIVE | DEMO
- Volume: yes (/app/data) | no (ephemeral)
- Sleep: none | sleeps after 15m (ping: https://…)

## Verify
- /api/health → …
- active signals → N
- mobile UI → OK

## Ops
- Logs: <command>
- Force scan: curl -X POST https://…/api/scan
- Redeploy: <command>

## Limits / risks
- …
```

# DEPLOY_AGENT_GUIDE — Agent Runbook for Production Deploy

This file is written for AI coding agents executing or troubleshooting a Lyla / Taskbot production deploy. Humans should read [`AWS_DEPLOYMENT.md`](AWS_DEPLOYMENT.md) instead.

Operating assumptions:

- Topology = single EC2 + Caddy reverse proxy + uvicorn + SQLite. See `AWS_DEPLOYMENT.md` for diagram.
- Frontend and backend share one origin via Caddy. Cross-origin deploys are out of scope.
- All paths absolute. Use `/srv/lyla/...` on the host.

---

## Mandatory file-edit map

When the deploy task says "do X", touch ONLY these files. Do not invent new files.

| Goal | File | Edit |
|---|---|---|
| Change backend port | `frontend/vite.config.ts` (`BACKEND_TARGET`), systemd `ExecStart`, Caddy `reverse_proxy` | All three together. Default 8765. |
| Change backend public URL | `.env` (`BASE_URL`) | Must equal the URL Caddy serves. |
| Add an HTTP route to the proxy | `frontend/vite.config.ts` AND `frontend/vite.config.js` AND Caddy `@api` matcher | All three must list the new path prefix. |
| Allow another browser origin | `app/main.py` `CORSMiddleware.allow_origins` | Hardcoded list. Edit, do not introduce env-driven config without user confirmation. |
| Change auth password | `.env` (`DASHBOARD_PASSWORD_SCRYPT`) | Generate hash with `python -m scripts.hash_dashboard_password`. Empty value = fail-closed. |
| Toggle `Secure` cookie | `.env` (`COOKIE_SECURE`) | `true` for HTTPS production, `false` for plain `http://localhost`. |
| Toggle device token gate | `.env` (`REQUIRE_DEVICE_TOKEN`) | `true` for production. `false` only during local smoke. |
| Change agent mode | `.env` (`AGENT_MODE`, `GOOGLE_API_KEY`) | Empty `AGENT_MODE` = auto-pick. |
| Change DB path | `.env` (`DATABASE_URL`) | SQLite absolute path needs FOUR slashes: `sqlite:////srv/lyla/data/taskbot.db`. |
| Change scheduler | `.env` (`SCHEDULER_ENABLED`, `SCHEDULER_INTERVAL_SECONDS`) | Production = `true`. |

---

## Pre-deploy verification (run before any change)

Run all of the following on the dev machine. Refuse to proceed if any fail.

```bash
python -m pytest -q                                  # expect "310 passed" or current count
python -m alembic upgrade head                       # no exceptions
python -m alembic check                              # no pending migrations (if Alembic version supports)
( cd frontend && npm ci && npm run build )           # exit 0
findstr /R "8000" frontend\.env frontend\vite.config.ts  # no matches
findstr /R "localhost:8000\|127.0.0.1:8000" docs\ AGENTS.md  # no matches
```

If any of these fail, stop and surface the failure. Do not push a half-baked deploy.

---

## Deploy step contract

Each numbered step has: precondition, command, postcondition.

### Step 1 — Provision EC2

- **Precondition**: domain DNS `A` record points to the EC2 elastic IP. Verify with `dig +short <domain>`.
- **Command**: not automatable here. Treat as user-handled.
- **Postcondition**: `ssh ubuntu@<domain>` works.

### Step 2 — Install system packages

- **Precondition**: SSH works.
- **Commands**: see `AWS_DEPLOYMENT.md` §2 verbatim.
- **Postcondition**: `caddy version`, `python3.12 --version`, `node --version` all succeed.

### Step 3 — Clone + Python deps

- **Precondition**: `/srv/lyla` exists and is owned by `ubuntu`.
- **Commands**:
  ```bash
  cd /srv/lyla
  git clone <repo> app
  cd app && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
  ```
- **Postcondition**: `python -c "import fastapi, sqlalchemy, alembic"` succeeds.

### Step 4 — Configure `.env`

- **Precondition**: Step 3 done.
- **Mandatory writes**:
  - `APP_ENV=production`
  - `DATABASE_URL=sqlite:////srv/lyla/data/taskbot.db`
  - `COOKIE_SECURE=true`
  - `REQUIRE_DEVICE_TOKEN=true`
  - `BASE_URL=https://<domain>`
  - `DASHBOARD_PASSWORD_SCRYPT=<hash>` (generated)
- **Postcondition**: `python -c "from app.config import settings; print(settings.base_url)"` prints the domain.

### Step 5 — Migrate + seed

- **Precondition**: `.env` complete, `/srv/lyla/data` writable by `ubuntu`.
- **Commands**:
  ```bash
  python -m alembic upgrade head
  python -m scripts.seed_dev
  ```
- **Postcondition**: `/srv/lyla/data/taskbot.db` exists. `seed_dev` printed `user_id` and `device_id` UUIDs. **Save those for Step 7.**

### Step 6 — systemd service

- **Precondition**: Step 5 done.
- **File**: `/etc/systemd/system/lyla-backend.service` exactly as in `AWS_DEPLOYMENT.md` §4.
- **Commands**:
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable --now lyla-backend
  sleep 2
  curl -fsS http://127.0.0.1:8765/healthz
  ```
- **Postcondition**: `curl` returns 200 with `{"status":"ok"}`.

### Step 7 — Frontend build

- **Precondition**: Step 5 produced demo UUIDs.
- **Edit `frontend/.env`** before building:
  ```
  VITE_API_BASE_URL=
  VITE_DEMO_USER_ID=<from seed_dev>
  VITE_DEMO_DEVICE_ID=<from seed_dev>
  ```
- **Commands**: `cd frontend && npm ci && npm run build`
- **Postcondition**: `frontend/dist/index.html` exists.

### Step 8 — Caddy

- **Precondition**: Step 6 healthcheck passed, Step 7 build succeeded.
- **File**: `/etc/caddy/Caddyfile` exactly as in `AWS_DEPLOYMENT.md` §6, with the user's real domain.
- **Commands**:
  ```bash
  sudo systemctl reload caddy
  sleep 5
  curl -fsS https://<domain>/healthz
  ```
- **Postcondition**: 200 with `{"status":"ok"}` over HTTPS.

### Step 9 — Smoke test

- Login: `POST https://<domain>/auth/login` with `{username,password}` returns 200 + `Set-Cookie: lyla_session=...; Secure; HttpOnly; SameSite=Lax`.
- Devices list: `GET https://<domain>/devices` with the cookie returns 200 JSON.
- Pair endpoint reachable from browser dashboard.

---

## Troubleshooting decision tree

Match the symptom string from the user, then follow the FIRST matching branch.

### `connect: connection refused` to backend

1. `sudo systemctl status lyla-backend` — if not active, `journalctl -u lyla-backend -n 200`.
2. If active: `ss -tlnp | grep 8765` — confirm uvicorn is bound. If absent, restart service.
3. If bound: check Caddy config `reverse_proxy 127.0.0.1:8765` matches actual port.

### `502 Bad Gateway` from Caddy

Almost always uvicorn down or returning non-HTTP. Check `journalctl -u lyla-backend -n 200` for tracebacks. Common causes:

- `sqlite3.OperationalError: unable to open database file` → `/srv/lyla/data` not writable. `sudo chown -R ubuntu:ubuntu /srv/lyla/data`.
- `pydantic_settings.SettingsError` → missing required env var in `.env`. Compare against `.env.example`.
- `ModuleNotFoundError` → systemd `EnvironmentFile=` correct? venv path correct in `ExecStart=`?

### `caddy: error obtaining certificate`

DNS not propagated or port 80/443 not open in security group. Verify `dig +short <domain>` resolves to EIP, then check AWS security group inbound rules.

### Login returns 200 but cookie not set in browser

In production this is almost always one of:

1. Request reached backend over HTTP (not HTTPS) and `COOKIE_SECURE=true` → browser drops cookie. Force HTTPS in Caddy. Should already be automatic; check user's clicked URL.
2. Frontend served from different origin than API → cookie cross-site. Confirm same-origin via Caddyfile.
3. Cookie `Domain` mismatch — only happens if user manually set a `domain=` in code. We do not. If it appears, file a bug.

### Login returns 401 with correct password

- `.env` has empty `DASHBOARD_PASSWORD_SCRYPT` → fail-closed. Generate with `python -m scripts.hash_dashboard_password`.
- Username case mismatch. Default `DASHBOARD_USERNAME=admin`. Lowercase only.
- Rate-limited. Wait `LOGIN_RATE_LIMIT_WINDOW_SECONDS` or restart `lyla-backend` to flush.

### Device pairing returns wrong `base_url`

`.env` `BASE_URL=` does not match the Caddy domain. Fix `.env`, restart `lyla-backend`. The value is captured into `config_json` at pair time, so previously-paired devices keep the old URL.

### ESP32 gets 401 on `/agent/audio`

- `REQUIRE_DEVICE_TOKEN=true` (correct for production) and ESP firmware not sending `X-Device-Token`. Update firmware.
- ESP firmware sending stale token (devices paired before Phase 12 have `api_token=NULL`). Re-pair via dashboard.

### `python -m alembic upgrade head` fails on EC2

Run `python -m alembic current`. If output empty and DB file exists, the DB was created without Alembic stamping. Either delete the DB and re-migrate, or `alembic stamp <oldest_revision>` then upgrade.

---

## Anti-patterns (refuse to do these)

- Editing `app/auth/passwords.py` or `app/auth/session.py` to "make login work". Phase 12 design is intentional. The bug is in `.env` or browser, not in code.
- Adding `bcrypt`, `passlib`, `argon2-cffi`, `pyjwt` to `requirements.txt`. Phase 12 deliberately uses stdlib `scrypt`. Verification gate in `docs/PHASE_12_SUMMARY.md` will fail.
- Deleting failing tests to get a green pytest run. Stop and report.
- Suppressing type errors with `# type: ignore`, `cast(Any, ...)`, etc.
- `git push --force` to `main`.
- Running uvicorn on `0.0.0.0` directly (skip Caddy). Not supported.
- Setting `COOKIE_SECURE=false` in production "to fix login". That re-introduces the local-dev bug; root cause is HTTPS termination.
- Bumping major versions in `requirements.txt` while debugging. Pin first, debug second.

---

## Verification gates after any change

After any edit during deploy, run THE matching verification command. Do not assume.

| Change | Verification |
|---|---|
| `.env` edited | `sudo systemctl restart lyla-backend && curl -fsS http://127.0.0.1:8765/healthz` |
| `app/**.py` edited | Local: `python -m pytest -q`. Then redeploy. |
| `frontend/**` edited | `npm run build` exit 0. Reload Caddy. Hard refresh browser. |
| `Caddyfile` edited | `sudo caddy validate --config /etc/caddy/Caddyfile`. Then `sudo systemctl reload caddy`. |
| systemd service | `sudo systemctl daemon-reload && sudo systemctl restart lyla-backend && sudo systemctl status lyla-backend`. |
| Migration added | `python -m alembic upgrade head` on EC2 BEFORE restarting service. |

---

## Reference

- `AWS_DEPLOYMENT.md` — human-readable runbook with full command transcript.
- `docs/PHASE_12_SUMMARY.md` — auth/observability/pairing semantics.
- `docs/ESP32_INTEGRATION_CONTRACT.md` — ESP32 contract; deploy must keep this stable.
- `.env.example` — single source of truth for valid env keys.

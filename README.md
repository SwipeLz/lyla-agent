# Lyla / Taskbot

Bahasa Indonesia voice/text task assistant for students. Powered by FastAPI + Google ADK on the backend, a Vite + React + Tailwind dashboard on the frontend, and an ESP32-S3 BMO-style device for face/voice interaction.

This README is the localhost runbook. Production deployment lives in [`AWS_DEPLOYMENT.md`](AWS_DEPLOYMENT.md). Architecture and per-phase changelogs live in [`docs/`](docs/).

---

## TL;DR

```powershell
# Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m alembic upgrade head
python -m scripts.seed_dev
python -m scripts.hash_dashboard_password --password admin
# Paste the printed value into .env as DASHBOARD_PASSWORD_SCRYPT=<value>
uvicorn app.main:app --reload --port 8765

# Frontend (separate terminal)
cd frontend
copy .env.example .env
# Paste VITE_DEMO_USER_ID + VITE_DEMO_DEVICE_ID printed by seed_dev
npm install
npm run dev
```

Open <http://localhost:5173>, login with `admin` / `admin`.

Backend lives at `http://127.0.0.1:8765`. **Never use port 8000** — that's a stale value from older docs and will fail on Windows due to Hyper-V port reservations.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.14 | Earlier 3.12+ also works |
| Node.js | 20.x LTS | For Vite dev server |
| Git | any | Cloning + version control |
| Google API Key (optional) | — | Real Gemini agent / STT / TTS. Skip for fake/hermetic dev. |

---

## Backend setup

### 1. Create virtualenv + install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure `.env`

```powershell
copy .env.example .env
```

Open `.env` and check the local-dev critical settings:

```
COOKIE_SECURE=false        # MANDATORY for http://localhost. true causes login redirect loop.
REQUIRE_DEVICE_TOKEN=false # Easier for first-time smoke. Set true once paired.
AGENT_MODE=                # Empty = auto: real if GOOGLE_API_KEY set, else fake.
GOOGLE_API_KEY=            # Optional, only for real Gemini.
```

### 3. Migrate database + seed demo user

```powershell
python -m alembic upgrade head
python -m scripts.seed_dev
```

`seed_dev` prints UUIDs for the demo user (`demo@taskbot.local`) and the demo device (`TASKBOT-DEMO-001`). Save them — you need them in the frontend `.env`.

### 4. Generate dashboard password hash

```powershell
python -m scripts.hash_dashboard_password --password admin
```

Copy the printed `<salt_hex>:<hash_hex>` value into `.env` as:

```
DASHBOARD_PASSWORD_SCRYPT=<paste_value_here>
```

Empty value = fail-closed (every login returns 401).

### 5. Start backend

```powershell
uvicorn app.main:app --reload --port 8765
```

Smoke test:

```powershell
curl http://127.0.0.1:8765/healthz
```

Swagger UI: <http://localhost:8765/docs>

---

## Frontend setup

### 1. Configure `.env`

```powershell
cd frontend
copy .env.example .env
```

Fill in:

```
VITE_API_BASE_URL=        # LEAVE EMPTY in dev. The Vite proxy forwards everything.
VITE_DEMO_USER_ID=<uuid printed by seed_dev>
VITE_DEMO_DEVICE_ID=<uuid printed by seed_dev>
```

### 2. Install + run

```powershell
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/agent`, `/auth`, `/dashboard`, `/devices`, `/observability`, and `/healthz` to `http://127.0.0.1:8765` so the browser sees a single same-origin host.

### 3. Login

Use `DASHBOARD_USERNAME=admin` (default) plus the password you hashed. After login you should land on the dashboard.

---

## Pair the demo device (ESP32-S3 prep)

After login, go to **Devices → Pair New Device**, give it a name, and copy the printed `config_json`. Save it as `/sd/config.json` on the microSD card before powering the ESP. Detailed firmware runbook: [`firmware/README.md`](firmware/README.md).

---

## Common errors

### "Cannot reach backend at port 8000"

You are running an outdated version of the frontend or copied an old `.env`. The backend uses **port 8765**. Confirm with:

```powershell
findstr /R "8000" frontend\.env frontend\vite.config.ts
```

Both should be empty. The proxy target is hardcoded to `http://127.0.0.1:8765` in `frontend/vite.config.ts`.

### Login keeps redirecting to /login

Three known causes, in order of likelihood:

1. **`COOKIE_SECURE=true` over plain HTTP.** The browser silently drops a `Secure` cookie on `http://localhost`. Fix: set `COOKIE_SECURE=false` in `.env`, restart uvicorn, login again.
2. **`VITE_API_BASE_URL` set to a different origin.** When Vite serves `http://localhost:5173` and the API base is `http://127.0.0.1:8765`, the cookie becomes cross-site and the browser ignores it. Fix: leave `VITE_API_BASE_URL=` empty so the Vite proxy keeps everything same-origin.
3. **Stale cookie.** DevTools → Application → Cookies → delete `lyla_session`, refresh, login again.

### `WinError 10013` when starting uvicorn

Windows reserves port ranges silently (Hyper-V, Docker Desktop, antivirus). Pick a different free port and update `uvicorn --port` and `frontend/vite.config.ts` (`BACKEND_TARGET`).

### `DASHBOARD_PASSWORD_SCRYPT` empty → 401

Generate a hash with `python -m scripts.hash_dashboard_password` and paste the full `salt:hash` string into `.env`. The setting is fail-closed by design.

---

## Useful commands

```powershell
# Run a one-shot agent CLI call (no HTTP, no frontend)
python -m scripts.run_agent_text "catat tugas matematika besok jam 10" --user-id <uuid>

# Run the audio CLI (fake STT + TTS by default)
$env:TASKBOT_USER_ID = "<uuid>"
$env:TASKBOT_DEVICE_ID = "<uuid>"
python -m scripts.run_agent_audio path\to\sample.wav

# Tests
python -m pytest -q

# ADK Web UI (dev agent only, NOT production)
adk web --port 8000
```

---

## Project layout

```
app/                FastAPI backend (models, services, tools, agent, api)
frontend/           Vite + React + Tailwind dashboard
agents/             ADK Web dev agent (stub tools, prompt iteration only)
firmware/           ESP32-S3 BMO firmware (PlatformIO project)
scripts/            CLI tools (seed_dev, hash_dashboard_password, smoke tests)
docs/               Phase summaries + architecture + ESP integration contracts
.kiro/specs/        Normative specs (win over docs on conflict)
```

---

## Where to read next

- [`docs/PHASE_12_SUMMARY.md`](docs/PHASE_12_SUMMARY.md) — auth, observability, device pairing.
- [`docs/PHASE_13_SUMMARY.md`](docs/PHASE_13_SUMMARY.md) — frontend BMO redesign.
- [`docs/PHASE_11_ARCHITECTURE.md`](docs/PHASE_11_ARCHITECTURE.md) — frozen audio + directive contract.
- [`docs/phase-12/ESP_BRIEF.md`](docs/phase-12/ESP_BRIEF.md) — ESP32-S3 integration brief.
- [`firmware/README.md`](firmware/README.md) — firmware build + flash + SD-card runbook.
- [`AWS_DEPLOYMENT.md`](AWS_DEPLOYMENT.md) — production deployment runbook.

---

## License

Internal academic project. License TBD.

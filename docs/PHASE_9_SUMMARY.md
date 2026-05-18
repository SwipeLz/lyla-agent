# Phase 9 Summary — Dashboard Frontend

## Status

**Shipped and verified end-to-end.** Frontend SPA at `frontend/` builds clean (`npm run build`), runs against the live FastAPI backend, and passes a manual demo flow including `POST /agent/text` round-trips. Backend tests: **189 passed** in `python -m pytest -q`.

## What shipped

### Frontend (the headline deliverable)

- **Vite 5 + React 18 + TypeScript 5 + Tailwind 3** single-page app at `frontend/`. No Next.js, no SSR, no BFF, no server actions.
- **Five pages** mounted under React Router 6:
  - `/` Ringkasan — five `StatCard`s + `AgentCommandBox` + recent activity feed
  - `/tasks` Tugas — list with status filter, mark-done, delete
  - `/expenses` Pengeluaran — manual entry form + list
  - `/logs` Riwayat — voice command log feed
  - `/devices` Devices — registered devices snapshot
- **Reusable components:** `Layout`, `StatCard`, `LoadingState`, `ErrorState`, `SetupBanner`, `AgentCommandBox`, `TaskList`, `ExpenseList`, `VoiceLogList`, `DeviceList`.
- **Typed API client** (`frontend/src/lib/api.ts`) covering all nine backend endpoints used: summary, tasks (GET/PATCH/DELETE), expenses (GET/POST), logs, devices, agent/text.
- **Indonesian** copy for user-facing strings; English for code, types, and docs.

### Backend (small, integration-driven)

These changes were necessary to make the frontend actually work end-to-end — they are *not* new business logic.

- **CORS middleware** added in `app/main.py`. Allows `http://localhost:5173` and `http://127.0.0.1:5173` for dev. Frontend hits FastAPI directly on `127.0.0.1:8765`.
- **`os.environ["GOOGLE_API_KEY"]` bridge** in `app/agent/runtime.py` (`_run_real`). Pydantic-settings loads `.env` into the settings object but does NOT propagate to `os.environ`; ADK's Google SDK reads the env var directly. Bridge runs only in the real-agent path, after the mode dispatcher.
- **Fake agent shorthand parsing** in `app/agent/fake.py`. New `_parse_amount` helper handles three Indonesian conventions in priority order:
  1. **Shorthand** (`10k` / `10rb` / `10 ribu` → 10000; `10jt` / `10 juta` → 10000000)
  2. **Thousand-grouped** (`10.000` → 10000; `1.000.000` → 1000000 — titik = ribuan in ID locale)
  3. **Bare integer** (`20000` → 20000)
- **Real-agent prompt + tool docstring** updated in `app/agent/adk_agent.py` (`INSTRUCTION`) and `app/agent/tool_factory.py` (`create_expense.__doc__`) so Gemini converts shorthand client-side before calling the tool. ADK best-practice route per Google docs (instructions-first; tool docstrings inform argument selection).

### Docs and tooling

- `docs/FRONTEND_DASHBOARD.md` runbook (English).
- `docs/PHASE_9_SUMMARY.md` (this file).
- `README.md` and `docs/ROADMAP.md` updated.
- `.gitignore` extended to exclude `.venv/` and `venv/`.
- Project `.venv/` set up with all `requirements.txt` deps installed.

## Files added

```
frontend/.env.example
frontend/.gitignore
frontend/index.html
frontend/package.json
frontend/postcss.config.js
frontend/tailwind.config.js
frontend/tsconfig.json
frontend/tsconfig.node.json
frontend/vite.config.ts
frontend/src/App.tsx
frontend/src/index.css
frontend/src/main.tsx
frontend/src/vite-env.d.ts
frontend/src/lib/api.ts
frontend/src/lib/env.ts
frontend/src/lib/format.ts
frontend/src/lib/types.ts
frontend/src/components/AgentCommandBox.tsx
frontend/src/components/DeviceList.tsx
frontend/src/components/ErrorState.tsx
frontend/src/components/ExpenseList.tsx
frontend/src/components/Layout.tsx
frontend/src/components/LoadingState.tsx
frontend/src/components/SetupBanner.tsx
frontend/src/components/StatCard.tsx
frontend/src/components/TaskList.tsx
frontend/src/components/VoiceLogList.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/DevicesPage.tsx
frontend/src/pages/ExpensesPage.tsx
frontend/src/pages/LogsPage.tsx
frontend/src/pages/TasksPage.tsx
docs/FRONTEND_DASHBOARD.md
docs/PHASE_9_SUMMARY.md
```

## Files modified (backend integration work)

```
app/main.py                  # CORS middleware
app/agent/runtime.py         # GOOGLE_API_KEY env bridge
app/agent/fake.py            # _parse_amount helper for IDR shorthand
app/agent/adk_agent.py       # INSTRUCTION shorthand conversion rules
app/agent/tool_factory.py    # create_expense docstring strengthened
.gitignore                   # .venv/ + venv/
README.md                    # Phase 9 frontend section
docs/ROADMAP.md              # Phase 9 marked current; Phase 8.5 deferred
```

## Files explicitly NOT changed

- `app/services/**`, `app/tools/**`, `app/models/**`, `app/api/**` (except `main.py`) — business logic untouched.
- `app/schemas/**` — no schema changes; frontend types match exactly.
- `agents/taskbot_agent/**` — dev shell untouched.
- `alembic/**` — no new migrations.
- `requirements.txt` — no new Python deps.
- No new pytest tests; existing 189 still pass.

## How to run end-to-end

### One-time setup

```powershell
# From project root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m alembic upgrade head
python -m scripts.seed_dev
# Note the printed user_id and device_id

# Frontend
cd frontend
copy .env.example .env
# Edit .env: paste user_id into VITE_DEMO_USER_ID
#           paste device_id into VITE_DEMO_DEVICE_ID
npm install
```

Optional: to use real Gemini instead of the hermetic fake agent, edit project-root `.env`:

```
GOOGLE_API_KEY=AIzaSy...
GOOGLE_ADK_MODEL=gemini-2.5-flash
```

(Pick a model your API key actually has access to — `gemini-2.5-flash` is a known-good fallback.)

### Daily run

Two terminals.

```powershell
# Terminal 1 — backend (venv active)
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8765
```

```powershell
# Terminal 2 — frontend
cd frontend
npm run dev
```

Open <http://localhost:5173>.

### Demo smoke

On the Ringkasan page, type `catat makan siang 20000` (or `7k ayam`, or `bayar listrik 1.5jt`) into the **Agent Command Box** → click **Jalankan**. Expect: reply text, optional device-feedback card, collapsed actions JSON. Summary stat cards refresh automatically.

## Verification gate

| Gate | Command | Expected |
|---|---|---|
| Frontend type-check + bundle | `cd frontend && npm run build` | exit 0; `dist/index.html` produced; 53 modules transformed |
| Backend regression | `python -m pytest -q` | `189 passed` |
| Forbidden-deps audit | `findstr /R "next remix angular vue" frontend\package.json` | no matches |

## Known issues encountered (and resolved) during integration

These are documented for the next operator who hits the same friction.

1. **`WinError 10013` on uvicorn port 8000.** Windows reserves port ranges silently (Hyper-V, Docker Desktop, antivirus). Fix: use `--port 8765`. The frontend `.env` and `vite.config.ts` reference `127.0.0.1:8765`. Pick any free port if 8765 is also taken.
2. **CORS preflight 405 on every dashboard call.** Backend originally had no CORS middleware. Two fixes attempted: (a) Vite proxy with relative URLs — flaky, returned 404 even when backend route was correct (root cause never fully diagnosed; suspected Windows networking layer or path mangling between Vite 5 and uvicorn). (b) **CORS middleware on FastAPI + absolute URLs from frontend** — chosen, works reliably.
3. **`No API key was provided` after setting `GOOGLE_API_KEY` in `.env`.** Pydantic-settings loaded into the settings object but did not propagate to `os.environ`, which ADK's `google.genai` reads. Fixed in `runtime.py` `_run_real` (real-agent path only).
4. **Agent saying `Pengeluaran Rp10 tercatat` for input `10k`.** The fake agent's regex `\d+` grabbed `"10"` and dropped the suffix. Fixed by `_parse_amount` helper. The real-agent path is fixed via `INSTRUCTION` + tool docstring.

## Intentionally NOT in Phase 9

- Phase 8.5 backend smoke test (deferred per operator's direction).
- Audio capture, STT, TTS.
- Real WhatsApp Business API integration.
- ESP32 firmware.
- JWT/OAuth/session authentication; dashboard auth stays at MVP `none`.
- Next.js, Remix, Angular, Vue, SvelteKit.
- LangChain, OpenClaw, ESP-Claw, Dify, Flowise.
- Automated frontend tests (Vitest/Playwright). `npm run build` TypeScript type-check is the only automated gate.

## Caveats

- The Ringkasan stat cards "Tugas pending" and "Pengeluaran bulan ini" are derived **client-side** from `getTasks(userId, "pending")` and `getExpenses(userId)` filtered to current month (Asia/Jakarta), because `GET /dashboard/summary` only returns `tasks_due_today` and `total_expenses_today`. Adding more fields server-side was deliberately avoided to keep Phase 9 frontend-only.
- For production deployment, configure FastAPI `CORSMiddleware` for the actual production origin (or put both behind a reverse proxy on the same origin) and tighten `allow_origins` away from the dev defaults baked in here.
- Real-agent path requires `GOOGLE_API_KEY` in project-root `.env` AND a model name accessible by that key. Without `GOOGLE_API_KEY`, the runtime auto-resolves to fake mode — instant responses, regex-driven, no LLM cost.

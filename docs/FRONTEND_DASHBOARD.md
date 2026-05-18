# Frontend Dashboard (Phase 9)

This document is the runbook for the Taskbot dashboard SPA at `frontend/`.

## Overview

The dashboard is a single-page web app that consumes the FastAPI backend
shipped in Phase 4–8. It is a thin client: every business rule lives in
the backend; the SPA is responsible only for fetching data, rendering it,
and forwarding user actions to the API.

The SPA covers five pages:

- **Ringkasan** (`/`) — summary stat cards plus the Agent Command Box and
  recent voice command activity.
- **Tugas** (`/tasks`) — task list with status filter, mark-done and
  delete actions.
- **Pengeluaran** (`/expenses`) — manual expense entry form plus the
  full expense list.
- **Riwayat** (`/logs`) — voice command logs ordered most-recent-first.
- **Devices** (`/devices`) — registered devices snapshot.

## Tech stack

- Vite 5
- React 18
- TypeScript 5 (strict)
- Tailwind CSS 3
- React Router 6

No Next.js, no SSR, no server actions, no React Server Components, no
backend-for-frontend layer. The browser talks to FastAPI directly.

## Project layout

```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── .env.example
└── src/
    ├── main.tsx                # ReactDOM mount + BrowserRouter
    ├── App.tsx                 # Routes + setup gate
    ├── index.css               # Tailwind directives
    ├── vite-env.d.ts           # import.meta.env typings
    ├── lib/
    │   ├── env.ts              # VITE_* env reader + isReady()
    │   ├── types.ts            # TypeScript types matching backend
    │   ├── api.ts              # Typed fetch client
    │   └── format.ts           # Intl-based formatters
    ├── components/
    │   ├── Layout.tsx
    │   ├── StatCard.tsx
    │   ├── LoadingState.tsx
    │   ├── ErrorState.tsx
    │   ├── SetupBanner.tsx
    │   ├── AgentCommandBox.tsx
    │   ├── TaskList.tsx
    │   ├── ExpenseList.tsx
    │   ├── VoiceLogList.tsx
    │   └── DeviceList.tsx
    └── pages/
        ├── DashboardPage.tsx
        ├── TasksPage.tsx
        ├── ExpensesPage.tsx
        ├── LogsPage.tsx
        └── DevicesPage.tsx
```

## Environment variables

Copy `.env.example` to `.env` and fill in values from
`python -m scripts.seed_dev`.

| Key | Required | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | **yes** | Origin of FastAPI. Must match the port uvicorn was started with (e.g. `http://127.0.0.1:8765`). |
| `VITE_DEMO_USER_ID` | **yes** | UUID printed by seed script. SPA refuses to call the API until this is set. |
| `VITE_DEMO_DEVICE_ID` | optional | UUID for demo device. Without it, AgentCommandBox warns and skips device feedback. |
| `VITE_DASHBOARD_TOKEN` | optional | Set only when backend uses `DASHBOARD_AUTH_MODE=shared_header`. Sent as `X-Dashboard-Token` header. |

## Running locally

Backend first (in the project venv):

```bash
.\.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate    # Linux/macOS
python -m alembic upgrade head
python -m scripts.seed_dev
uvicorn app.main:app --reload --port 8765
```

Then the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The frontend issues calls directly to
`VITE_API_BASE_URL` (e.g. `http://127.0.0.1:8765`); FastAPI's
`CORSMiddleware` (registered in `app/main.py`) responds to preflight
requests so the dashboard works without a reverse proxy.

If port 8765 collides with something on your machine, pick another and
update both `uvicorn --port` and `VITE_API_BASE_URL` to match.

## Production build

```bash
cd frontend
npm run build
```

Output is written to `frontend/dist/`. Serve it with any static file
server. In production, tighten `app/main.py`'s `CORSMiddleware`
`allow_origins` to your real frontend origin (the dev defaults
`http://localhost:5173` and `http://127.0.0.1:5173` are not appropriate
for production), or put both frontend and backend behind a reverse
proxy on the same origin and drop the middleware entirely.

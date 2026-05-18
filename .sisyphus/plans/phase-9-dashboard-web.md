# Phase 9 — Dashboard Web (Vite + React + TypeScript + Tailwind)

## TL;DR

> **Quick Summary**: Build a lightweight Vite/React/TS/Tailwind SPA at `frontend/` that consumes the existing FastAPI backend. No Next.js, no SSR, no BFF. Single-page client only.
>
> **Deliverables**:
> - `frontend/` project: configs + `src/{lib,components,pages}/`
> - `docs/FRONTEND_DASHBOARD.md`, `docs/PHASE_9_SUMMARY.md`
> - Updated `README.md`, `docs/ROADMAP.md`
>
> **Estimated Effort**: Medium (one session of focused work)
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: Specs → frontend configs → lib (types/api) → components → pages → App wiring → build verify → docs

---

## Context

### Original Request

User wants Phase 9 (Dashboard Web). Phase 8.5 smoke test is intentionally deferred. Backend (Phase 4–8) is complete with 186/186 tests passing — must not be modified unless a confirmed incompatibility surfaces.

### Backend Inspection Findings (already read)

Endpoints confirmed in `app/api/agent.py` and `app/api/dashboard.py`:

| Endpoint | Method | Notes |
|---|---|---|
| `/agent/text` | POST | Body `{user_id, device_id?, text, timezone?}`. Empty text → 422. Unknown user/device → 404. Errors → 500. |
| `/dashboard/summary` | GET | `?user_id=`. Returns `{tasks_due_today, total_expenses_today}` ONLY (2 fields, not 4). |
| `/dashboard/tasks` | GET | `?user_id=&status=`. Optional status filter. |
| `/dashboard/tasks/{id}` | PATCH | Partial update, `model_dump(exclude_unset=True)`. |
| `/dashboard/tasks/{id}` | DELETE | Returns 204. |
| `/dashboard/expenses` | GET | `?user_id=&start_at=&end_at=`. Range optional. |
| `/dashboard/expenses` | POST | Body `{user_id, amount (int), category?, note?, spent_at?}`. Returns 201. |
| `/dashboard/logs` | GET | `?user_id=`. Ordered most-recent-first. |
| `/dashboard/devices` | GET | `?user_id=`. |

Schemas confirmed in `app/schemas/dashboard.py` and `app/schemas/agent.py`:
- All IDs are **string UUIDs** (Pydantic `str`), not int.
- `Expense.amount` is `int` rupiah.
- Datetimes are ISO 8601 timezone-aware.
- `VoiceCommandLog.parsed_actions` is `list[Any] | None`.
- `AgentTextResponse` is `{reply, actions: list[dict], device_feedback: dict | null}`.
- Auth: `DASHBOARD_AUTH_MODE=none` default; optional `X-Dashboard-Token` header when `shared_header`.

### Adaptation Notes (frontend-only, no backend changes)

- Summary endpoint only returns 2 fields. The "pending task count" and "total expenses this month" requested for the dashboard page are derived client-side from `getTasks(userId, "pending")` and `getExpenses(userId)` filtered to month-to-date.
- `device_id` lookup is by **id** (UUID), not `device_code`, when the agent endpoint validates existence.

### Metis Review

**Identified gaps and how they're addressed in this plan**:
- *What if backend uses port other than 8000?* — `VITE_API_BASE_URL` default but configurable.
- *What if `shared_header` auth is enabled later?* — API client supports an optional `X-Dashboard-Token` header read from `VITE_DASHBOARD_TOKEN` (added to `.env.example`).
- *Stack-trace leakage on errors?* — `ApiError` only carries `message` + `status`; backend already returns `{detail: string}` only.
- *Missing demo IDs UX?* — Setup banner per Requirement 3.2.
- *CORS?* — backend currently has no CORS middleware; document in `FRONTEND_DASHBOARD.md` as a likely first hiccup with fix instructions (FastAPI `CORSMiddleware`). This is a backend change BUT only if blocking; otherwise document the workaround (vite proxy).

**Decision on CORS**: Use **vite dev-server proxy** to avoid touching the backend. `vite.config.ts` proxies `/agent`, `/dashboard`, `/devices`, `/healthz` to `http://127.0.0.1:8000`. Production build users would need either CORS middleware or a reverse proxy — documented but not implemented.

---

## Work Objectives

### Core Objective

Deliver a working Vite/React/TS/Tailwind dashboard SPA that exercises every existing dashboard endpoint and the agent endpoint, ready for laptop/tablet demo.

### Concrete Deliverables

- `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/index.html`, `frontend/.env.example`, `frontend/.gitignore`
- `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`
- `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/format.ts`, `frontend/src/lib/env.ts`
- `frontend/src/components/Layout.tsx`, `StatCard.tsx`, `AgentCommandBox.tsx`, `TaskList.tsx`, `ExpenseList.tsx`, `VoiceLogList.tsx`, `DeviceList.tsx`, `LoadingState.tsx`, `ErrorState.tsx`, `SetupBanner.tsx`
- `frontend/src/pages/DashboardPage.tsx`, `TasksPage.tsx`, `ExpensesPage.tsx`, `LogsPage.tsx`, `DevicesPage.tsx`
- `docs/FRONTEND_DASHBOARD.md`, `docs/PHASE_9_SUMMARY.md`
- `README.md` (updated), `docs/ROADMAP.md` (updated)

### Definition of Done

- [ ] `cd frontend && npm install` succeeds
- [ ] `cd frontend && npm run build` produces `frontend/dist/` with no TypeScript errors
- [ ] `cd frontend && npm run dev` serves on http://localhost:5173 with all 5 pages reachable
- [ ] With backend running + demo seeded + `.env` configured, dashboard shows real data
- [ ] AgentCommandBox sends `"catat makan siang 20000"` → backend returns reply + actions; UI refreshes summary
- [ ] `python -m pytest -q` still reports 186 passed (no backend changes)
- [ ] No `next`/`@remix-run/*`/`@angular/*`/`vue` in `frontend/package.json`
- [ ] `git diff --stat` of backend code (`app/`, `agents/`, `alembic/`, `requirements.txt`) is empty

### Must Have

- Vite + React 18 + TypeScript 5 + Tailwind 3
- Typed API client in `frontend/src/lib/api.ts`
- Five pages: Dashboard, Tasks, Expenses, Logs, Devices
- AgentCommandBox with refresh callback
- Responsive layout (laptop + tablet)
- Indonesian error message when backend unreachable

### Must NOT Have (Guardrails)

- `next` package or any Next.js artifact (`pages/_app.tsx`, `app/layout.tsx`, etc.)
- Server-side rendering, server actions, or React Server Components
- Backend-for-frontend layer (no Node middleware proxying API)
- Hardcoded UUIDs in `.tsx`/`.ts` source files
- New backend endpoints, new Pydantic schemas, new service methods
- Audio/STT/TTS code
- Real WhatsApp integration
- JWT/OAuth/session auth
- LangChain, OpenClaw, ESP-Claw, Dify, Flowise
- ESP32 firmware
- Heavy date library (use `Intl.DateTimeFormat` and native `Date`)
- State libraries beyond what React provides (no Redux, MobX, Zustand)
- Routing libraries beyond `react-router-dom@6` (the only allowed extra)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** for build verification. Manual demo verification is acknowledged but not blocking for spec sign-off.

### Test Decision

- **Infrastructure exists**: NO (no frontend test harness)
- **Automated tests**: NONE — Phase 9 is demo-ready frontend; tests deferred unless explicitly requested
- **Framework**: N/A
- **Build verification**: `npm run build` (TypeScript type-check + Vite bundle) is the gate

### QA Policy

Every task that produces source files MUST pass `npm run build` after the task. Final integration QA: launch dev server, exercise each page, run agent command, verify refresh.

- **Frontend/UI**: Manual smoke via `npm run dev` against running backend with seeded data; screenshots optional.
- **API client**: Compile-time type safety via `tsc --noEmit` (run by `vite build`).

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — must complete first):
├── Task 1: Frontend configs (package.json, vite.config.ts, tsconfig*.json, tailwind, postcss, index.html, .env.example, .gitignore)
├── Task 2: Frontend configs (package.json, vite.config.ts, tsconfig*.json, tailwind, postcss, index.html, .env.example, .gitignore)
└── Task 3: index.css + Tailwind directives

Wave 2 (lib — types first, then API + format + env helpers):
├── Task 4: src/lib/types.ts                  (depends on Task 1 schemas summary)
├── Task 5: src/lib/env.ts                    (depends on Task 2 .env.example)
├── Task 6: src/lib/format.ts                 (independent)
└── Task 7: src/lib/api.ts                    (depends on Task 4)

Wave 3 (components + pages — heavy parallel):
├── Task 8:  src/components/LoadingState.tsx + ErrorState.tsx + SetupBanner.tsx
├── Task 9:  src/components/StatCard.tsx
├── Task 10: src/components/Layout.tsx
├── Task 11: src/components/AgentCommandBox.tsx (depends on Task 7)
├── Task 12: src/components/TaskList.tsx        (depends on Task 4, 7)
├── Task 13: src/components/ExpenseList.tsx     (depends on Task 4, 7)
├── Task 14: src/components/VoiceLogList.tsx    (depends on Task 4, 7)
└── Task 15: src/components/DeviceList.tsx      (depends on Task 4, 7)

Wave 4 (pages — depends on Wave 3 components):
├── Task 16: src/pages/DashboardPage.tsx
├── Task 17: src/pages/TasksPage.tsx
├── Task 18: src/pages/ExpensesPage.tsx
├── Task 19: src/pages/LogsPage.tsx
└── Task 20: src/pages/DevicesPage.tsx

Wave 5 (App wiring + verify + docs):
├── Task 21: src/App.tsx + src/main.tsx
├── Task 22: npm install + npm run build verification
├── Task 23: docs/FRONTEND_DASHBOARD.md
├── Task 24: docs/PHASE_9_SUMMARY.md
└── Task 25: README.md + docs/ROADMAP.md updates

Critical Path: 1 → 2 → 4 → 7 → 11/16 → 21 → 22
Parallel Speedup: ~50% faster than sequential (Waves 3 & 4 run 5–8 in parallel)
```

### Agent Dispatch Summary

- Wave 1: Task 1 → `writing`, Tasks 2–3 → `quick`
- Wave 2: Tasks 4–7 → `quick`
- Wave 3: Tasks 8–15 → `visual-engineering`
- Wave 4: Tasks 16–20 → `visual-engineering`
- Wave 5: Task 21 → `quick`, Task 22 → `unspecified-high` (build + verify), Tasks 23–25 → `writing`

---

## TODOs

- [ ] 1. Frontend project scaffolding (configs)

  **What to do**:
  - `frontend/package.json` — name `lyla-dashboard`, private, scripts `dev`/`build`/`preview`, deps: `react@^18.3`, `react-dom@^18.3`, `react-router-dom@^6.26`; devDeps: `vite@^5`, `@vitejs/plugin-react@^4`, `typescript@^5.5`, `@types/react`, `@types/react-dom`, `tailwindcss@^3.4`, `postcss@^8`, `autoprefixer@^10`.
  - `frontend/vite.config.ts` — React plugin + dev-server proxy to backend (`/agent`, `/dashboard`, `/devices`, `/healthz` → `http://127.0.0.1:8000`).
  - `frontend/tsconfig.json` — strict, ESNext, jsx react-jsx, moduleResolution bundler, paths for `@/*`.
  - `frontend/tsconfig.node.json` — for `vite.config.ts`.
  - `frontend/tailwind.config.js` — content `./index.html`, `./src/**/*.{ts,tsx}`.
  - `frontend/postcss.config.js` — tailwind + autoprefixer.
  - `frontend/index.html` — root `<div id="root">` + `<script type="module" src="/src/main.tsx">`.
  - `frontend/.env.example` — `VITE_API_BASE_URL=http://127.0.0.1:8000`, `VITE_DEMO_USER_ID=`, `VITE_DEMO_DEVICE_ID=`, `VITE_DASHBOARD_TOKEN=` (empty).
  - `frontend/.gitignore` — `node_modules/`, `dist/`, `.env`, `.env.local`.

  **Must NOT do**:
  - Do not pin `next`, `remix`, `vue`, `@angular/*`.
  - Do not add `redux`, `mobx`, `zustand`, `react-query`/`@tanstack/react-query`.
  - Do not include any UUID literal.

  **Recommended Agent Profile**: `quick`.

  **Parallelization**: Wave 1, blocks: 4–25.

  **Acceptance Criteria**:
  - [ ] `cd frontend && npm install` exits 0
  - [ ] `node -e "JSON.parse(require('fs').readFileSync('frontend/package.json'))"` parses
  - [ ] No forbidden dep present

- [ ] 2. Tailwind base CSS

  **What to do**:
  - `frontend/src/index.css` — Tailwind directives `@tailwind base; @tailwind components; @tailwind utilities;` plus a small `:root` block with neutral CSS vars and a `body { @apply bg-slate-50 text-slate-900 antialiased; }`.

  **Must NOT do**: No third-party CSS framework imports.

  **Recommended Agent Profile**: `quick`.

  **Parallelization**: Wave 1, parallel to 2.

  **Acceptance Criteria**: file exists and is imported by `main.tsx` (verified in Task 20).

- [ ] 3. `src/lib/types.ts` — TypeScript types matching backend

  **What to do**:
  - Define: `ApiError` (class with `message: string`, `status: number`).
  - `DeviceFeedback` = `{ success: boolean; type: "device_command"; command?: { face?: string; sound?: string; text?: string } } | Record<string, unknown>` (loose to match `dict | None`).
  - `AgentTextRequest = { user_id: string; device_id?: string; text: string; timezone?: string }`.
  - `AgentTextResponse = { reply: string; actions: Array<Record<string, unknown>>; device_feedback: DeviceFeedback | null }`.
  - `DashboardSummary = { tasks_due_today: number; total_expenses_today: number }` (only 2 fields, mirrors `SummaryOut`).
  - `Task = { id: string; user_id: string; title: string; course: string | null; status: string; priority: string | null; deadline_at: string | null; reminder_at: string | null; created_at: string }`.
  - `TaskPatchInput = Partial<Pick<Task, "status" | "title" | "course" | "deadline_at" | "reminder_at" | "priority">>`.
  - `Expense = { id: string; user_id: string; amount: number; category: string | null; note: string | null; spent_at: string; created_at: string }`.
  - `ExpenseCreateInput = { user_id: string; amount: number; category?: string | null; note?: string | null; spent_at?: string | null }`.
  - `VoiceCommandLog = { id: string; user_id: string | null; device_id: string | null; input_text: string; parsed_actions: Array<Record<string, unknown>> | null; response_text: string | null; status: string; created_at: string }`.
  - `Device = { id: string; user_id: string; device_code: string; status: string; last_seen_at: string | null; created_at: string }`.

  **Must NOT do**: no `any`. Use `Record<string, unknown>` or `unknown` for free-form payloads.

  **Recommended Agent Profile**: `quick`.

  **References**: `app/schemas/dashboard.py`, `app/schemas/agent.py`.

  **Acceptance Criteria**: `tsc --noEmit` clean (verified by Task 21 build).

- [ ] 4. `src/lib/env.ts` — typed env reader + setup-status helper

  **What to do**:
  - Export `API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").trim()`.
  - Export `DEMO_USER_ID = (import.meta.env.VITE_DEMO_USER_ID ?? "").trim() || null`.
  - Export `DEMO_DEVICE_ID = (import.meta.env.VITE_DEMO_DEVICE_ID ?? "").trim() || null`.
  - Export `DASHBOARD_TOKEN = (import.meta.env.VITE_DASHBOARD_TOKEN ?? "").trim() || null`.
  - Export `isReady(): { ok: true } | { ok: false; reason: string }` — returns ok only if `DEMO_USER_ID` is set.
  - Add ambient typing for `import.meta.env` in `src/vite-env.d.ts` (or include in `env.ts` via interface merge).

  **Must NOT do**: no `process.env` references (this is a browser app).

  **Recommended Agent Profile**: `quick`.

  **Parallelization**: Wave 2, parallel to Tasks 3, 5, 6.

- [ ] 5. `src/lib/format.ts` — display helpers

  **What to do**:
  - `formatCurrencyIDR(value: number): string` → uses `Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 })`. Returns "—" for `null`/`NaN`.
  - `formatDateTime(iso: string | null | undefined): string` → uses `Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Jakarta" })`. Returns "—" for null.
  - `formatDate(iso: string | null | undefined): string` → date only, same locale.
  - `formatStatus(value: string | null | undefined): string` → returns capitalized version, "—" for null.

  **Must NOT do**: no `dayjs`/`date-fns`/`moment` imports.

  **Recommended Agent Profile**: `quick`.

  **Parallelization**: Wave 2, parallel.

- [ ] 6. `src/lib/api.ts` — typed API client

  **What to do**:
  - Import `ApiError`, types from `./types`, `API_BASE_URL` and `DASHBOARD_TOKEN` from `./env`.
  - Internal `request<T>(path, init?)`:
    1. Call `fetch(API_BASE_URL + path, { ...init, headers: { "Content-Type": "application/json", ...(DASHBOARD_TOKEN ? { "X-Dashboard-Token": DASHBOARD_TOKEN } : {}), ...(init?.headers ?? {}) } })`.
    2. On `TypeError` (network failure) throw `new ApiError("Backend tidak dapat dihubungi. Pastikan FastAPI berjalan di " + API_BASE_URL, 0)`.
    3. If `!res.ok`: try parse `{ detail: string }`, throw `new ApiError(detail || res.statusText, res.status)`.
    4. If `res.status === 204` return `undefined as T`.
    5. Else `return await res.json() as T`.
  - Public:
    - `getSummary(userId: string): Promise<DashboardSummary>` → `request("/dashboard/summary?user_id=" + encodeURIComponent(userId))`.
    - `getTasks(userId: string, status?: string): Promise<Task[]>` → `?user_id=...&status=...`.
    - `updateTask(taskId: string, patch: TaskPatchInput): Promise<Task>` → PATCH `/dashboard/tasks/${taskId}` with JSON body.
    - `deleteTask(taskId: string): Promise<void>` → DELETE.
    - `getExpenses(userId: string): Promise<Expense[]>`.
    - `createExpense(input: ExpenseCreateInput): Promise<Expense>` → POST.
    - `getLogs(userId: string): Promise<VoiceCommandLog[]>`.
    - `getDevices(userId: string): Promise<Device[]>`.
    - `runAgentText(payload: AgentTextRequest): Promise<AgentTextResponse>` → POST `/agent/text`.

  **Must NOT do**: no `axios`, no `react-query`. Plain `fetch`.

  **Recommended Agent Profile**: `quick`.

  **References**: `app/api/dashboard.py`, `app/api/agent.py` for status codes and query params.

  **Acceptance Criteria**: `tsc --noEmit` clean.

- [ ] 7. `src/components/LoadingState.tsx` + `ErrorState.tsx` + `SetupBanner.tsx`

  **What to do**:
  - `LoadingState` — small skeleton/spinner: a `div` with Tailwind `animate-pulse` and a configurable `label` prop (default "Memuat data…").
  - `ErrorState` — receives `error: ApiError | Error` prop; displays `error.message` in a red banner; if `status === 0` (network failure) emphasize the FastAPI base URL hint.
  - `SetupBanner` — receives `reason: string`; displays Indonesian instructions to set `VITE_DEMO_USER_ID` in `.env`, run `python -m scripts.seed_dev`, and copy the printed UUID.

  **Must NOT do**: no inline `<style>` tags; Tailwind only.

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 3, parallel to 8–13.

  **Acceptance Criteria**: components render without props errors; build passes.

- [ ] 8. `src/components/StatCard.tsx`

  **What to do**:
  - Props: `{ label: string; value: string | number; hint?: string; tone?: "neutral" | "warn" | "good" }`.
  - Render: a `<div>` with `rounded-lg border border-slate-200 bg-white p-4 shadow-sm`; large value in `text-2xl font-semibold`; small label in `text-xs uppercase tracking-wide text-slate-500`; optional hint in `text-xs text-slate-400`.
  - Tone modifier adjusts border or value color (warn → amber, good → emerald, neutral → slate).

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 3.

- [ ] 9. `src/components/Layout.tsx`

  **What to do**:
  - Receives `{ children: ReactNode }`.
  - Sidebar (left, fixed on `md+`) with brand "Taskbot Dashboard" and `<NavLink>` entries pointing to `/`, `/tasks`, `/expenses`, `/logs`, `/devices`. Active state via Tailwind `aria-[current=page]:` or NavLink's className callback.
  - Top bar showing the current `DEMO_USER_ID` (truncated) and a small env-status pill (green if `isReady().ok`, red otherwise).
  - Main content area: `<main class="flex-1 p-6">{children}</main>`.
  - Mobile: stack — top bar with hamburger, sidebar collapses to a `<details>` or simple top horizontal scroll nav (keep it simple, no animation).

  **Must NOT do**: no client-side state libs. Local `useState` only.

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 3.

- [ ] 10. `src/components/AgentCommandBox.tsx`

  **What to do**:
  - Props: `{ onSuccess?: () => void }`.
  - Local state: `text: string`, `loading: boolean`, `result: AgentTextResponse | null`, `error: ApiError | null`.
  - Reads `DEMO_USER_ID` and `DEMO_DEVICE_ID` from `lib/env`.
  - Renders: `<textarea>` (rows=2) for command, submit button "Jalankan", optional "Bersihkan" reset button.
  - If `DEMO_DEVICE_ID` is null, show a small amber notice: "Device tidak diset; perintah device tidak akan dipantulkan."
  - On submit: validate text not empty; call `runAgentText({ user_id: DEMO_USER_ID!, device_id: DEMO_DEVICE_ID ?? undefined, text, timezone: "Asia/Jakarta" })`. On success set `result`, call `onSuccess?.()`. On error set `error`.
  - Display `result.reply` in a card. If `result.device_feedback` present, render `face/sound/text` fields prominently. Render `result.actions` as a collapsed `<details>` with formatted JSON (`JSON.stringify(actions, null, 2)`).

  **Must NOT do**: do not call `runAgentText` if `DEMO_USER_ID` is null (let `SetupBanner` upstream handle that).

  **Recommended Agent Profile**: `visual-engineering`.

  **References**: `app/api/agent.py` for response shape, `app/agent/runtime.py` for `device_feedback` semantics.

  **Acceptance Criteria**: build passes; manual smoke shows reply + refresh on success.

- [ ] 11. `src/components/TaskList.tsx`

  **What to do**:
  - Props: `{ tasks: Task[]; onUpdate?: (t: Task) => void; onDelete?: (id: string) => void }`.
  - Renders a `<table>` (md+) and stacked cards (mobile) with columns: title, course, status (pill), priority, deadline_at (formatDateTime), reminder_at (formatDateTime).
  - Inline actions per row: "Tandai selesai" (calls `onUpdate` after `updateTask(t.id, { status: "done" })`), "Hapus" (calls `onDelete` after `deleteTask(t.id)`). Buttons disabled while their own request is in flight.
  - Use `formatStatus` for status badge color: pending→amber, done→emerald, others→slate.
  - Empty state: "Belum ada tugas."

  **Must NOT do**: do not perform business filtering here (filter is the page's job).

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 3.

- [ ] 12. `src/components/ExpenseList.tsx`

  **What to do**:
  - Props: `{ expenses: Expense[] }`.
  - Renders a list with: amount (formatCurrencyIDR), category, note (truncated), spent_at (formatDateTime).
  - Empty state: "Belum ada pengeluaran."

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 3.

- [ ] 13. `src/components/VoiceLogList.tsx`

  **What to do**:
  - Props: `{ logs: VoiceCommandLog[] }`.
  - Each row: `created_at` (formatDateTime), `input_text`, status pill (success→emerald, error→red, others→slate), `response_text` (truncated, expandable via `<details>`), `parsed_actions` collapsed in `<details><pre>JSON.stringify(...)</pre></details>`.
  - Empty state: "Belum ada riwayat perintah."

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 3.

- [ ] 14. `src/components/DeviceList.tsx`

  **What to do**:
  - Props: `{ devices: Device[] }`.
  - Each row: `device_code` (mono font), `status` pill, `last_seen_at` (formatDateTime, "—" if null), `created_at`.
  - Empty state: "Belum ada device terdaftar."

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 3.

- [ ] 15. `src/pages/DashboardPage.tsx`

  **What to do**:
  - On mount, fetch in parallel via `Promise.all`: `getSummary`, `getTasks(userId, "pending")`, `getExpenses(userId)`, `getLogs(userId)`, `getDevices(userId)`. Use a `refreshKey` `useState` to allow `AgentCommandBox.onSuccess` to bump and refetch.
  - Compute client-side: `monthExpenses` = sum of expenses where `spent_at` is in the current month (Asia/Jakarta).
  - Render five `StatCard` components:
    - "Tugas pending" → tasks length
    - "Tugas jatuh tempo hari ini" → `summary.tasks_due_today`
    - "Pengeluaran hari ini" → `formatCurrencyIDR(summary.total_expenses_today)`
    - "Pengeluaran bulan ini" → `formatCurrencyIDR(monthExpenses)`
    - "Device aktif" → devices length
  - Below cards: AgentCommandBox (with `onSuccess={() => setRefreshKey(k => k+1)}`).
  - Then: "Aktivitas terkini" — VoiceLogList sliced to top 5.
  - Loading state: `LoadingState`. Error: `ErrorState`. If `!isReady().ok`: `SetupBanner`.

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 4.

- [ ] 16. `src/pages/TasksPage.tsx`

  **What to do**:
  - Optional `<select>` filter for status (`""`, `"pending"`, `"done"`, `"in_progress"`).
  - On filter change refetch via `getTasks(userId, status || undefined)`.
  - Use TaskList component. `onUpdate`: optimistic update via local state replace; on error revert. `onDelete`: optimistic remove + revert.
  - Refresh button.

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 4.

- [ ] 17. `src/pages/ExpensesPage.tsx`

  **What to do**:
  - Inline form: amount (number input, min=1), category (text), note (textarea), spent_at (datetime-local; convert to ISO before submit).
  - On submit: `createExpense({ user_id: DEMO_USER_ID!, amount, category, note, spent_at })`. On success append to local list; reset form.
  - Below form: ExpenseList.
  - Refresh button.

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 4.

- [ ] 18. `src/pages/LogsPage.tsx`

  **What to do**:
  - Fetch `getLogs(userId)`; render VoiceLogList.
  - Refresh button.

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 4.

- [ ] 19. `src/pages/DevicesPage.tsx`

  **What to do**:
  - Fetch `getDevices(userId)`; render DeviceList.
  - Banner explaining ESP32 firmware integration is deferred.
  - Refresh button.

  **Recommended Agent Profile**: `visual-engineering`.

  **Parallelization**: Wave 4.

- [ ] 20. `src/App.tsx` + `src/main.tsx` — routing and bootstrap

  **What to do**:
  - `main.tsx`: import `./index.css`; render `<BrowserRouter><App /></BrowserRouter>` into `#root` via `ReactDOM.createRoot`.
  - `App.tsx`: top-level Layout wrapping `<Routes>` with five `<Route>`: `/` → `DashboardPage`, `/tasks` → `TasksPage`, `/expenses` → `ExpensesPage`, `/logs` → `LogsPage`, `/devices` → `DevicesPage`. Add a fallback `*` route showing a small "Halaman tidak ditemukan" message with a link back to `/`.
  - At the very top of `App.tsx`, check `isReady()`. If not ok, render `<SetupBanner reason={...} />` instead of routing — so the user is forced to fix `.env` first.

  **Recommended Agent Profile**: `quick`.

  **Parallelization**: Wave 5.

  **Acceptance Criteria**: build passes; dev server starts; navigation works.

- [ ] 21. Build verification

  **What to do**:
  - `cd frontend && npm install` (first time)
  - `cd frontend && npm run build`
  - Verify exit code 0 and `frontend/dist/index.html` exists.
  - If TypeScript errors surface, fix at the source (don't add `// @ts-ignore`).

  **Recommended Agent Profile**: `unspecified-high`.

  **Parallelization**: Wave 5, blocks 22.

  **QA Scenarios**:
  ```
  Scenario: build succeeds with no TS errors
    Tool: Bash
    Steps:
      1. cd frontend
      2. npm install
      3. npm run build
    Expected: exit 0, "✓ built in" message, dist/index.html present
    Evidence: terminal log

  Scenario: forbidden deps absent
    Tool: Bash (findstr or grep)
    Steps:
      1. findstr /R "next remix angular vue" frontend\package.json
    Expected: no matches
  ```

- [ ] 22. `docs/FRONTEND_DASHBOARD.md`

  **What to do**:
  - English. Sections: Overview, Tech stack, Project layout, `.env` keys (table), Running dev server, Building for production, How the API client works, How AgentCommandBox works, CORS notes (vite proxy in dev; for prod, suggest reverse proxy or FastAPI `CORSMiddleware` snippet — explicitly noting this is **out of scope for Phase 9** and only mentioned for operators), Troubleshooting (common errors).

  **Recommended Agent Profile**: `writing`.

  **Parallelization**: Wave 5, parallel to 23–24.

- [ ] 23. `docs/PHASE_9_SUMMARY.md`

  **What to do**:
  - English. What shipped, files added, files updated, file count totals, what is intentionally NOT in this phase (Next.js, audio, WhatsApp, JWT, ESP firmware, smoke test deferred), how to run end-to-end, screenshots placeholder.

  **Recommended Agent Profile**: `writing`.

- [ ] 24. Update `README.md` and `docs/ROADMAP.md`

  **What to do**:
  - `README.md`: add a "Frontend Dashboard (Phase 9)" section. Include backend run commands, then frontend run commands, then `.env` configuration. Mention "uses Vite + React + TypeScript, NOT Next.js". Mention dashboard auth is MVP/none.
  - `docs/ROADMAP.md`: mark Phase 9 as `(Current)` if appropriate, or shipped; note Phase 8.5 deferred.

  **Recommended Agent Profile**: `writing`.

  **Parallelization**: Wave 5.

---

## Final Verification Wave

- [ ] F1. **Plan compliance audit** — verify every "Must Have" item is present in `frontend/`, every "Must NOT Have" item is absent (grep `frontend/package.json` for forbidden deps; grep `frontend/src/` for hardcoded UUIDs).
- [ ] F2. **Build verification** — `cd frontend && npm install && npm run build` exits 0; `frontend/dist/index.html` exists.
- [ ] F3. **Backend regression** — `python -m pytest -q` reports 186 passed.
- [ ] F4. **Manual demo smoke** — start backend (`uvicorn app.main:app --reload`) + frontend (`npm run dev`); navigate all 5 pages; submit `"catat makan siang 20000"` via AgentCommandBox; verify reply renders and dashboard summary updates.

## Commit Strategy

One commit per wave to keep diffs reviewable. Suggested messages:
- `phase-9: scaffold frontend project (Vite + React + TS + Tailwind)`
- `phase-9: implement API client, types, format helpers`
- `phase-9: implement reusable components and AgentCommandBox`
- `phase-9: implement five dashboard pages and App wiring`
- `phase-9: add frontend docs and update README + ROADMAP`

## Success Criteria

### Verification Commands

```bash
# Frontend build (compile-time type check + bundle)
cd frontend && npm install && npm run build

# Backend regression
python -m pytest -q
# Expected: 186 passed

# Forbidden-deps audit
findstr /R "next remix angular vue " frontend\package.json
# Expected: no matches

# Hardcoded UUID audit
findstr /R /S "[a-f0-9]\{8\}-[a-f0-9]\{4\}" frontend\src
# Expected: no matches except in comments
```

### Final Checklist

- [ ] All 25 tasks complete
- [ ] Build passes
- [ ] Backend tests still 186/186
- [ ] No forbidden dependencies
- [ ] No hardcoded secrets/IDs
- [ ] Demo runs end-to-end

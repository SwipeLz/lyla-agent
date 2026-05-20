# Phase 13 — Frontend BMO Redesign + Phase 12 UI Integration

## TL;DR

> Visual + functional overhaul `frontend/`. BMO mascot identity. Tambah landing/login/observability page + device pair modal. Wire ke Phase 12 backend endpoints (auth + observability + pair).
>
> **Deliverables**:
> - 2 halaman publik baru (`/`, `/login`)
> - 1 halaman authenticated baru (`/app/observability`)
> - 5 halaman dashboard existing direpaint dengan BMO theme
> - 1 modal pair device baru di `/app/devices`
> - 8 BMO design components di `frontend/src/components/bmo/`
> - Tailwind config extended dengan BMO palette
> - AuthGuard / PublicGuard router wrappers
> - API client refactor: cookie auth (drop `X-Dashboard-Token`)
> - BMO face SVG dipindah ke `frontend/public/bmo/`
>
> **Estimated Effort**: 14–18 jam
> **Parallel Execution**: 4 waves
> **Critical Path**: tokens → BMO components → AuthGuard → page redesign → observability

---

## Context

### Original Request

User minta "Lakukan analisis terhadap semua fitur dan struktur website saya lalu buatkan landing page dan halaman login serta dashboard kemudian page yang diperlukan sesuai dengan struktur website saya. buat design brief dan plan untuk saya konfirmasi nantinya untuk dieksekusi." dengan referensi `design_brief/bmo_design_reference.html` + `design_brief/bmo_face/*.svg`.

### References

- Brief: [`docs/phase-13/FRONTEND_BRIEF.md`](../../docs/phase-13/FRONTEND_BRIEF.md)
- BMO reference: `design_brief/bmo_design_reference.html`
- BMO faces: `design_brief/bmo_face/*.svg` (9 expressions)
- Backend API yang akan dikonsumsi:
  - Phase 9: `/dashboard/*`, `/agent/text`
  - Phase 12: `/auth/{login,logout,me}`, `/observability/{trace,recent,stats,devices}`, `POST /devices/pair`

### Inspection Findings (already known)

| File | Status | Action |
|---|---|---|
| `frontend/src/App.tsx` | exists, 5 routes | refactor to nested `/` public + `/app/*` private |
| `frontend/src/components/Layout.tsx` | sidebar layout | replace with top navbar (BMO style) |
| `frontend/src/lib/api.ts` | uses `X-Dashboard-Token` | switch to `credentials: 'include'`, add observability + auth + pair endpoints |
| `frontend/src/lib/types.ts` | covers Phase 9 types | extend with auth + observability + device pair types |
| `frontend/src/lib/env.ts` | requires `VITE_DEMO_USER_ID` | drop `VITE_DASHBOARD_TOKEN`, keep demo user IDs untuk `/agent/text` payload |
| `frontend/src/index.css` | Tailwind base | add BMO font + body bg |
| `frontend/tailwind.config.js` | Tailwind defaults | extend palette + shadow |
| `app/main.py` CORS | `allow_credentials=False` | flip ke `True`, narrow origins |

### Decisions Locked

| Decision | Choice | Rationale |
|---|---|---|
| Stack | Vite + React + TS + Tailwind (existing) | no rewrite; keep momentum |
| Router | React Router v6 nested routes | already installed |
| Auth client | cookie-based, `credentials: 'include'` | matches Phase 12 server contract |
| AuthGuard impl | wrapper component, `GET /auth/me` on mount | simple, no new dep |
| Observability live tail | `setInterval` 3s polling | brief explicitly states no WebSocket |
| Drill-down UI | side drawer (slide-in from right) | better than modal for log inspection |
| BMO face delivery | static SVG di `public/bmo/`, dipanggil via `<img>` | no SVG-as-component build complexity |
| Color tokens | extend Tailwind config (not CSS vars) | less indirection, autocomplete works |
| Font | keep Inter, add JetBrains Mono untuk code/token | minimal asset weight |
| Empty state | `<EmptyState>` reusable, BMO face + caption | brief design system pattern |
| Mobile breakpoints | 375 / 768 / 1024 / 1440 | brief Pre-Delivery checklist |
| Test framework | none (manual QA) | brief Out of Scope; cuma `npm run build` gate |

---

## Work Objectives

### Core Objective

Frontend yang visually BMO + functionally selaras Phase 12 backend, sehingga operator/demo viewer bisa: (a) lihat landing yang menjelaskan Taskbot dalam 5 detik, (b) login lewat dashboard, (c) pair device baru lewat UI, (d) drill-down request audio yang fail untuk diagnose layer.

### Concrete Deliverables

- `frontend/public/bmo/{idle,happy,sad,excited,dizzy,rage,shock,crying,very_sad}_face.svg`
- `frontend/tailwind.config.js` — palette + shadow + font extension
- `frontend/src/components/bmo/` — 8 reusable components (Mascot, Face, Card, Button, Badge, Input, EmptyState, ErrorState)
- `frontend/src/components/auth/{AuthGuard,PublicGuard,UserMenu}.tsx`
- `frontend/src/components/landing/{HeroSection,FeatureCard,HowItWorksStep,FaqAccordion,PublicNavbar,PublicFooter}.tsx`
- `frontend/src/components/devices/{DeviceCard,PairDeviceModal}.tsx`
- `frontend/src/components/observability/{ObsStatsBar,LiveTailTable,TraceDrawer,DeviceStatusGrid,StageTimingBar}.tsx`
- `frontend/src/components/AppNavbar.tsx` (replaces sidebar Layout)
- `frontend/src/pages/{LandingPage,LoginPage,ObservabilityPage}.tsx` (NEW)
- `frontend/src/pages/{DashboardPage,TasksPage,ExpensesPage,LogsPage,DevicesPage}.tsx` (REDESIGN)
- `frontend/src/lib/api.ts` (REFACTOR auth + new endpoints)
- `frontend/src/lib/types.ts` (extend)
- `frontend/src/lib/env.ts` (cleanup `DASHBOARD_TOKEN`)
- `frontend/src/App.tsx` (nested routes)
- `frontend/src/index.css` (font + body bg)
- `app/main.py` CORS adjustment (1-line change, separate task)
- `docs/PHASE_13_SUMMARY.md` (post-implementation)
- `docs/ROADMAP.md` (Phase 13 marker)

### Definition of Done

- [ ] `cd frontend; npm install; npm run build` exit 0, zero TS errors
- [ ] Landing page render `/` dengan BMO hero
- [ ] Login form berhasil POST `/auth/login`, redirect `/app` on success
- [ ] AuthGuard redirect `/app/*` → `/login` saat tanpa cookie
- [ ] PublicGuard redirect `/login` → `/app` saat sudah login
- [ ] Logout button POST `/auth/logout`, clear cookie, redirect `/`
- [ ] Pair Device modal di `/app/devices` POST `/devices/pair`, tampilkan config_json + copy button
- [ ] `/app/observability` polling `/observability/recent` setiap 3s
- [ ] Drill-down drawer query `/observability/trace/{log_id}` saat row click
- [ ] Stats bar di observability render p50/p95/p99 dari `/observability/stats?window=1h`
- [ ] Device grid di observability render `/observability/devices` dengan online indicator
- [ ] BMO face SVG muncul di ≥5 titik (hero, login, empty state, observability log row, device card)
- [ ] Semua copy Indonesian; cursor-pointer di interactive; focus ring visible
- [ ] Backend regression: `python -m pytest -q` masih 310 passed (CORS change shouldn't affect tests)

### Must Have

- BMO color palette terapan ke seluruh UI (8 token kunci)
- BMO face SVG dipakai sebagai mascot di minimal 5 titik
- Auth flow end-to-end (login → guarded routes → logout)
- Pair device flow lengkap dengan config_json copy
- Observability live tail + drill-down drawer + device grid
- Mobile responsive (375 / 768 / 1024 / 1440)
- Accessibility minimum: cursor-pointer, focus ring, alt text, label
- Tidak break existing dashboard pages

### Must NOT Have (Guardrails)

- No Next.js / SSR / Remix migration
- No new component library (no shadcn/ui, no Radix, no Headless UI)
- No state management library (Redux/Zustand) — `useState` + Context cukup
- No WebSocket — HTTP polling only
- No dark mode toggle (deferred)
- No frontend test framework (manual QA)
- No PWA / service worker
- No i18n switcher
- No animation library (Framer Motion, etc.) — Tailwind transitions only
- No icon library beyond Heroicons SVG inline (matches `/skill ui-ux-pro-max` rules)
- No emoji as icon (UI-UX rules section)
- No backend changes selain CORS adjustment 1 baris

---

## Verification Strategy

### Test Decision

- **Infrastructure exists**: NO frontend test framework (out of scope per brief)
- **Automated tests**: NONE
- **Build verification**: `npm run build` (TS + Vite bundle)
- **Backend regression**: `python -m pytest -q` masih 310 passed setelah CORS change

### QA Policy

Manual QA per page using BMO Pre-Delivery Checklist:

- Visual: BMO face muncul, palette match, no emoji icon, hover stable
- Interaction: cursor-pointer, hover feedback, smooth transition 200ms
- Light mode contrast: text 4.5:1, border visible
- Layout: floating navbar spacing, no horizontal scroll mobile
- Auth: login success/fail, guard redirect both directions
- Observability: polling jalan, drawer open/close, polling pause saat drawer open

Manual smoke per task akan ditulis explicit di Acceptance section per TODO.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — must complete first):
├── Task 1: Tailwind config extension (palette, font, shadow)
├── Task 2: Move BMO SVG assets to frontend/public/bmo/
├── Task 3: Update lib/types.ts (auth + observability + pair types)
├── Task 4: Update lib/env.ts (drop DASHBOARD_TOKEN)
└── Task 5: Update lib/api.ts (cookie auth + new endpoints)

Wave 2 (Components — independent, parallel):
├── Task 6: BMO base components (Mascot, Face, Card, Button, Badge, Input)
├── Task 7: BMO state components (EmptyState, ErrorState)
├── Task 8: Auth components (AuthGuard, PublicGuard, UserMenu)
├── Task 9: Landing components (Hero, FeatureCard, HowItWorks, FAQ, Navbar, Footer)
├── Task 10: AppNavbar (top navbar untuk /app/*)
├── Task 11: Devices components (DeviceCard, PairDeviceModal)
└── Task 12: Observability components (StatsBar, LiveTailTable, TraceDrawer, DeviceGrid, StageTimingBar)

Wave 3 (Pages — uses Wave 2 components):
├── Task 13: LandingPage
├── Task 14: LoginPage
├── Task 15: ObservabilityPage
├── Task 16: DashboardPage redesign
├── Task 17: TasksPage redesign
├── Task 18: ExpensesPage redesign
├── Task 19: LogsPage redesign
└── Task 20: DevicesPage redesign + pair modal wiring

Wave 4 (Wiring + verification):
├── Task 21: App.tsx nested routes + guard wiring
├── Task 22: index.css update (font, body bg)
├── Task 23: Backend CORS adjustment (allow_credentials=True)
├── Task 24: npm run build verification
├── Task 25: Manual QA checklist execution
└── Task 26: docs/PHASE_13_SUMMARY.md + ROADMAP update
```

### Critical Path

Task 1 → 5 → 6 → 8 → 21 → 24

### Agent Dispatch Summary

- Wave 1: Tasks 1-5 → `quick`
- Wave 2: Tasks 6-12 → `visual-engineering` (UI components)
- Wave 3: Tasks 13-20 → `visual-engineering` (page composition)
- Wave 4: Tasks 21-26 → mixed (`quick` for wiring, `writing` for docs)

---

## TODOs

- [ ] 1. Tailwind config extension

  **What to do**:
  - Edit `frontend/tailwind.config.js` (or `.ts` if migrated)
  - Extend `theme.extend.colors` dengan token BMO dari brief tabel:
    - `bmo: { body: '#9FD5B1', screen: '#C5E3BF', mouth: '#1F8941', dark: '#1C4B3B', yellow: '#F7E72F', blue: '#313F98', 'blue-light': '#C8CFFF', cyan: '#77CFDB', red: '#ED306A', purple: '#b297c7', 'screen-dark': '#0D1B2A' }`
    - `surface: { DEFAULT: '#F8FAF6', elev: '#FFFFFF' }`
    - `border: { DEFAULT: '#D1E0CC' }`
  - Extend `theme.extend.fontFamily.mono` dengan `['JetBrains Mono', 'ui-monospace', 'monospace']`
  - Extend `theme.extend.boxShadow.bmo` dengan `'-2px 2px 0 2px #639975'`

  **Must NOT do**: jangan ganti font sans default; jangan introduce CSS variables lapis dua.

  **References**:
  - `design_brief/bmo_design_reference.html:11-21` (palette swatches)
  - `docs/phase-13/FRONTEND_BRIEF.md` Design Tokens section

  **Acceptance**:
  - `grep "bmo-dark" frontend/tailwind.config.js` finds match
  - `npm run build` exit 0

- [ ] 2. Move BMO SVG assets

  **What to do**:
  - Buat folder `frontend/public/bmo/`
  - Copy 9 file dari `design_brief/bmo_face/*.svg` ke `frontend/public/bmo/`
  - Verify file sizes match (sanity check)

  **Must NOT do**: jangan modifikasi SVG content; jangan inline kan SVG ke React component (akses via path).

  **Acceptance**:
  - 9 file ada di `frontend/public/bmo/`
  - Bisa diakses via URL `/bmo/idle_face.svg` saat dev server running

- [ ] 3. lib/types.ts extension

  **What to do**:
  - Tambah types berikut:
    - `LoginRequest { username: string; password: string }`
    - `MeResponse { username: string; expires_at: string }`
    - `DevicePairRequest { name: string }`
    - `DevicePairResponse { device_id, device_code, api_token, config_json: Record<string, unknown> }`
    - `StageTimings { validate?, stt?, agent?, classify?, tts? }`
    - `RequestTrace` (mirror Pydantic schema dari `app/schemas/observability.py`)
    - `RecentLogSummary { id, device_id, created_at, audio_code?, status, total_ms? }`
    - `StatsResponse { count, success_count, error_count, p50_ms?, p95_ms?, p99_ms?, top_audio_codes: Array<{code: string, count: number}> }`
    - `DeviceStatusOut { id, device_code, name, status, is_online, last_seen_at?, firmware_version?, wifi_rssi_dbm?, battery_pct?, free_heap_bytes? }`
  - Extend existing `Device` type dengan optional telemetry fields (firmware_version, wifi_rssi_dbm, battery_pct, free_heap_bytes)

  **References**:
  - `app/schemas/observability.py`
  - `app/schemas/auth.py`
  - `app/schemas/devices.py`

  **Acceptance**:
  - `tsc --noEmit` clean
  - Semua schema field nullable sesuai backend

- [ ] 4. lib/env.ts cleanup

  **What to do**:
  - Hapus `DASHBOARD_TOKEN` constant + export
  - Hapus referensi `VITE_DASHBOARD_TOKEN`
  - Tetap pertahankan `DEMO_USER_ID`, `DEMO_DEVICE_ID`, `API_BASE_URL`, `isReady`
  - Tambah komentar bahwa demo IDs masih dipakai untuk `/agent/text` payload sampai backend resolve user dari session

  **Must NOT do**: jangan hapus `isReady()` — masih dipakai existing pages.

  **Acceptance**:
  - `grep DASHBOARD_TOKEN frontend/src` no matches
  - `npm run build` exit 0

- [ ] 5. lib/api.ts refactor

  **What to do**:
  - Hapus `buildHeaders` `X-Dashboard-Token` injection
  - Tambah `credentials: 'include'` ke setiap `fetch` call
  - Tambah handler 401: kalau path bukan `/auth/*`, throw `AuthRequiredError` (new class) yang akan ditangkap oleh AuthGuard
  - Tambah endpoints baru:
    - `login(payload: LoginRequest): Promise<MeResponse>`
    - `logout(): Promise<void>`
    - `me(): Promise<MeResponse>`
    - `pairDevice(payload: DevicePairRequest): Promise<DevicePairResponse>`
    - `getRecent(params?: {limit?, device_id?, status?}): Promise<RecentLogSummary[]>`
    - `getTrace(log_id: string): Promise<RequestTrace>`
    - `getStats(window?: '1h'|'24h'|'7d'): Promise<StatsResponse>`
    - `getObsDevices(): Promise<DeviceStatusOut[]>`

  **Must NOT do**: jangan break existing endpoints (`getSummary`, `getTasks`, dst); ubah hanya credentials + 401 handling.

  **Acceptance**:
  - `npm run build` exit 0
  - `grep credentials frontend/src/lib/api.ts` matches semua fetch call
  - 9 endpoint baru exported

- [ ] 6. BMO base components

  **What to do**: Buat `frontend/src/components/bmo/`:
  - `BmoMascot.tsx` — props `size?: 28|48|80`. Render mascot dari design_brief HTML lines 91-194 (body + face + disc + buttons). Hardcode CSS-in-Tailwind dengan absolute positioning. Default 80.
  - `BmoFace.tsx` — props `expression: 'idle'|'happy'|'sad'|'excited'|'dizzy'|'rage'|'shock'|'crying'|'very_sad'`, `size?: number`. Render `<img src={\`/bmo/${expression}_face.svg\`} alt={\`BMO ${expression}\`} />` dengan width/height.
  - `BmoCard.tsx` — props `variant?: 'default'|'success'|'info'|'warning'|'error'`, `children`. Border + bg per variant token.
  - `BmoButton.tsx` — props `variant: 'primary'|'secondary'|'accent'|'destructive'`, `size?: 'sm'|'md'`, standard HTML button props. Match design_brief lines 48-77 button styles.
  - `BmoBadge.tsx` — props `tone: 'online'|'idle'|'syncing'|'offline'|'success'|'error'`, `children`. Match design_brief badge classes.
  - `BmoInput.tsx` — props extend HTML input. Match design_brief lines 79-89 input style. Include focus ring.

  **Must NOT do**: jangan import icon library; jangan animate (statis dulu); jangan emoji.

  **References**:
  - `design_brief/bmo_design_reference.html:91-194` (mascot CSS)
  - `design_brief/bmo_design_reference.html:36-77` (badge + button)

  **Acceptance**:
  - 6 file created, each `export function BmoXxx`
  - `npm run build` exit 0

- [ ] 7. BMO state components

  **What to do**: Buat di `frontend/src/components/bmo/`:
  - `EmptyState.tsx` — props `face?: BmoExpression = 'idle'`, `title: string`, `description?: string`, `cta?: ReactNode`. Centered layout dengan BMO 80px + heading + body + optional CTA.
  - `ErrorState.tsx` — props `face?: BmoExpression = 'sad'`, `error: Error`, `onRetry?: () => void`. Replace existing `frontend/src/components/ErrorState.tsx` (consolidate). Show error message + retry button.

  **Must NOT do**: jangan duplikat existing `ErrorState.tsx` — replace it. Existing usages should still work (props compat).

  **References**:
  - `frontend/src/components/ErrorState.tsx` (existing — check current props)
  - `frontend/src/components/LoadingState.tsx` (style reference for spacing)

  **Acceptance**:
  - 2 file created
  - Existing imports `from "../components/ErrorState"` masih kompat
  - `npm run build` exit 0

- [ ] 8. Auth components

  **What to do**: Buat `frontend/src/components/auth/`:
  - `AuthGuard.tsx` — wrapper. On mount: call `api.me()`. While loading: spinner. On 200: render `children` + provide user via `<UserContext.Provider>`. On 401/error: `<Navigate to="/login" replace />`.
  - `PublicGuard.tsx` — inverse. On mount: call `api.me()`. On 200: `<Navigate to="/app" replace />`. On 401: render `children` (login form).
  - `UserMenu.tsx` — dropdown trigger + menu. Trigger: username text + chevron. Menu items: "Logout" (calls `api.logout()` then redirect `/`).
  - `UserContext.ts` — `createContext<MeResponse | null>(null)` + `useUser()` hook with null-check throw.

  **Must NOT do**: jangan implement remember-me; jangan persist user di localStorage (cookie sudah handle).

  **References**:
  - `app/api/auth.py` — endpoint contracts
  - React Router v6 `<Navigate>` docs

  **Acceptance**:
  - 4 file created
  - AuthGuard properly redirects without cookie
  - `npm run build` exit 0

- [ ] 9. Landing components

  **What to do**: Buat `frontend/src/components/landing/`:
  - `PublicNavbar.tsx` — top navbar untuk public pages. BMO mini logo (28px) kiri, links "Fitur" "FAQ" tengah, button "Login" + "Coba demo" kanan. Sticky top.
  - `HeroSection.tsx` — split layout: BMO mascot 80px kiri (atau atas di mobile), heading "Asisten suara untuk pelajar Indonesia." + tagline + 2 CTA button kanan.
  - `FeatureCard.tsx` — props `icon: ReactNode`, `title: string`, `description: string`. 3 cards akan dipakai di LandingPage: Tugas / Pengeluaran / Reminder.
  - `HowItWorksStep.tsx` — props `step: number`, `expression: BmoExpression`, `title`, `description`. 4 steps: idle → record → happy → speaking.
  - `FaqAccordion.tsx` — props `items: Array<{q: string, a: string}>`. Native `<details>` for accessibility.
  - `PublicFooter.tsx` — copyright + GitHub link + email. "Dibuat untuk skripsi".

  **Must NOT do**: jangan pakai gradient background; jangan pakai animation library (CSS transition saja).

  **References**:
  - `docs/phase-13/FRONTEND_BRIEF.md` Page 1 wireframe
  - `design_brief/bmo_design_reference.html` palette

  **Acceptance**:
  - 6 file created
  - Each component standalone testable in isolation
  - `npm run build` exit 0

- [ ] 10. AppNavbar

  **What to do**: Buat `frontend/src/components/AppNavbar.tsx`:
  - Top horizontal bar (replace existing sidebar Layout).
  - Left: BMO mini-logo + "Taskbot" wordmark.
  - Center: NavLinks ke `/app` `/app/tasks` `/app/expenses` `/app/logs` `/app/devices` `/app/observability`. Active state: underline `bmo-body`.
  - Right: `<UserMenu />`.
  - Mobile: collapse links jadi hamburger menu (existing Layout pattern).
  - Use `bmo-dark` background, `bmo-screen` text.

  **References**:
  - `design_brief/bmo_design_reference.html:197-209` (navbar style)
  - `frontend/src/components/Layout.tsx` (existing pattern to replace)

  **Acceptance**:
  - File created
  - Active link highlighted on current route
  - Mobile hamburger works
  - `npm run build` exit 0

- [ ] 11. Devices components

  **What to do**: Buat `frontend/src/components/devices/`:
  - `DeviceCard.tsx` — props `device: DeviceStatusOut | Device`. Card dengan BMO mascot 48px kiri, info kanan (name, device_code, badge online/offline, firmware/RSSI/battery jika ada). Match design_brief lines 408-430.
  - `PairDeviceModal.tsx` — props `open: boolean`, `onClose: () => void`. Internal state: `name`, `loading`, `result?: DevicePairResponse`, `error?`. Form input nama → POST `/devices/pair` → tampilkan config_json di `<textarea readonly>` + tombol "Salin" (Clipboard API). ESC + click outside close. Focus trap dasar.

  **Must NOT do**: jangan implement rotate-token (backend tidak punya); jangan generate config_json di frontend.

  **References**:
  - `design_brief/bmo_design_reference.html:408-430` (device card)
  - `docs/phase-13/FRONTEND_BRIEF.md` Page 8 wireframe

  **Acceptance**:
  - 2 file created
  - Modal aria-modal + role=dialog
  - Copy button works (manual test)
  - `npm run build` exit 0

- [ ] 12. Observability components

  **What to do**: Buat `frontend/src/components/observability/`:
  - `ObsStatsBar.tsx` — props `stats: StatsResponse`. 4 stat cards horizontal: requests count, p95 latency, success rate %, top audio_code. Use `<StatCard>` existing pattern.
  - `LiveTailTable.tsx` — props `rows: RecentLogSummary[]`, `onRowClick: (id: string) => void`, `polling: boolean`. Table dengan kolom time/device/audio_code/status/total_ms/stt/agent. Click row → onRowClick. Highlight selected row. Indicator polling ON di header.
  - `TraceDrawer.tsx` — props `logId: string | null`, `onClose: () => void`. Slide-in dari kanan. Fetch `/observability/trace/{logId}` saat logId berubah. Render `<StageTimingBar />`, transcript, reply, parsed_actions JSON, client telemetry, error block. BMO face in header sesuai status (happy/sad/dizzy).
  - `StageTimingBar.tsx` — props `timings: StageTimings`. Horizontal stacked bar 5 segments: validate / stt / agent / classify / tts. Width proporsional total. Tooltip per segment.
  - `DeviceStatusGrid.tsx` — props `devices: DeviceStatusOut[]`. Grid responsif. Per device: `<DeviceCard>` dari Task 11 + telemetry detail.

  **Must NOT do**: jangan import chart library; jangan WebSocket; jangan virtual scroll (data kecil <200 rows).

  **References**:
  - `app/schemas/observability.py` — schema contracts
  - `docs/phase-13/FRONTEND_BRIEF.md` Page 9 wireframe

  **Acceptance**:
  - 5 file created
  - Polling ON/OFF state visible
  - Drawer open/close smooth
  - `npm run build` exit 0

- [ ] 13. LandingPage

  **What to do**: Buat `frontend/src/pages/LandingPage.tsx`:
  - Compose: `<PublicNavbar />`, `<HeroSection />`, 3 `<FeatureCard />`, 4 `<HowItWorksStep />`, `<FaqAccordion />`, `<PublicFooter />`.
  - Background: `bg-surface` dengan accent `bmo-purple` di hero section.
  - 3 features: "Catat tugas", "Pantau pengeluaran", "Reminder otomatis".
  - 4 how-it-works steps: "Tekan tombol" (idle) → "Bicara" (excited) → "Backend memproses" (idle) → "BMO menjawab" (happy).
  - FAQ items: 4 pertanyaan ("Apakah perlu hardware?", "Bisa offline?", "Bahasa apa?", "Berapa harganya?").

  **References**:
  - `docs/phase-13/FRONTEND_BRIEF.md` Page 1
  - Wave 2 components

  **Acceptance**:
  - Page render at `/`
  - Mobile responsive (test 375px)
  - All CTAs link ke `/login`

- [ ] 14. LoginPage

  **What to do**: Buat `frontend/src/pages/LoginPage.tsx`:
  - Centered card 400px max-width
  - BMO mascot 80px di top, swap expression based on form state:
    - idle: default
    - happy: success (before redirect)
    - sad: 401 error
    - dizzy: 429 rate-limit error
  - Form: username + password inputs, "Masuk" button
  - Hint text: "Default: admin/admin (kontak admin untuk credentials)"
  - On submit: `api.login({username, password})` → on success: `<Navigate to="/app" />`. On error: tampilkan error message + swap face.
  - Disable submit button while loading
  - "← Kembali ke beranda" link top-left

  **References**:
  - `app/api/auth.py` — login endpoint
  - `docs/phase-13/FRONTEND_BRIEF.md` Page 2

  **Acceptance**:
  - Successful login redirects ke `/app`
  - 401 shows BMO sad
  - 429 shows BMO dizzy + cooldown message
  - Empty form: button disabled

- [ ] 15. ObservabilityPage

  **What to do**: Buat `frontend/src/pages/ObservabilityPage.tsx`:
  - State: `selectedLogId`, `polling` (default true), data states untuk recent/stats/devices.
  - Mount: fetch initial recent + stats + devices.
  - `useEffect` polling: `setInterval(3000)` re-fetch recent + stats while `polling && !selectedLogId`. Pause saat drawer open. Pause saat `document.hidden`.
  - Layout vertikal:
    - Top: `<ObsStatsBar />`
    - Middle: `<LiveTailTable rows={recent} onRowClick={setSelectedLogId} polling={polling} />`
    - Bottom: `<DeviceStatusGrid devices={devices} />`
  - Drawer: `<TraceDrawer logId={selectedLogId} onClose={() => setSelectedLogId(null)} />` slide-in dari kanan.
  - Toggle button "Pause / Resume" untuk control polling.
  - Loading + error states pakai `<LoadingState />` + `<ErrorState />`.

  **References**:
  - `app/api/observability.py` — endpoint contracts
  - `docs/phase-13/FRONTEND_BRIEF.md` Page 9 wireframe

  **Acceptance**:
  - Polling visible dengan indicator
  - Drawer open/close smoothly
  - No infinite re-render (verify via React DevTools profiler)
  - Polling pauses saat tab background (test by switching tab)

- [ ] 16. DashboardPage redesign

  **What to do**: Edit `frontend/src/pages/DashboardPage.tsx`:
  - Keep all existing data fetching logic intact (`Promise.all` + Snapshot type)
  - Replace 5 `<StatCard>` dengan BMO-themed variant: gunakan `bmo-screen` background, `bmo-dark` text, format mengikuti `design_brief/bmo_design_reference.html` lines 386-404.
  - AgentCommandBox: tetap functional, tapi tambah `<BmoFace expression>` di kanan box yang react ke result state (idle saat awal, excited saat loading, happy saat success, sad saat error).
  - Header: ganti sizing pakai BMO H1 (28px, weight 500, `bmo-dark`).
  - Empty state recent logs: pakai `<EmptyState face="idle">` "Belum ada aktivitas hari ini."

  **Must NOT do**: jangan ubah API call signature atau Snapshot type — backend tidak berubah.

  **References**: existing `frontend/src/pages/DashboardPage.tsx`, `frontend/src/components/AgentCommandBox.tsx`.

  **Acceptance**:
  - Page render at `/app`
  - All 5 stat cards visible dengan BMO color
  - Agent command box BMO face swap on state change
  - `npm run build` exit 0

- [ ] 17. TasksPage redesign

  **What to do**: Edit `frontend/src/pages/TasksPage.tsx` + `frontend/src/components/TaskList.tsx`:
  - Keep existing CRUD logic.
  - Header H1 BMO style.
  - Filter chips status (pending / done) pakai `<BmoBadge>`.
  - Empty state: `<EmptyState face="idle" title="Belum ada tugas" description="Coba katakan: catat tugas matematika besok" />`.
  - Row hover: `bg-bmo-screen/40`.
  - Action button "Edit" / "Tandai selesai" pakai `<BmoButton variant="secondary" size="sm">`.

  **Must NOT do**: jangan break edit task feature dari teammate (commit `4f9ce4c`).

  **Acceptance**:
  - Task list render dengan BMO theme
  - Edit task modal masih jalan
  - Empty state muncul saat tasks kosong

- [ ] 18. ExpensesPage redesign

  **What to do**: Edit `frontend/src/pages/ExpensesPage.tsx` + `frontend/src/components/ExpenseList.tsx`:
  - Keep existing logic.
  - BMO header H1.
  - Form add expense: pakai `<BmoInput>` + `<BmoButton variant="primary">`.
  - Currency style: `font-mono text-bmo-dark font-medium`.
  - Empty state: `<EmptyState face="idle" title="Belum ada pengeluaran" description="Coba: catat makan siang 25000" />`.

  **Acceptance**:
  - Page render dengan BMO theme
  - Form input/button BMO style
  - `npm run build` exit 0

- [ ] 19. LogsPage redesign + rename

  **What to do**: Edit `frontend/src/pages/LogsPage.tsx` + `frontend/src/components/VoiceLogList.tsx`:
  - Header rename: "Riwayat" → "Riwayat Suara".
  - Tambah BMO face mini icon (28px) per row mapping status:
    - status=success → happy
    - status=error → sad
    - lainnya → idle
  - Reply text truncate 80 char + tombol "Lihat detail" expand row inline.
  - Empty state: `<EmptyState face="idle" title="Belum ada riwayat" />`.

  **Must NOT do**: jangan ubah column structure (keep id, input_text, response_text, status, created_at).

  **Acceptance**:
  - Page render dengan icon BMO per row
  - Expand row works
  - `npm run build` exit 0

- [ ] 20. DevicesPage redesign + pair modal wiring

  **What to do**: Edit `frontend/src/pages/DevicesPage.tsx`:
  - Replace existing `<DeviceList>` rendering dengan grid `<DeviceCard>` (Wave 2 Task 11).
  - Header: tombol "Pair Device Baru" buka `<PairDeviceModal>`.
  - Modal close → refresh device list (`load(userId)`).
  - Hapus banner "Integrasi firmware ESP32 ditunda" (sudah obsolete).
  - Empty state: `<EmptyState face="idle" title="Belum ada device" cta={<BmoButton onClick={openModal}>Pair sekarang</BmoButton>} />`.

  **Must NOT do**: jangan hapus existing `<DeviceList>` sebelum `<DeviceCard>` siap (Task 11 dependency).

  **References**:
  - `app/api/devices.py` — pair endpoint
  - Wave 2 Task 11 components

  **Acceptance**:
  - Pair modal opens + closes
  - Successful pair → device list refresh
  - Config_json copy button works
  - `npm run build` exit 0

- [ ] 21. App.tsx nested routes + guard wiring

  **What to do**: Edit `frontend/src/App.tsx`:
  - Restructure routes:
    ```tsx
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<PublicGuard><LoginPage /></PublicGuard>} />
      <Route path="/app" element={<AuthGuard><AppLayout /></AuthGuard>}>
        <Route index element={<DashboardPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="expenses" element={<ExpensesPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="devices" element={<DevicesPage />} />
        <Route path="observability" element={<ObservabilityPage />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
    ```
  - `<AppLayout>` = wrapper baru: `<AppNavbar /> + <main><Outlet /></main>`. Replace existing `<Layout>` (legacy sidebar dipensiunkan).
  - `isReady()` check tetap dipakai untuk dashboard pages tapi tidak menghalangi landing/login (mereka public).

  **Must NOT do**: jangan hapus `<Layout>` sebelum semua page migrated; jangan break NotFound route.

  **References**: existing `frontend/src/App.tsx`, React Router v6 docs.

  **Acceptance**:
  - `/` accessible without cookie
  - `/login` accessible without cookie, redirects ke `/app` saat sudah login
  - `/app/*` redirect ke `/login` saat tanpa cookie
  - Refresh halaman tetap di route yang sama
  - `npm run build` exit 0

- [ ] 22. index.css update

  **What to do**: Edit `frontend/src/index.css`:
  - Body background: ganti `bg-slate-50` → `bg-surface`
  - Body text color: ganti `text-slate-900` → `text-bmo-dark`
  - Add JetBrains Mono import via `@font-face` atau `<link>` di `index.html` (latter lebih simpel — Google Fonts CDN).
  - Tambah utility class `.bmo-screen-text` untuk render code/token (font-mono, bg-bmo-screen, text-bmo-dark, padding 2px 6px, rounded).

  **Must NOT do**: jangan tambahkan global CSS reset; Tailwind sudah handle.

  **Acceptance**:
  - Body bg visible berbeda (hint of green)
  - Code element di tasks/devices page render mono font
  - `npm run build` exit 0

- [ ] 23. Backend CORS adjustment

  **What to do**: Edit `app/main.py` `CORSMiddleware` config:
  - Set `allow_credentials=True`
  - Pastikan `allow_origins` include `http://localhost:5173` + `http://127.0.0.1:5173` (existing) + production frontend URL kalau sudah diketahui.
  - Pastikan `allow_methods=["*"]` dan `allow_headers=["*"]` masih ada.

  **Must NOT do**:
  - Jangan set `allow_origins=["*"]` bersama `allow_credentials=True` — illegal per CORS spec, browser akan reject.
  - Jangan rusak existing 310 tests — TestClient tidak melalui CORS path, jadi changes safe.

  **References**: `app/main.py:39-48` (existing middleware).

  **Acceptance**:
  - `python -m pytest -q` masih 310 passed
  - Frontend dev (`npm run dev` port 5173) bisa hit backend port 8765 tanpa CORS error
  - DevTools network tab menunjukkan `Access-Control-Allow-Credentials: true`

- [ ] 24. npm run build verification

  **What to do**:
  - `cd frontend && npm install` (kalau ada dep baru — JetBrains Mono via Google Fonts tidak butuh package).
  - `npm run build` → expect exit 0, dist artifact ter-generate.
  - Cek bundle size warning. Bila >500KB warning, dokumentasikan tapi jangan blok.
  - Cek `tsc -b` hasil: zero TypeScript errors.

  **Must NOT do**: jangan disable strict mode untuk hide errors.

  **Acceptance**:
  - `npm run build` exit 0
  - `frontend/dist/` ter-generate
  - Zero TS errors di stderr

- [ ] 25. Manual QA checklist execution

  **What to do**: Jalankan smoke test manual berdasarkan BMO Pre-Delivery Checklist:

  Setup: `uvicorn app.main:app --port 8765` + `cd frontend && npm run dev` + login `admin/admin` (set `DASHBOARD_PASSWORD_SCRYPT` via helper script dulu).

  Visual:
  - [ ] Landing page render BMO mascot di hero
  - [ ] Login page BMO face swap on error states (test wrong password → sad face)
  - [ ] No emoji icons di UI
  - [ ] Hover stable (no layout shift)

  Interaction:
  - [ ] All buttons cursor-pointer
  - [ ] Login form: username + password + submit works
  - [ ] AuthGuard redirect: hapus cookie via DevTools → akses `/app` → redirect `/login`
  - [ ] Logout works (cookie cleared, redirect /)
  - [ ] Pair modal: submit → config_json muncul → copy button works
  - [ ] Observability live tail: kirim 3 request lewat `/agent/text`, verifikasi muncul di tail dalam 3s
  - [ ] Drill-down: click row → drawer slide-in dengan stage timing bar
  - [ ] Polling pause saat drawer open
  - [ ] Stats bar update dengan window 1h

  Layout:
  - [ ] Mobile 375px: nav collapse, no horizontal scroll
  - [ ] Tablet 768px: cards 2 column
  - [ ] Desktop 1024px+: cards 3-5 column

  Accessibility:
  - [ ] Keyboard navigation: Tab through nav links, focus ring visible
  - [ ] Form input punya label visible
  - [ ] BMO face SVG punya alt text

  **Acceptance**:
  - All checklist items checked
  - Issue ditemukan dicatat sebagai bug (tidak block phase, dokumentasi di Known Issues)

- [ ] 26. Docs — PHASE_13_SUMMARY.md + ROADMAP

  **What to do**: Buat `docs/PHASE_13_SUMMARY.md`:
  - Status (shipped, page count, component count)
  - What shipped (BMO theme, landing, login, observability, pair modal)
  - Files added (list)
  - Files modified (list)
  - How to run end-to-end (frontend + backend + login workflow)
  - Verification gates (npm run build + manual QA)
  - Known issues (bug-bug yang tidak blok demo)
  - Caveats (no test framework, no dark mode, single-user, observability polling 3s)
  - Recommended next phase (Phase 11c ESP32 firmware)

  Update `docs/ROADMAP.md`:
  - Mark Phase 13 sebagai shipped
  - Phase 11c (ESP32 firmware) becomes next

  Update `AGENTS.md`:
  - Append `docs/PHASE_13_SUMMARY.md` + `docs/phase-13/FRONTEND_BRIEF.md` ke "Where the canonical decisions live"

  **Acceptance**: 3 doc updates committed.

---

## Final Verification Wave

- [ ] F1. **Plan compliance audit** — every Must Have present, every Must NOT Have absent. Grep `frontend/package.json` untuk new deps (kosong). Grep `frontend/src` untuk emoji-as-icon (kosong). Grep `frontend/src` untuk `X-Dashboard-Token` (kosong).
- [ ] F2. **Frontend build** — `cd frontend && npm run build` exit 0, zero TS errors.
- [ ] F3. **Backend regression** — `python -m pytest -q` masih 310 passed.
- [ ] F4. **Auth flow smoke** — login admin/admin → /app accessible → logout → /app redirects /login.
- [ ] F5. **Observability live data smoke** — uvicorn + frontend running → trigger 3 `/agent/text` calls → verify muncul di `/app/observability` live tail dalam 3s → click row → drawer drill-down render dengan stage timing.
- [ ] F6. **Pair device smoke** — `/app/devices` → tombol pair → modal → submit → config_json muncul → copy button copies blob ke clipboard.
- [ ] F7. **Mobile responsive smoke** — DevTools 375px / 768px / 1024px → nav collapse, no horizontal scroll, BMO mascot scale proper.
- [ ] F8. **Accessibility smoke** — Tab through landing, login, dashboard. Focus ring visible. SVG mascot punya alt text. Form input punya label.

---

## Commit Strategy

Satu commit per wave + sub-fase, untuk reviewability:

- `phase-13: tailwind tokens + bmo svg assets + lib refactor`
- `phase-13: bmo design components (mascot, face, card, button, badge, input, states)`
- `phase-13: auth components + applayout navbar`
- `phase-13: landing page + login page`
- `phase-13: observability page + drill-down drawer`
- `phase-13: device pair modal + dashboard pages redesign`
- `phase-13: app.tsx nested routes + cors adjustment`
- `phase-13: docs (summary + roadmap + agents)`

---

## Success Criteria

### Verification Commands

```powershell
# Frontend build
cd frontend
npm install
npm run build
# Expected: dist/ generated, exit 0

# Backend regression (must stay green)
cd ..
.\.venv\Scripts\Activate.ps1
python -m pytest -q
# Expected: 310 passed

# Forbidden refs audit
findstr /S "X-Dashboard-Token" frontend\src
# Expected: no matches

findstr /S "VITE_DASHBOARD_TOKEN" frontend\src
# Expected: no matches

# Manual smoke
# Terminal 1: uvicorn app.main:app --port 8765
# Terminal 2: cd frontend && npm run dev (port 5173)
# Browser: http://localhost:5173
# 1. Landing page renders
# 2. Click Login → /login → masukkan admin/admin
# 3. Redirect /app → dashboard render
# 4. Click Devices → Pair → input nama → submit → config_json muncul
# 5. Click Observability → live tail polling
# 6. Trigger /agent/text via curl → muncul di tail
# 7. Click row → drill-down drawer
# 8. Logout → redirect /
```

### Final Checklist

- [ ] All 26 tasks complete
- [ ] `npm run build` exit 0
- [ ] Backend tests masih 310 passed
- [ ] BMO palette terapan ke seluruh UI
- [ ] BMO face SVG di ≥5 titik
- [ ] Auth flow end-to-end working
- [ ] Pair modal returns config_json
- [ ] Observability live tail + drawer + grid functional
- [ ] Mobile responsive 375px+
- [ ] No new Python dependency
- [ ] No new Node dependency
- [ ] Brief acceptance criteria all met


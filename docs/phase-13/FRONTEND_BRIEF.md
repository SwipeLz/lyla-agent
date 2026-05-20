# Phase 13 — Frontend Brief: BMO-themed Taskbot Dashboard

## TL;DR

> Visual + functional overhaul of `frontend/` to match BMO mascot identity and add the missing surfaces: public landing page, login flow, observability dashboard, dan device pairing modal. Five existing pages direpaint dengan BMO palette. Stack tetap Vite + React + TypeScript + Tailwind — no Next.js, no SSR.
>
> **Out of scope**: hardware integration UI, mobile-native app, marketing CMS, dark mode toggle (deferred).
>
> **Pages yang dibikin/diubah** (8 total): 2 baru public (landing + login), 5 redesign existing dashboard, 1 baru observability, plus device pairing modal di halaman devices.
>
> **Estimated effort**: 14–18 jam (visual-engineering category).
> **Parallel execution**: 4 waves.

---

## Vision

Taskbot adalah AIoT companion bertema BMO (Adventure Time). Frontend harus:

- **Friendly + retro game console**, bukan corporate SaaS dingin
- **Mascot-driven** — BMO face SVG hadir di banyak titik (hero, empty state, error state, device card, observability live tail)
- **Functional minimalism** — colorful tapi tidak chaos. Satu warna primer (BMO green dark `#1C4B3B`), satu warna canvas (`#C5E3BF` screen-green), satu warna aksi (`#313F98` button-blue / `#ED306A` button-red)
- **Indonesian-first copy** — semua user-facing text bahasa Indonesia, sesuai existing copy convention

Personality words: *playful, calm, nostalgic, trustworthy, slightly geeky*.

Anti-personality: *sterile dashboard, neon hyper-modern, dark cyberpunk, generic Material Design*.

---

## Inventory

### Existing pages (akan didiredesign)

| Path | Komponen utama | Status |
|---|---|---|
| `/` | DashboardPage (StatCard × 5, AgentCommandBox, VoiceLogList) | redesign |
| `/tasks` | TasksPage (TaskList) | redesign |
| `/expenses` | ExpensesPage (ExpenseList) | redesign |
| `/logs` | LogsPage (VoiceLogList) | redesign + rename ke "Riwayat Suara" |
| `/devices` | DevicesPage (DeviceList) | redesign + tambah modal pair |

### Halaman baru

| Path | Tujuan | Auth |
|---|---|---|
| `/` | Landing page publik (hero + features + CTA login) | public |
| `/login` | Form login dashboard (Phase 12 auth) | public |
| `/app/observability` | Live tail + drill-down + device grid (Phase 12 endpoints) | session-gated |

### Restrukturisasi route

```
public:
/             → LandingPage
/login        → LoginPage

authenticated (under /app):
/app          → DashboardPage
/app/tasks    → TasksPage
/app/expenses → ExpensesPage
/app/logs     → LogsPage
/app/devices  → DevicesPage (+ pair modal)
/app/observability → ObservabilityPage (NEW)
```

Akses ke `/app/*` tanpa session → redirect `/login`. Akses `/login` saat sudah login → redirect `/app`.

---

## Design Tokens

### Color Palette (dari `design_brief/bmo_design_reference.html`)

| Token | Hex | Penggunaan |
|---|---|---|
| `bmo-body` | `#9FD5B1` | Background body BMO, hero hover |
| `bmo-screen` | `#C5E3BF` | Canvas utama (background section, badge) |
| `bmo-mouth` | `#1F8941` | Aksen sukses, success badge |
| `bmo-dark` | `#1C4B3B` | Heading text, primary button bg, navbar |
| `bmo-yellow` | `#F7E72F` | Accent kecil (warning ringan, button hover halo) |
| `bmo-blue` | `#313F98` | Secondary action button, link aktif |
| `bmo-blue-light` | `#C8CFFF` | Text on `bmo-blue`, badge syncing |
| `bmo-cyan` | `#77CFDB` | Info badge, observability "live" indikator |
| `bmo-red` | `#ED306A` | Destructive action, error badge |
| `bmo-purple` | `#b297c7` | Background dekoratif (landing page bg) |
| `bmo-screen-dark` | `#0D1B2A` | Dark "screen" panel di observability live tail |

Off-the-rack neutrals (untuk text body & border, supaya tidak monoton hijau):

| Token | Hex | Penggunaan |
|---|---|---|
| `surface` | `#F8FAF6` | Background canvas utama (hint of green) |
| `surface-elev` | `#FFFFFF` | Card background |
| `text-primary` | `#1C4B3B` | Heading + body utama |
| `text-secondary` | `#475569` | Caption, label muted |
| `border` | `#D1E0CC` | Border kartu (hint of green) |

### Typography

Tetap Inter (existing), no new font. Disesuaikan weight + spacing:

| Element | Font | Size | Weight | Color |
|---|---|---|---|---|
| H1 (page title) | Inter | 28px | 500 | `bmo-dark` |
| H2 (section) | Inter | 20px | 500 | `bmo-dark` |
| Body | Inter | 15px | 400 | `text-primary` |
| Caption / label | Inter | 13px | 400 | `text-secondary` |
| Code / token | JetBrains Mono | 13px | 400 | `bmo-dark` on `bmo-screen` |

Tambah `JetBrains Mono` (atau fallback `ui-monospace`) hanya untuk render device token, log_id, JSON.

### Spacing, radius, shadow

- Spacing scale: Tailwind default
- Radius: `rounded-lg` (12px) untuk card; `rounded-md` (8px) untuk button & input; `rounded-full` untuk badge
- Shadow: minimal. Card pakai `border border-border` (1px), tidak `shadow-md`. Special exception: device card hero dapat `shadow-[—2px_2px_0_2px_#639975]` ala mascot drop-shadow

### Status badge mapping

| Status | Background | Text | Token |
|---|---|---|---|
| online / success | `#C5E3BF` | `#1C4B3B` | bmo-screen / bmo-dark |
| syncing / info | `#C8CFFF` | `#1A2466` | bmo-blue-light |
| idle / warning | `#FFF9C2` | `#6B5F00` | yellow-50 |
| offline / error | `#FFD6E5` | `#8B0035` | red-100 |

---

## Page-by-Page Wireframes

### 1. Landing page `/` (NEW, public)

**Goal**: jelasin Taskbot dalam 5 detik scroll, undang calon user login / coba demo.

```
┌────────────────────────────────────────────────────────┐
│ [BMO mini-logo] Taskbot         [Login] [Coba demo]    │
├────────────────────────────────────────────────────────┤
│                                                        │
│           HERO                                         │
│  ┌──────────────┐                                      │
│  │              │   "Asisten suara untuk pelajar       │
│  │  BMO mascot  │    Indonesia."                       │
│  │  (idle face) │                                      │
│  │   80px       │   Catat tugas, ingatkan deadline,    │
│  │              │   pantau pengeluaran — semua dengan  │
│  └──────────────┘   suara.                             │
│                                                        │
│            [▶ Mulai sekarang]  [Lihat fitur]           │
│                                                        │
├────────────────────────────────────────────────────────┤
│  3 PILAR                                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                 │
│  │ tugas   │  │expense  │  │reminder │                 │
│  │ icon    │  │ icon    │  │ icon    │                 │
│  │ catat   │  │ pantau  │  │ ingat   │                 │
│  │ tugas…  │  │ uang…   │  │ jadwal… │                 │
│  └─────────┘  └─────────┘  └─────────┘                 │
├────────────────────────────────────────────────────────┤
│  HOW IT WORKS (4 langkah, ilustrasi BMO face transisi) │
│  idle → record → happy → speaking                      │
├────────────────────────────────────────────────────────┤
│  FAQ ringkas (4 pertanyaan)                            │
│  Footer: dibuat untuk skripsi · GitHub · email         │
└────────────────────────────────────────────────────────┘
```

Komponen baru: `<HeroSection />`, `<FeatureCard />`, `<HowItWorksStep />`, `<FaqAccordion />`, `<PublicNavbar />`, `<PublicFooter />`.

### 2. Login `/login` (NEW, public)

**Goal**: form login Phase 12. Single-user creds dummy. Disambungkan ke `POST /auth/login`.

```
┌────────────────────────────────────────────────────────┐
│ [BMO logo]                          ← Kembali ke beranda│
├────────────────────────────────────────────────────────┤
│                                                        │
│          ┌──────────────────────────┐                  │
│          │                          │                  │
│          │      [BMO 80px]          │                  │
│          │                          │                  │
│          │   Masuk Dashboard        │                  │
│          │                          │                  │
│          │   Username               │                  │
│          │   [_______________]      │                  │
│          │                          │                  │
│          │   Password               │                  │
│          │   [_______________]      │                  │
│          │                          │                  │
│          │   [Masuk]                │                  │
│          │                          │                  │
│          │   ⓘ Default admin/admin  │                  │
│          │                          │                  │
│          └──────────────────────────┘                  │
└────────────────────────────────────────────────────────┘
```

Empty state default kosong. Saat error 401: BMO swap ke `sad_face.svg`, kasih caption "Username atau password salah". Saat 429: BMO `dizzy_face.svg`, "Terlalu banyak percobaan. Tunggu 5 menit."

Komponen: `<LoginCard />` (bisa reuse design pattern card BMO mascot).

### 3. App Layout (`/app/*`)

```
┌────────────────────────────────────────────────────────┐
│ [BMO mini] Taskbot   [Ringkasan][Tugas][Pengeluaran]   │
│                      [Riwayat][Devices][Observability] │
│                                       [user▾][Logout]  │
├────────────────────────────────────────────────────────┤
│                                                        │
│  PAGE CONTENT                                          │
│                                                        │
└────────────────────────────────────────────────────────┘
```

Top navbar `bmo-dark` background, link hover `bmo-screen`, link aktif underline `bmo-body`. Replace existing sidebar.

Komponen baru: `<AppNavbar />`, `<UserMenu />` (logout via `POST /auth/logout`).

### 4. Dashboard `/app` (REDESIGN)

Layout sama dengan existing tapi visual BMO. Stat card 5 kolom dengan label kecil + angka besar `bmo-dark`. AgentCommandBox dipertajam: BMO face di kanan, react ke status response (success → happy_face, error → sad_face, idle → idle_face). VoiceLogList diganti tabel dengan badge status warna BMO.

### 5. Tasks `/app/tasks` (REDESIGN)

Tetap functional table existing. Header "Tugas" + filter chip status. Empty state: BMO `idle_face` + caption "Belum ada tugas. Coba `catat tugas matematika besok`."

### 6. Expenses `/app/expenses` (REDESIGN)

Sama dengan tasks. Tabel + form add expense. Currency styled `bmo-dark`.

### 7. Logs (Riwayat) `/app/logs` (REDESIGN)

Tabel `VoiceCommandLog`. Tambahin BMO face icon kecil di kolom status (mapping status string → BMO face SVG). Reply text di-truncate, expand on click.

### 8. Devices `/app/devices` (REDESIGN + Pair Modal)

Card grid (bukan tabel). Setiap card pakai BMO mascot mini 48px dari `bmo_design_reference.html`. Header tombol "Pair Device" → modal:

```
┌──────────────────────────────────────┐
│  Pair Device Baru             [×]    │
├──────────────────────────────────────┤
│                                      │
│  Nama device                         │
│  [Lyla Demo Unit_______________]     │
│                                      │
│  [Batal]            [Generate]       │
│                                      │
│  ──── setelah submit ────             │
│                                      │
│  ✓ Device berhasil dipair            │
│                                      │
│  Salin config_json ke /sd/config.json│
│  ┌────────────────────────────┐      │
│  │ { "device_id": "...",      │      │
│  │   "device_token": "...",   │      │
│  │   ...                     }│      │
│  └────────────────────────────┘      │
│                                      │
│  [📋 Salin]   [Tutup]                │
└──────────────────────────────────────┘
```

Komponen baru: `<DeviceCard />` (with BMO mascot + badge status), `<PairDeviceModal />`.

### 9. Observability `/app/observability` (NEW)

Tiga panel sesuai brief:

```
┌────────────────────────────────────────────────────────┐
│ STATS  [reqs/min] [p95]  [success%]  [active devices]  │
├────────────────────────────────────────────────────────┤
│                                                        │
│ LIVE TAIL (auto-refresh 3s)                            │
│ ┌────────────────────────────────────────────────────┐ │
│ │ time | device | code | status | total | stt | agent│ │
│ │ 12:42| TBOT01 | ok_t | ✓      | 2.1s  | 320 | 1.4s │ │← click row
│ │ 12:41| TBOT01 | err_ | ✗      | 5.2s  | 320 | 4.8s │ │
│ │ ...                                                │ │
│ └────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────┤
│ [DRILL-DOWN SIDEBAR — appears on row click]            │
│  • stage timing horizontal bar                         │
│  • transcript                                          │
│  • reply                                               │
│  • parsed_actions JSON                                 │
│  • client telemetry (firmware/RSSI/battery)            │
│  • error block (jika ada) — BMO sad/rage face          │
├────────────────────────────────────────────────────────┤
│ DEVICE GRID                                            │
│ ┌──────┐ ┌──────┐ ┌──────┐                             │
│ │BMO 48│ │BMO 48│ │BMO 48│                             │
│ │TBOT01│ │TBOT02│ │TBOT03│                             │
│ │●online│ ●online│ ●offline│                            │
│ │RSSI  │ │RSSI  │ │RSSI  │                             │
│ │bat   │ │bat   │ │bat   │                             │
│ └──────┘ └──────┘ └──────┘                             │
└────────────────────────────────────────────────────────┘
```

BMO face mapping (di drill-down + device card):
- `ok_*` audio_code → `happy_face.svg`
- `err_*` → `sad_face.svg`
- `fallback_tts` → `shock_face.svg`
- offline device → `very_sad_face.svg` atau `idle_face.svg` muted

Komponen baru: `<ObsStatsBar />`, `<LiveTailTable />`, `<TraceDrawer />`, `<DeviceStatusGrid />`, `<StageTimingBar />`.

Live tail polling: `setInterval(3000)` ke `GET /observability/recent?limit=50`. Pause polling saat drawer open. Tab visibility check (pause kalau tab background).


---

## Auth Flow & Routing

```
User opens / (landing) ─────────► always public
User clicks "Login" ────────────► /login
POST /auth/login (success) ─────► cookie set, redirect /app
POST /auth/login (fail) ────────► stay /login, show BMO sad face + error
User opens /app/* with cookie ──► render page
User opens /app/* no cookie ────► redirect /login
GET /auth/me on app mount ──────► verify session valid; if 401 redirect /login
User clicks Logout ─────────────► POST /auth/logout, redirect /
```

Implementation:
- `<AuthGuard>` HOC/component wraps `/app/*`. Calls `GET /auth/me` on mount. Loading → spinner. 401 → `<Navigate to="/login" />`. 200 → render children + cache user info via React context.
- `<PublicGuard>` wraps `/login`. If `GET /auth/me` returns 200, redirect to `/app`.
- Login form: `fetch('/auth/login', { credentials: 'include', ... })`. Cookie `lyla_session` di-set otomatis oleh browser.
- API client (`lib/api.ts`) update: semua request pakai `credentials: 'include'`. Hapus `X-Dashboard-Token` header (deprecated by Phase 12 cookie auth). Kalau response 401 dari `/app/*` page → trigger redirect login.

Backend wiring: backend sudah punya `/auth/login`, `/auth/logout`, `/auth/me`. Tidak ada perubahan backend yang diperlukan.

CORS: backend `app/main.py` perlu dipastikan `allow_credentials=True` dan origin frontend masuk whitelist. **Cek + update kalau perlu** sebagai task tersendiri di plan.

---

## Component Library

Reusable components yang akan dibuat di `frontend/src/components/bmo/`:

| Component | Props | Where used |
|---|---|---|
| `<BmoMascot size?>` | size (28/48/80) | hero, login, devices, observability |
| `<BmoFace expression?>` | idle/happy/sad/excited/dizzy/rage/shock/crying | empty state, error state, observability log |
| `<BmoCard>` | variant (default/success/info/warning/error) | semua card |
| `<BmoButton>` | variant (primary/secondary/accent/destructive), size | semua button |
| `<BmoBadge>` | tone (online/idle/syncing/offline) | semua status |
| `<BmoInput>` | standard input + bmo border | login, forms |
| `<EmptyState>` | face + title + description + cta | empty list states |
| `<ErrorState>` | face=sad, title, retry | reuse existing pattern |

`<BmoFace>` reads SVG dari `design_brief/bmo_face/*.svg` — copy ke `frontend/public/bmo/` saat eksekusi.

Tailwind config update:
- Extend palette dengan token BMO di tabel atas
- Tambah font family `mono: ['JetBrains Mono', 'ui-monospace']`
- Tambah custom shadow `bmo: '-2px 2px 0 2px #639975'`

---

## Pre-Existing Frontend Cleanup

Sebelum redesign, ada 1 cleanup kecil:

- `lib/env.ts` mungkin perlu update — `DEMO_USER_ID` env-driven masih dipakai sementara di Wave 3 redesign, sampai backend integrate auth-driven user resolve. Untuk Phase 13 frontend tetap pakai existing pattern (single-user MVP), tinggal nanti diganti pakai `GET /auth/me` response `username`.
- Hapus `DASHBOARD_TOKEN` dari `lib/env.ts` dan `lib/api.ts` — di Phase 12 sudah diganti session cookie. Backward incompatible cleanup.

---

## Accessibility

- Semua interactive element punya `cursor-pointer` (BMO rules section)
- Focus ring visible di semua input + button (`focus:ring-2 focus:ring-bmo-blue`)
- BMO face SVG punya `<title>` element + aria-label
- Color contrast ratio ≥4.5:1 — palette di atas sudah memenuhi
- Form input punya label visible (bukan placeholder-only)
- Live tail row punya `role="row"`, `aria-rowindex`
- Modal pair device punya `role="dialog"`, `aria-modal="true"`, focus trap, ESC close
- Polling pause saat user prefer-reduced-motion atau tab background

---

## Browser Support

- Chrome / Edge / Firefox / Safari 2 versi terakhir
- Mobile responsive: 375px, 768px, 1024px, 1440px breakpoints
- No IE / legacy browser support

---

## Acceptance Criteria

- [ ] Landing page render di `/`, public, ada CTA login
- [ ] Login form functional dengan credentials test
- [ ] AuthGuard redirect properly (cookie ada → /app, no cookie + /app → /login)
- [ ] Logout clears cookie + redirect /
- [ ] Devices page punya tombol "Pair" + modal yang return config_json
- [ ] Observability page render live tail, polling 3s, drill-down sidebar berfungsi
- [ ] Stats card di observability nunjukin numeric percentile yang nyata (bukan placeholder)
- [ ] Device grid di observability nunjukin online/offline status (60s threshold)
- [ ] Semua copy bahasa Indonesia
- [ ] BMO face SVG muncul di minimal 5 titik (hero, login, empty state, observability log, device card)
- [ ] Color palette match BMO reference (visual review by user)
- [ ] No regression: existing `/tasks`, `/expenses`, `/logs`, `/devices` tetap functional
- [ ] `npm run build` exit 0, no TS errors
- [ ] WCAG: cursor-pointer, focus visible, contrast ratio ≥4.5:1 — verified manually

---

## Out of Scope

Documented sebagai non-goal supaya tidak scope-creep:

- Dark mode toggle (deferred Phase 14)
- WebSocket live updates (HTTP polling 3s sufficient)
- BMO mascot animation (idle blink, mouth movement) — visual asset SVG static
- Frontend test suite (vitest/playwright) — manual QA cukup untuk MVP
- i18n switcher — Indonesian only
- PWA / offline mode
- User profile edit / password change UI
- Multi-device pairing flow with WebSocket sync
- Audio waveform visualizer di observability

---

## References

- BMO design reference HTML: `design_brief/bmo_design_reference.html`
- BMO face SVGs: `design_brief/bmo_face/*.svg` (idle, happy, sad, excited, dizzy, rage, shock, crying, very_sad)
- Phase 12 auth endpoints: `app/api/auth.py`
- Phase 12 observability endpoints: `app/api/observability.py`
- Phase 12 device pairing: `app/api/devices.py`
- Existing frontend runbook: `docs/FRONTEND_DASHBOARD.md`


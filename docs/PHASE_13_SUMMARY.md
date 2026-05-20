# Phase 13 — Frontend BMO Redesign + Phase 12 UI — SHIPPED

**Status**: shipped. Frontend BMO theme + landing/login/observability pages + device pair modal.

**Build**: `npm run build` exit 0. 77 modules. 230 KB JS / 70 KB gzip.
**Backend regression**: 310 passed (no regression from CORS adjustment).

## What shipped

### Public surface (NEW)
- `/` — Landing page dengan hero BMO, 3 fitur, 4 cara kerja, FAQ, CTA login
- `/login` — Form login Phase 12 dengan BMO face state-mapped (idle / excited / happy / sad / dizzy)

### Authenticated surface (NEW + redesign)
- `/app` — Dashboard redesign dengan BMO palette (was `/`)
- `/app/tasks` — Tasks redesign dengan filter chips
- `/app/expenses` — Expenses redesign dengan BMO form input
- `/app/logs` — Riwayat Suara redesign dengan empty state
- `/app/devices` — Devices redesign dengan card grid + Pair modal
- `/app/observability` — NEW: live tail (3s polling) + drill-down drawer + device grid + stats bar

### Auth flow (NEW)
- `<AuthGuard>` wraps `/app/*`, redirects to `/login` saat tanpa cookie
- `<PublicGuard>` wraps `/login`, redirects ke `/app` saat sudah login
- `<UserMenu>` dropdown dengan logout button
- API client refactored: `credentials: 'include'`, `AuthRequiredError` saat 401 di non-auth endpoints

### BMO design system
- Tailwind config extended: 11 BMO color tokens + JetBrains Mono font + custom shadow
- 8 BMO base components: `BmoMascot`, `BmoFace`, `BmoCard`, `BmoButton`, `BmoBadge`, `BmoInput`, `EmptyState`, plus existing `ErrorState`
- 9 BMO face SVG di `frontend/public/bmo/` (idle, happy, sad, very_sad, excited, dizzy, rage, shock, crying)
- BMO mascot 3 ukuran: 28px (logo), 48px (cards), 80px (hero)

### Component library by domain
- `auth/`: AuthGuard, PublicGuard, UserMenu, UserContext (4 files)
- `landing/`: PublicNavbar, HeroSection, FeatureCard, HowItWorksStep, FaqAccordion, PublicFooter (6 files)
- `devices/`: DeviceCard, PairDeviceModal (2 files)
- `observability/`: ObsStatsBar, LiveTailTable, TraceDrawer, StageTimingBar, DeviceStatusGrid (5 files)
- `bmo/`: 6 base components
- AppNavbar (top horizontal nav, replaces sidebar)

## Files added (37)

```
frontend/public/bmo/{idle,happy,sad,very_sad,excited,dizzy,rage,shock,crying}_face.svg

frontend/src/components/bmo/
  BmoMascot.tsx
  BmoFace.tsx
  BmoCard.tsx
  BmoButton.tsx
  BmoBadge.tsx
  BmoInput.tsx

frontend/src/components/auth/
  AuthGuard.tsx
  PublicGuard.tsx
  UserMenu.tsx
  UserContext.ts

frontend/src/components/landing/
  PublicNavbar.tsx
  HeroSection.tsx
  FeatureCard.tsx
  HowItWorksStep.tsx
  FaqAccordion.tsx
  PublicFooter.tsx

frontend/src/components/devices/
  DeviceCard.tsx
  PairDeviceModal.tsx

frontend/src/components/observability/
  ObsStatsBar.tsx
  LiveTailTable.tsx
  TraceDrawer.tsx
  StageTimingBar.tsx
  DeviceStatusGrid.tsx

frontend/src/components/AppNavbar.tsx
frontend/src/components/EmptyState.tsx

frontend/src/pages/
  LandingPage.tsx
  LoginPage.tsx
  ObservabilityPage.tsx

docs/PHASE_13_SUMMARY.md
docs/phase-13/FRONTEND_BRIEF.md
.sisyphus/plans/phase-13-frontend-bmo.md
```

## Files modified (10)

- `frontend/tailwind.config.js` — extended palette + font + shadow
- `frontend/index.html` — JetBrains Mono CDN link
- `frontend/src/index.css` — body bg `bg-surface`, text `text-bmo-dark`
- `frontend/src/App.tsx` — nested routes, AuthGuard/PublicGuard wiring, NotFound BMO redesign
- `frontend/src/lib/types.ts` — auth + observability + pair types, AuthRequiredError, Device telemetry
- `frontend/src/lib/api.ts` — cookie auth, 401 → AuthRequiredError, 9 new endpoints
- `frontend/src/lib/env.ts` — drop `DASHBOARD_TOKEN`
- `frontend/src/pages/{Dashboard,Tasks,Expenses,Logs,Devices}Page.tsx` — BMO redesign
- `app/main.py` — CORS `allow_credentials=True`
- `docs/ROADMAP.md` — Phase 13 marker

## How to run end-to-end

Backend setup:

```powershell
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m scripts.seed_dev
python -m scripts.hash_dashboard_password --password admin
# Copy printed value into .env as DASHBOARD_PASSWORD_SCRYPT=<value>
```

Backend run:

```powershell
uvicorn app.main:app --port 8765
```

Frontend setup (one-time):

```powershell
cd frontend
npm install
# Set VITE_API_BASE_URL=http://127.0.0.1:8765 in frontend/.env
# Set VITE_DEMO_USER_ID + VITE_DEMO_DEVICE_ID dari output seed_dev
```

Frontend run:

```powershell
npm run dev
```

Open browser:

1. `http://localhost:5173/` — landing page render dengan BMO hero
2. Click "Login" → `/login`
3. Username `admin` / password `admin` → submit → redirect `/app`
4. Click "Devices" → "Pair Device Baru" → input nama → Generate → config_json muncul → Salin
5. Click "Observability" → live tail polling tiap 3s
6. Trigger backend: `curl -X POST http://127.0.0.1:8765/agent/text -H "Content-Type: application/json" -d '{"user_id":"<demo_user>","text":"halo"}'` (atau via Agent Command box di Dashboard)
7. Lihat row baru muncul di live tail dalam 3 detik
8. Click row → drawer drill-down dengan stage timing bar
9. Click logout di pojok kanan navbar → cookie cleared → redirect `/`

## Verification gates

| Gate | Command | Expected |
|---|---|---|
| Frontend build | `cd frontend; npm run build` | exit 0, 77 modules |
| Backend regression | `python -m pytest -q` | 310 passed |
| No legacy refs | `findstr /S "X-Dashboard-Token" frontend\src` | no matches |


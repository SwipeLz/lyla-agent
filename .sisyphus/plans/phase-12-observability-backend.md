# Phase 12 — Observability Dashboard + Simple Auth (Backend)

## TL;DR

> **Quick Summary**: Add observability/troubleshooting backend so any failure during Phase 11c (ESP integration) can be diagnosed by layer (validation/STT/agent/TTS/network) within seconds via dashboard drill-down. Plus minimal-but-internet-safe auth + device pairing flow so operator can provision an ESP without manually editing files.
>
> **Threat model: internet-facing.** Backend dihost di server (VPS atau Cloudflare Tunnel ke WSL). TLS dihandle di luar app oleh tunnel/reverse proxy. App tetap pakai HTTP internally. Ini mengubah beberapa keputusan keamanan dari versi LAN-only sebelumnya — lihat tabel "Decisions Locked".
>
> **Deliverables**:
> - Alembic migration: `VoiceCommandLog` (+3 cols), `Device` (+4 cols)
> - Stdlib-only auth: `app/auth/passwords.py` (scrypt), `app/auth/session.py` (in-memory store)
> - In-memory rate limiter (`app/api/_rate_limit.py`) untuk `/auth/login`
> - 3 auth endpoints (`/auth/login`, `/auth/logout`, `/auth/me`) — hashed creds di env, no DB user table
> - 4 observability endpoints (trace, recent, stats, devices)
> - Device pairing endpoint (returns ready-to-paste `config_json`) — **no rotate-token** (manual procedure)
> - Stage-timing capture in `_agent_helpers.py` and `audio.py` handler
> - Extended heartbeat schema (firmware_version, RSSI, battery, free_heap)
> - `X-Device-Token` enforcement gate **default ON**
> - ~33 new tests, no regression on 256 existing
>
> **Estimated Effort**: 13-16 hours (tambah ~1.5 jam dari versi LAN-only untuk scrypt + rate limit)
> **Parallel Execution**: YES — 6 waves
> **Critical Path**: settings → migration → models → password+session+ratelimit → telemetry → observability endpoints → tests → docs

---

## Context

### Original Request

Operator wants a dashboard surface that tracks every parameter sent between ESP32 and backend so failures during demo can be pinpointed (e.g. "fail at STT" or "fail at agent") within ~5 seconds of looking. Single user, single device, dummy creds. Backend dihost di internet (VPS atau Cloudflare Tunnel ke WSL), bukan LAN-only — ESP32 nembak ke domain publik, bukan IP lokal. Anti-overengineering: NO multi-user, NO Prometheus stack, NO BLE/captive portal, NO JWT/OAuth, NO Redis. Effectiveness over sophistication, **tapi internet-facing wajib aman secukupnya**: password hashed (stdlib scrypt), device-token default ON, login rate-limit, cookie `Secure`. TLS dihandle di luar app (tunnel/reverse proxy).

### Constraints from Briefs

Reference: [`docs/phase-12/BACKEND_BRIEF.md`](../../docs/phase-12/BACKEND_BRIEF.md) and [`docs/phase-12/ESP_BRIEF.md`](../../docs/phase-12/ESP_BRIEF.md).

- **Existing tests MUST stay green**: 256 passed baseline.
- **`/agent/text` and `/agent/audio` behavior MUST be bit-for-bit unchanged**: response shapes don't change. Only metadata is captured server-side.
- **AGENTS.md AR7** preserved: no provider SDK in `app/audio/*` dispatchers.
- **Layer rules** per `app/AGENTS.md`: api → agent → tools → services → models. Observability and auth code stays in `app/api/` (presentation layer).
- **Migration is reversible**: Alembic downgrade tested.
- **Append-only `VoiceCommandLog`**: `metadata_json` written once, never updated.

### Inspection Findings (already known)

| File | Status | What we'll do |
|---|---|---|
| `app/config.py` | exists, pydantic-settings | add 4 new settings |
| `app/models/voice_command_log.py` | exists | add 3 cols via migration |
| `app/models/device.py` | exists, has `api_token` col already | add 4 telemetry cols, leverage existing token col |
| `app/api/_agent_helpers.py` | returns `AgentInvocation(result, log_id)` | extend to capture timings into metadata |
| `app/api/audio.py` | calls helper, classifies directive | extend to capture stage timings + write metadata |
| `app/api/devices.py` | has `POST /devices/{device_code}/status` | extend body schema for telemetry; add `POST /devices/pair` only (no rotate-token endpoint) |
| `app/api/dashboard.py` | exists with `/dashboard/*` endpoints | leave alone; observability lives in new `app/api/observability.py` |
| `app/services/log_service.py` | `create_voice_command_log` returns row | extend to accept `metadata_json` and timestamps |

### Decisions Locked

| Decision | Choice | Rationale |
|---|---|---|
| Threat model | internet-facing (VPS or Cloudflare Tunnel → WSL) | backend di-host di server, bukan LAN demo |
| TLS termination | external (tunnel / reverse proxy) | app tetap HTTP, no certifi handling in code, no `ssl` module usage |
| Auth storage | env-driven (hashed), in-memory session dict | single-user MVP, no DB clutter, server-restart re-login is acceptable |
| Password hashing | stdlib `hashlib.scrypt` (n=2**14, r=8, p=1) | no new dep, ~50ms/login, OWASP-recommended params for KDF |
| Credential at rest in `.env` | `DASHBOARD_PASSWORD_SCRYPT` (hex of `salt:hash`) | plaintext password never on disk; helper script generates the value |
| Session token format | URL-safe random 32 bytes (`secrets.token_urlsafe(32)`) | stdlib, no JWT lib |
| Session TTL | 24 hours default, env-configurable | usability for demo |
| Cookie flags | `HttpOnly`, `SameSite=Lax`, `Secure=True` (env-toggleable for local dev) | Secure mandatory under HTTPS termination |
| Login rate limit | in-memory token bucket per-IP, 5 fails / 5 min → 429 | brute-force defense without Redis; ~30 LOC |
| Token enforcement | `REQUIRE_DEVICE_TOKEN` flag, **default `True`** | internet-facing → endpoint terbuka = quota Gemini bocor; gating ON sejak hari pertama |
| Device-token rotation endpoint | **dropped** | 1-device MVP, manual procedure (regen via DB / pair ulang) lebih simpel daripada flow OTA config |
| Pairing flow | manual SD-card transfer of `config_json` blob | brief explicitly chose Scenario A (manual provisioning) |
| Telemetry storage | single `metadata_json` JSON column on `VoiceCommandLog` | avoids 2-table joins; SQLite JSON1 functions handle ad-hoc queries later |
| Stats aggregation | computed on-the-fly from VoiceCommandLog | no time-series DB, 1 demo unit = small data |
| Observability endpoints location | new `app/api/observability.py` | clean separation from `dashboard.py` (read-only operator views vs business CRUD) |

---

## Work Objectives

### Core Objective

Operator can: (a) login dengan dummy creds, (b) pair new device → get config_json blob, (c) watch live tail of `/agent/audio` requests dengan stage-by-stage timing breakdown, (d) drill into any failed request to see exactly which layer failed.

### Concrete Deliverables

- `alembic/versions/xxxxxx_phase12_observability.py`
- `app/config.py` — 6 new settings (added: `dashboard_password_scrypt`, `cookie_secure`, `login_rate_limit_*`)
- `.env.example` — Phase 12 block
- `app/auth/__init__.py`
- `app/auth/passwords.py` — `hash_password`, `verify_password` (stdlib `hashlib.scrypt`)
- `app/auth/session.py` — in-memory session store
- `app/api/auth.py` — login/logout/me endpoints
- `app/api/_auth_dependencies.py` — `require_session` and `require_device_token` dependencies
- `app/api/_rate_limit.py` — in-memory per-IP token bucket for `/auth/login`
- `app/api/observability.py` — 4 endpoints
- `app/api/devices.py` — extended (pair + heartbeat schema; **no rotate-token**)
- `app/api/_agent_helpers.py` — captures stage timings
- `app/api/audio.py` — captures full telemetry including ESP-sent fields
- `app/services/log_service.py` — accepts metadata_json + timestamps
- `app/services/device_service.py` — `pair_device`, `update_telemetry` methods (no `rotate_token`)
- `app/schemas/auth.py`, `app/schemas/observability.py`, `app/schemas/device.py` (extend)
- `app/main.py` — mount new routers
- `scripts/hash_dashboard_password.py` — CLI helper to generate `DASHBOARD_PASSWORD_SCRYPT` value
- ~33 new tests under `app/tests/test_phase12_*.py`
- `docs/PHASE_12_SUMMARY.md` — what shipped
- `docs/ROADMAP.md` — Phase 12 marked current

### Definition of Done

- [ ] `python -m pytest -q` reports 289+ passed (256 + ~33 new), zero regression
- [ ] `python -m alembic upgrade head` then `python -m alembic downgrade -1` round-trips clean
- [ ] `python -m scripts.hash_dashboard_password` mencetak nilai siap-paste untuk `DASHBOARD_PASSWORD_SCRYPT`
- [ ] Operator can `POST /auth/login` dengan password plaintext, server verify pakai scrypt
- [ ] 6 percobaan login salah dari IP yang sama dalam 5 menit → request ke-6 dapat 429
- [ ] Operator can `POST /devices/pair` → receive valid `config_json`
- [ ] `POST /agent/audio` writes `metadata_json` with stage timings
- [ ] `GET /observability/trace/{log_id}` returns full structured trace
- [ ] `GET /observability/recent?limit=50` returns array sorted newest-first
- [ ] `GET /observability/stats?window=1h` returns aggregates
- [ ] `GET /observability/devices` returns array with telemetry
- [ ] Heartbeat with extended fields updates Device row's telemetry cols
- [ ] **`REQUIRE_DEVICE_TOKEN=true` (default)**: request ke `/agent/audio` tanpa `X-Device-Token` valid → 401
- [ ] `COOKIE_SECURE=true` (default in production): cookie `lyla_session` di-set dengan flag `Secure`
- [ ] No new entry in `requirements.txt` (use stdlib `secrets`, `hmac`, `hashlib`)
- [ ] Existing `/agent/text` test suite still passes unchanged

### Must Have

- 6 new settings + `.env.example` block
- Helper script `scripts/hash_dashboard_password.py` untuk generate scrypt hash dari plaintext password
- Migration reversible (Alembic upgrade + downgrade pair)
- `VoiceCommandLog.metadata_json` populated for every successful AND error path
- Stage timings: `validate`, `stt`, `agent`, `classify`, `tts` (5 stages)
- Auth dependencies (`require_session`) applied to `/observability/*` and device-pairing endpoints
- `X-Device-Token` enforcement is **default ON** via `REQUIRE_DEVICE_TOKEN=True`
- Login rate limit: in-memory token bucket per-IP, default 5 fails / 5 min
- Cookie set with `HttpOnly`, `SameSite=Lax`, dan `Secure` (toggle via `COOKIE_SECURE`, default `True`)
- Device pairing returns a complete `config_json` blob ready for SD card

### Must NOT Have (Guardrails)

- No new Python dependency (use stdlib only — `hashlib.scrypt` is in stdlib)
- No bcrypt/argon2/passlib/JWT libraries
- No Redis/Memcached
- **No plaintext password compare.** Only verify via `hashlib.scrypt`
- No DB user table (env-stored hashed creds only)
- No JWT, no refresh tokens, no OAuth
- No WebSocket for live tail (HTTP polling sufficient)
- No Prometheus exporter, no metrics middleware library
- No multi-user, no RBAC, no admin actions audit log
- No WAL or sharding strategies for SQLite (single-user demo)
- No HTTPS code in app — TLS termination is external (tunnel/reverse proxy). App stays HTTP.
- No `ssl` module / certifi handling in code
- **No `POST /devices/{id}/rotate-token` endpoint.** Rotation is manual procedure (DB update + re-pair).
- No CSRF token (mitigated by `SameSite=Lax` + cookie auth scope)
- No changes to `/agent/text` handler
- No changes to AR7-protected modules (`app/audio/*` stays untouched except for indirect use via existing imports)

---

## Verification Strategy

### Test Decision

- **Infrastructure exists**: YES (pytest + Hypothesis + autouse network kill-switch)
- **Automated tests**: YES — TDD-style for each new endpoint
- **Framework**: pytest (existing)
- **Build verification**: `python -m pytest -q` is the gate; +Alembic migration round-trip test

### QA Policy

Per task:

- Unit tests for stateless helpers (session store, telemetry capture)
- Integration tests for endpoints via `TestClient` (mirror `test_agent_audio_endpoint.py` style)
- Migration test: upgrade + downgrade in test fixture
- Hermeticity: AR7 still enforced; no provider SDK pulled into `sys.modules`
- Network: existing autouse kill-switch fixture continues to work

Manual smoke:
- Start uvicorn → login via curl → pair device → simulate audio request with telemetry → query observability endpoints → verify all fields present

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — must complete first):
├── Task 1: Settings + .env.example block + hash_dashboard_password.py helper
├── Task 2: Alembic migration (VoiceCommandLog + Device columns)
└── Task 3: Update Pydantic schemas (DeviceOut extension, VoiceCommandLog metadata)

Wave 2 (Auth + sessions + rate limit — independent of telemetry work):
├── Task 4a: app/auth/passwords.py (scrypt hash + verify)
├── Task 4b: app/auth/session.py (in-memory session store)
├── Task 5: app/api/auth.py (login/logout/me endpoints) + app/api/_rate_limit.py
└── Task 6: app/api/_auth_dependencies.py (require_session + require_device_token)

Wave 3 (Telemetry capture — after Wave 1):
├── Task 7: log_service.create_voice_command_log accepts metadata_json + timestamps
├── Task 8: _agent_helpers.process_agent_text_command captures stage timings
└── Task 9: audio.py handler captures full telemetry (server + ESP-sent fields)

Wave 4 (Device pairing + heartbeat — after Wave 1, parallel with Wave 3):
├── Task 10: device_service.pair_device + update_telemetry (no rotate_token)
├── Task 11: api/devices.py — POST /devices/pair
└── Task 12: api/devices.py — extended heartbeat schema for status endpoint

Wave 5 (Observability endpoints — after Waves 2 + 3 + 4):
├── Task 13: app/api/observability.py — GET /observability/trace/{log_id}
├── Task 14: app/api/observability.py — GET /observability/recent
├── Task 15: app/api/observability.py — GET /observability/stats
└── Task 16: app/api/observability.py — GET /observability/devices

Wave 6 (Wiring + tests + docs):
├── Task 17: app/main.py — mount routers
├── Task 18: Tests (auth, scrypt, rate limit, telemetry, pairing, observability) — ~33 tests
├── Task 19: Full regression (must stay 256+ passed)
├── Task 20: Migration round-trip test
└── Task 21: Docs (PHASE_12_SUMMARY.md, ROADMAP, AGENTS.md updates)

Critical Path: Task 1 → Task 2 → Task 7 → Task 9 → Task 13 → Task 17 → Task 19
```

### Agent Dispatch Summary

- Wave 1: Tasks 1-3 → `quick`
- Wave 2: Tasks 4a, 4b, 5, 6 → `quick`
- Wave 3: Tasks 7-9 → `unspecified-high` (touches existing handlers)
- Wave 4: Tasks 10-12 → `quick`
- Wave 5: Tasks 13-16 → `quick`
- Wave 6: Tasks 17-21 → mixed (`writing` for docs, `unspecified-high` for full regression)

---

## TODOs

- [ ] 1. Settings + `.env.example` block + helper CLI

  **What to do**:
  - Add to `app/config.py` `Settings`:
    - `dashboard_username: str = "admin"`
    - `dashboard_password_scrypt: str = ""` — hex blob `salt_hex:hash_hex` (32-byte salt + 64-byte hash). Empty string = login disabled (fail-closed).
    - `session_ttl_hours: int = 24`
    - `cookie_secure: bool = True` — set `False` only for local dev tanpa TLS
    - `require_device_token: bool = True` — default ON (internet-facing)
    - `login_rate_limit_max_fails: int = 5`
    - `login_rate_limit_window_seconds: int = 300`
    - `base_url: str = "http://127.0.0.1:8765"` — used by `/devices/pair` to embed in `config_json`
    - `mvp_user_email: str = "demo@taskbot.local"` — single-user MVP resolver
  - Append to `.env.example` Phase 12 block with same uppercase keys. Untuk `DASHBOARD_PASSWORD_SCRYPT`, isikan placeholder dengan komentar:
    ```
    # Phase 12 — dashboard auth + observability (internet-facing).
    # Single-user MVP, scrypt-hashed password (stdlib), in-memory sessions.
    # Generate value with: python -m scripts.hash_dashboard_password
    DASHBOARD_USERNAME=admin
    DASHBOARD_PASSWORD_SCRYPT=
    SESSION_TTL_HOURS=24
    COOKIE_SECURE=true
    REQUIRE_DEVICE_TOKEN=true
    LOGIN_RATE_LIMIT_MAX_FAILS=5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS=300
    BASE_URL=http://127.0.0.1:8765
    MVP_USER_EMAIL=demo@taskbot.local
    ```
  - Create `scripts/hash_dashboard_password.py`:
    - Reads plaintext password from stdin (with `getpass.getpass`) or `--password` arg.
    - Calls `app.auth.passwords.hash_password(plaintext)` (defined in Task 4a).
    - Prints the resulting `salt_hex:hash_hex` string ready to paste into `.env`.
    - Exit 0 on success, non-zero if password empty.

  **Must NOT do**:
  - Don't hardcode a default scrypt hash in code (would weaken fail-closed posture).
  - Don't log plaintext password.
  - Don't introduce JWT secret keys.

  **Acceptance**:
  - `from app.config import settings; settings.dashboard_username == "admin"` works
  - `.env.example` parseable, all keys present
  - `python -m scripts.hash_dashboard_password --password admin` prints a valid `salt:hash` string
  - With `DASHBOARD_PASSWORD_SCRYPT=""`, login MUST always 401 (verified in Task 18)

- [ ] 2. Alembic migration

  **What to do**:
  - Generate revision: `alembic revision -m "phase12_observability"`
  - In `upgrade()`:
    - `op.add_column("voice_command_logs", sa.Column("metadata_json", sa.JSON(), nullable=True))`
    - `op.add_column("voice_command_logs", sa.Column("request_received_at", sa.DateTime(timezone=True), nullable=True))`
    - `op.add_column("voice_command_logs", sa.Column("response_sent_at", sa.DateTime(timezone=True), nullable=True))`
    - `op.add_column("devices", sa.Column("firmware_version", sa.String(64), nullable=True))`
    - `op.add_column("devices", sa.Column("wifi_rssi_dbm", sa.Integer(), nullable=True))`
    - `op.add_column("devices", sa.Column("battery_pct", sa.Integer(), nullable=True))`
    - `op.add_column("devices", sa.Column("free_heap_bytes", sa.Integer(), nullable=True))`
  - In `downgrade()`: drop all 7 columns in reverse order.
  - Use `with op.batch_alter_table("...") as batch_op:` for SQLite compatibility.
  - Update `app/models/voice_command_log.py` and `app/models/device.py` ORM classes to declare new columns matching migration.

  **Must NOT do**: no NOT NULL constraints (existing rows have no values), no default values that require backfill.

  **Acceptance**:
  - `alembic upgrade head` succeeds on fresh DB
  - `alembic downgrade -1` succeeds and removes columns
  - `from app.models import VoiceCommandLog, Device; VoiceCommandLog.__table__.c.metadata_json` exists

- [ ] 3. Pydantic schema extensions

  **What to do**:
  - Extend `app/schemas/dashboard.py::DeviceOut`:
    - Add: `firmware_version: Optional[str] = None`
    - Add: `wifi_rssi_dbm: Optional[int] = None`
    - Add: `battery_pct: Optional[int] = None`
    - Add: `free_heap_bytes: Optional[int] = None`
  - Create `app/schemas/observability.py`:
    - `StageTimings(BaseModel)`: validate, stt, agent, classify, tts (all `int`, ms)
    - `RequestTrace(BaseModel)`: id, user_id, device_id, input_text, response_text, status, created_at, request_received_at, response_sent_at, stage_timings, audio (filename/size/content_type), transcription_mode, directive (audio_code/face/screen_text), tts (mode/available), client (request_id/firmware/rssi/battery/recording_duration), error (layer/detail) — all optional except id/created_at
    - `RecentLogSummary(BaseModel)`: id, device_id, created_at, audio_code, status, total_ms (computed) — for live tail rows
    - `StatsResponse(BaseModel)`: count, success_count, error_count, p50_ms, p95_ms, p99_ms, top_audio_codes (list of {code, count})
    - `DeviceStatusOut(BaseModel)`: id, device_code, name, status, last_seen_at, firmware_version, wifi_rssi_dbm, battery_pct, free_heap_bytes
  - Create `app/schemas/auth.py`:
    - `LoginRequest(BaseModel)`: username, password
    - `MeResponse(BaseModel)`: username, expires_at

  **Must NOT do**: no schema migrations; these are response shapes only.

  **Acceptance**: all schemas import + validate sample dicts cleanly.

- [ ] 4a. `app/auth/passwords.py` — scrypt hash + verify

  **What to do**:
  - Create new package `app/auth/__init__.py` (empty `__all__ = []`).
  - Create `app/auth/passwords.py`:
    - Constants:
      - `SCRYPT_N = 2**14`  # 16384, OWASP-recommended baseline (~50ms on modern CPU)
      - `SCRYPT_R = 8`
      - `SCRYPT_P = 1`
      - `SCRYPT_DKLEN = 64`  # 64-byte derived key
      - `SALT_BYTES = 32`
    - `def hash_password(plaintext: str) -> str`:
      - Generate `salt = secrets.token_bytes(SALT_BYTES)`
      - `dk = hashlib.scrypt(plaintext.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN, maxmem=64*1024*1024)`
      - Return `f"{salt.hex()}:{dk.hex()}"`
    - `def verify_password(plaintext: str, stored: str) -> bool`:
      - If `stored` empty/missing colon → return `False` (fail-closed)
      - Split into `salt_hex`, `hash_hex`; if either decode fails → `False`
      - Recompute scrypt with same params on same salt
      - Compare via `hmac.compare_digest(computed, expected)` (constant-time)
      - Return bool
    - Both functions stateless, no module-level cache.

  **Must NOT do**:
  - No new dependency. Use stdlib `hashlib`, `hmac`, `secrets`.
  - No fallback to plaintext compare.
  - No silent exception swallowing — let `ValueError` from bad hex propagate to caller via `False` return only after defensive `try/except ValueError` around `bytes.fromhex`.

  **Acceptance**:
  - `verify_password("admin", hash_password("admin"))` returns `True`
  - `verify_password("admin", hash_password("wrong"))` returns `False`
  - `verify_password("admin", "")` returns `False` (fail-closed)
  - `verify_password("admin", "not_a_valid_hex:zzz")` returns `False`
  - Hashing same plaintext twice produces different stored values (different salts)

- [ ] 4b. `app/auth/session.py` — in-memory session store

  **What to do**:
  - Create `app/auth/session.py`:
    - `@dataclass class Session: token: str; username: str; expires_at: datetime`
    - `class SessionStore` with `create(username) -> Session`, `get(token) -> Session | None`, `revoke(token) -> None`, `cleanup_expired() -> int`
    - Internal storage: `dict[str, Session]` + `threading.Lock`
    - Token: `secrets.token_urlsafe(32)` (43 chars URL-safe)
    - Expires: `datetime.now(tz=UTC) + timedelta(hours=settings.session_ttl_hours)`
    - Lazy eviction: `get()` checks expiry, returns None if expired and removes
  - Module-level singleton: `session_store = SessionStore()`

  **Must NOT do**:
  - No new dependency (use stdlib `secrets`, `threading`, `datetime`).
  - No persistence to disk; this is intentional for MVP.

  **Acceptance**:
  - `s = session_store.create("admin"); s.token` is 43-char string
  - `session_store.get(s.token)` returns same Session
  - After expiry: `session_store.get(s.token)` returns None

- [ ] 5. `app/api/auth.py` + `app/api/_rate_limit.py`

  **What to do**:
  - Create `app/api/_rate_limit.py`:
    - `class LoginRateLimiter`:
      - Internal: `dict[str, list[float]]` mapping IP → list of failed-attempt unix timestamps + `threading.Lock`
      - `check(ip: str) -> None`: prune timestamps older than `settings.login_rate_limit_window_seconds`; if remaining count >= `settings.login_rate_limit_max_fails`, raise `HTTPException(429, "Too many failed login attempts. Try again later.")`
      - `record_failure(ip: str) -> None`: append `time.time()` to that IP's list
      - `record_success(ip: str) -> None`: clear list for IP (reset)
    - Module-level singleton: `login_rate_limiter = LoginRateLimiter()`
    - Helper: `def get_client_ip(request: Request) -> str` — prefer `X-Forwarded-For` first hop (since reverse proxy / Cloudflare Tunnel adds it), else `request.client.host or "unknown"`. Strip whitespace, take only first comma-separated entry.

  - Create `app/api/auth.py`:
    - `router = APIRouter(prefix="/auth", tags=["Auth"])`
    - `POST /auth/login` body `LoginRequest`:
      1. `ip = get_client_ip(request)`; `login_rate_limiter.check(ip)` (raises 429 if over limit)
      2. Username compare via `hmac.compare_digest(payload.username, settings.dashboard_username)` (constant-time)
      3. Password verify via `app.auth.passwords.verify_password(payload.password, settings.dashboard_password_scrypt)`
      4. If `settings.dashboard_password_scrypt == ""` → always 401 (fail-closed) regardless of input
      5. On match: `login_rate_limiter.record_success(ip)`; create session; set cookie `lyla_session`:
         - `httponly=True`
         - `samesite="lax"`
         - `secure=settings.cookie_secure`
         - `path="/"`
         - `max_age = settings.session_ttl_hours * 3600`
         - Return `MeResponse(username, expires_at)`
      6. On mismatch (any reason): `login_rate_limiter.record_failure(ip)`; raise 401 `{"detail": "Invalid credentials"}`
      - Use a dummy verify call on the username-mismatch path so total response time doesn't leak whether username exists (always run scrypt once). Comment this in code.
    - `POST /auth/logout`:
      - Read `lyla_session` cookie, call `session_store.revoke(token)`
      - Clear cookie via `response.delete_cookie("lyla_session", path="/")` (also pass `secure`/`samesite`/`httponly` matching set)
      - Return 204
    - `GET /auth/me`:
      - Use `Depends(require_session)` (defined in Task 6)
      - Return `MeResponse(username, expires_at)`

  **Must NOT do**:
  - No CSRF token (mitigated by `SameSite=Lax` + cookie auth scope; defer to production).
  - No password reset, signup, email verification.
  - No leaking timing: ALWAYS run scrypt once per login attempt, even on username mismatch.
  - No storing IPs persistently — in-memory only.

  **Acceptance**:
  - `POST /auth/login` correct creds returns 200 + `Set-Cookie` with `Secure` flag (when `COOKIE_SECURE=true`)
  - Wrong password returns 401, increments failure counter
  - 6 wrong-password attempts from same IP within 5 min → 6th returns 429
  - Successful login resets the failure counter
  - `GET /auth/me` without cookie returns 401; with valid cookie returns 200
  - With `DASHBOARD_PASSWORD_SCRYPT=""`: every login attempt returns 401

- [ ] 6. `app/api/_auth_dependencies.py` — auth dependencies

  **What to do**:
  - Create `app/api/_auth_dependencies.py`:
    - `async def require_session(request: Request) -> Session`:
      - Read cookie `lyla_session`
      - If missing/invalid/expired: raise `HTTPException(401, "Not authenticated")`
      - Return Session
    - `async def require_device_token(request: Request, db: Session = Depends(get_db)) -> Device | None`:
      - If `not settings.require_device_token`: return None (gate OFF, allow all). **Note**: default is now `True`, so this branch only triggers when explicitly disabled (e.g. local dev without paired ESP).
      - Read header `X-Device-Token`
      - If missing: raise 401 `{"detail": "Device token required"}`
      - Query `Device` by `api_token`; if None: raise 401 `{"detail": "Invalid device token"}`
      - Return matched Device

  **Must NOT do**:
  - Don't apply dependencies here; just define. Wave 5/6 wires them.
  - Don't use `OAuth2PasswordBearer` (overkill for cookie auth).
  - Don't log the device token value (PII / sensitive).

  **Acceptance**: dependencies importable, smoke-testable.

- [ ] 7. `log_service.create_voice_command_log` extension

  **What to do**:
  - Add 3 new optional kwargs: `metadata_json: dict | None = None`, `request_received_at: datetime | None = None`, `response_sent_at: datetime | None = None`.
  - When provided, persist to the corresponding columns. Validate `metadata_json` is JSON-serializable via `json.dumps` like existing `parsed_actions`.
  - Existing callers (without new kwargs) MUST continue to work unchanged — keyword-only parameters with defaults.
  - Return the row including the new fields populated (or None).

  **Must NOT do**:
  - Don't change function position-arg signature (keyword-only additions).
  - Don't validate `metadata_json` shape — schema is server-controlled, no untrusted input.

  **Acceptance**:
  - Existing `test_log_service.py` continues to pass unchanged
  - New row written with `metadata_json={"k": "v"}` round-trips correctly

- [ ] 8. `_agent_helpers.process_agent_text_command` — capture stage timings

  **What to do**:
  - Add `time.perf_counter()` instrumentation around 3 stages inside the helper:
    - `agent_invocation_ms` (the `await run_text(...)` call)
    - Set `request_received_at = datetime.now(tz=UTC)` at function entry
    - Set `response_sent_at = datetime.now(tz=UTC)` just before returning
  - Build a `metadata_json` dict containing:
    ```python
    {
      "stage_timings_ms": {"agent": agent_ms},
      "transcription": None,  # filled by audio.py if STT happened
      "directive": None,  # filled by audio.py
      "audio": None,  # filled by audio.py
      "tts": None,  # filled by audio.py
      "client": {},  # filled by audio.py from form fields
      "error": None
    }
    ```
  - Pass `metadata_json`, `request_received_at`, `response_sent_at` to `log_service.create_voice_command_log` (success path).
  - On failure path: `metadata_json["error"] = {"layer": "agent", "detail": str(exc)}`; still pass timestamps + metadata to error log row.
  - Extend `AgentInvocation` dataclass with new field: `metadata: dict` so `audio.py` handler can update it post-classify.
  - Return `AgentInvocation(result, log_id, metadata)`.

  **Must NOT do**:
  - Don't change `/agent/text` handler behavior (it doesn't call this helper directly... wait, it does NOT call this helper — confirmed by `app/api/agent.py` module docstring).
  - Don't break existing 256 tests. If any test fails, the metadata extension must be additive-only.

  **References**: `app/api/_agent_helpers.py` (Phase 11b version), `app/api/audio.py` for downstream usage pattern.

  **Acceptance**:
  - `test_agent_audio_endpoint.py` still passes
  - New metadata accessible via `invocation.metadata` after helper returns
  - Stage timings populated with non-zero `agent` value on success

- [ ] 9. `app/api/audio.py` — capture full telemetry including ESP-sent fields

  **What to do**:
  - Add new `Form` parameters to `post_agent_audio` (all optional):
    - `client_request_id: str | None = Form(None)`
    - `firmware_version: str | None = Form(None)`
    - `wifi_rssi_dbm: int | None = Form(None)`
    - `battery_pct: int | None = Form(None)`
    - `recording_duration_ms: int | None = Form(None)`
  - Wrap each major stage with `time.perf_counter()`:
    - validate
    - stt
    - classify
    - tts
  - After helper returns, mutate `invocation.metadata`:
    - `metadata["stage_timings_ms"]["validate"] = validate_ms`
    - Same for stt, classify, tts (agent already set by helper)
    - `metadata["audio"] = {filename, size_bytes, content_type}`
    - `metadata["transcription"] = {mode, duration_ms}`
    - `metadata["directive"] = {audio_code, face}`
    - `metadata["tts"] = {mode, available, content_type}`
    - `metadata["client"] = {request_id, firmware_version, wifi_rssi_dbm, battery_pct, recording_duration_ms}`
  - Persist updated metadata via a follow-up call: `log_service.update_voice_command_log_metadata(db, log_id, metadata)`. Or simpler: pass full metadata to helper BEFORE log row write — but ordering: helper writes log on success path inside itself. Cleanest: `log_service.update_voice_command_log_metadata(db, log_id, metadata_dict)` that does `UPDATE voice_command_logs SET metadata_json = ? WHERE id = ?`.

  **NOTE on append-only contract**:
  - VoiceCommandLog is append-only at semantic level (don't mutate content/parsed_actions/response_text/status). Updating `metadata_json` to attach captured timings AFTER the row is written is acceptable because metadata is server-internal observability, not core audit data. Document this exception in the code comment.

  **Must NOT do**:
  - Don't break `/agent/audio` response shape.
  - Don't include client-sent telemetry in user-facing response (only stored in metadata for backend observation).
  - Don't validate `wifi_rssi_dbm`/`battery_pct` ranges; ESP may send -1 sentinel for unknown values.
  - Don't fail the request if metadata update fails; log a warning and proceed (best-effort).

  **References**: `app/api/audio.py` (Phase 11b), `app/services/log_service.py` (extended in Task 7).

  **Acceptance**:
  - `test_agent_audio_endpoint.py` still passes
  - New tests: send request with telemetry form fields, verify `metadata_json` columns populated correctly
  - Stage timings sum approximates total request time

- [ ] 10. `device_service` — pair_device + update_telemetry

  **What to do**:
  - Add to `app/services/device_service.py`:
    - `pair_device(db, user_id, name) -> Device`:
      - Generate `device_code = "TASKBOT-" + secrets.token_hex(4).upper()`
      - Generate `api_token = "tk_live_" + secrets.token_urlsafe(32)`
      - Verify user exists; raise `NotFoundError` if not
      - Create Device row with status `OFFLINE`, return persisted row
    - `update_telemetry(db, device_id, *, firmware_version=None, wifi_rssi_dbm=None, battery_pct=None, free_heap_bytes=None) -> Device`:
      - Find device; raise `NotFoundError` if not
      - For each non-None kwarg, update column; commit + return refreshed row

  **Must NOT do**:
  - **No `rotate_token` method.** Token rotation is intentionally manual (DB update + re-pair via dashboard) for 1-device MVP. Adding rotation endpoint would force re-flashing the SD card, which is more friction than the security benefit warrants for this scope.
  - Don't expose `api_token` in returns that go to dashboard reads (filter at schema layer).
  - Don't enforce ownership (single-user MVP).

  **Acceptance**: unit-tested with mock DB; raises typed exceptions.

- [ ] 11. `app/api/devices.py` — POST /devices/pair

  **What to do**:
  - `base_url` and `mvp_user_email` already added in Task 1.
  - Add to `app/api/devices.py`:
    - `POST /devices/pair`:
      - Body `DevicePairRequest(name: str)`
      - Auth: `Depends(require_session)`
      - Resolve user: `db.query(User).filter(User.email == settings.mvp_user_email).one_or_none()`; raise 404 if missing
      - Call `device_service.pair_device(db, user.id, payload.name)`
      - Build `config_json` dict matching ESP_BRIEF.md schema (use `settings.base_url` for `base_url` field)
      - Return 201 with `DevicePairResponse(device_id, device_code, api_token, config_json)`

  **Must NOT do**:
  - **No `POST /devices/{id}/rotate-token` endpoint.** Rotation is manual procedure documented in PHASE_12_SUMMARY.md.
  - Don't enforce ownership check in MVP.
  - Don't expose api_token via GET endpoints.

  **Acceptance**:
  - `POST /devices/pair` without session: 401
  - With session: 201, response includes valid `config_json` with all required keys
  - Token format: `tk_live_<43chars>`; device_code format: `TASKBOT-<8 hex chars>`
  - `config_json["base_url"]` matches `settings.base_url`

- [ ] 12. Extended heartbeat schema for status endpoint

  **What to do**:
  - In `app/schemas/device.py` (or wherever `DeviceStatusUpdate` lives): extend optional fields `firmware_version`, `wifi_rssi_dbm`, `battery_pct`, `free_heap_bytes`.
  - In `app/api/devices.py` heartbeat handler: when extended fields provided, call `device_service.update_telemetry(db, device.id, **fields)` after the existing status update.
  - When fields absent, only the existing `status` + `last_seen_at` update happens (backward-compatible).
  - Heartbeat endpoint stays guarded by existing token mechanism.

  **Must NOT do**:
  - Don't validate ranges of telemetry numeric fields (`-1` sentinel allowed).
  - Don't break existing heartbeat tests.

  **Acceptance**:
  - Existing heartbeat tests pass unchanged
  - Heartbeat with telemetry: Device row's telemetry cols updated

- [ ] 13. `GET /observability/trace/{log_id}` — full request drill-down

  **What to do**:
  - Create `app/api/observability.py`:
    - `router = APIRouter(prefix="/observability", tags=["Observability"], dependencies=[Depends(require_session)])`
    - `GET /observability/trace/{log_id}`:
      - Query `VoiceCommandLog` by id; raise 404 if not found
      - Parse `metadata_json` (defensively — may be None for pre-Phase-12 rows)
      - Return `RequestTrace` schema with all fields populated; null for missing telemetry
  - All endpoints in this file inherit `require_session` via router-level dependency.

  **Must NOT do**:
  - Don't expose `Device.api_token` in any response.
  - Don't allow cross-user lookup (single-user MVP, but document future filter by `Depends(get_current_user)`).

  **Acceptance**:
  - Without session: 401
  - With session, valid log_id: 200 with full RequestTrace
  - Unknown log_id: 404
  - Pre-Phase-12 log row (metadata_json IS NULL): 200, telemetry fields null

- [ ] 14. `GET /observability/recent` — live tail

  **What to do**:
  - `GET /observability/recent`:
    - Query params: `limit: int = 50` (max 200), `device_id: str | None = None`, `status: str | None = None`
    - Build SQLAlchemy query: filter by device_id and/or status if provided, order by `created_at DESC`, limit
    - For each row, build `RecentLogSummary` (id, device_id, created_at, audio_code from metadata, status, total_ms = response_sent_at - request_received_at if both set else null)
    - Return list

  **Must NOT do**:
  - Don't return full transcript or response_text in summary (only available via /trace).
  - Don't fetch all rows then paginate in Python — use SQL `LIMIT`.

  **Acceptance**:
  - Default returns up to 50 newest
  - With `device_id` filter: only that device's rows
  - With `status="error"`: only error rows
  - Without session: 401

- [ ] 15. `GET /observability/stats` — aggregates

  **What to do**:
  - `GET /observability/stats?window=1h`:
    - Window values: `1h`, `24h`, `7d` (default `1h`)
    - Compute window cutoff via `datetime.now(tz=UTC) - timedelta(...)`
    - SQL queries (use SQLAlchemy):
      - `count` = total rows in window
      - `success_count` = rows where status=`success`
      - `error_count` = rows where status=`error`
    - For latency percentiles:
      - Fetch rows in window with both timestamps non-null
      - Compute `total_ms = (response_sent_at - request_received_at).total_seconds() * 1000` per row
      - Sort, compute p50/p95/p99 via `statistics.quantiles` or manual indexing
    - For top audio_codes:
      - Iterate rows in window, extract `metadata_json["directive"]["audio_code"]`, tally with `Counter`
      - Return top 5 as `[{"code": ..., "count": ...}]`
    - Return `StatsResponse` with all fields

  **Must NOT do**:
  - Don't introduce a time-series DB.
  - Don't pre-compute or cache; small data, recompute every request acceptable.

  **Acceptance**:
  - Empty window: zero counts, percentiles null
  - Populated window: numeric percentiles, top_audio_codes non-empty

- [ ] 16. `GET /observability/devices` — device status grid data

  **What to do**:
  - `GET /observability/devices`:
    - Query all Devices ordered by `last_seen_at DESC NULLS LAST`
    - For each: compute `is_online = (last_seen_at and now - last_seen_at < 60s)`
    - Build `DeviceStatusOut` per row (without `api_token`)
    - Return list

  **Must NOT do**:
  - Don't expose `api_token`.

  **Acceptance**:
  - Returns array even if empty
  - `is_online` correctly reflects 60-second threshold
  - Without session: 401

- [ ] 17. `app/main.py` — wire new routers + middleware

  **What to do**:
  - Import: `from app.api import auth as auth_router, observability as observability_router`
  - Add routers (order matters — auth before observability so middleware unwinds correctly):
    - `app.include_router(auth_router.router)`
    - `app.include_router(observability_router.router)`
  - The existing `audio` and `audio_tts` routers stay as-is.
  - Existing CORS middleware stays unchanged.
  - Existing `X-Lyla-Protocol` middleware stays unchanged.
  - No new global middleware needed; auth is dependency-based.

  **Must NOT do**:
  - Don't add session middleware that runs before/after every request — overhead unnecessary; per-route `Depends(require_session)` is sufficient.

  **Acceptance**:
  - `app/main.py` imports cleanly
  - All endpoints discoverable via `/docs` (FastAPI Swagger)

- [ ] 18. Tests — auth, scrypt, rate limit, telemetry, pairing, observability

  **What to do**:
  - Add test files under `app/tests/` (~33 tests total):
    - `test_phase12_passwords.py` (~5 tests):
      - `hash_password` returns `salt:hash` shape, both halves hex
      - Same plaintext hashed twice produces different output (different salts)
      - `verify_password` returns True for correct plaintext+stored
      - `verify_password` returns False for wrong plaintext
      - `verify_password("x", "")` returns False (fail-closed empty stored)
      - `verify_password("x", "garbage")` returns False (no colon)
      - `verify_password("x", "zz:zz")` returns False (bad hex)
    - `test_phase12_auth.py` (~7 tests):
      - login correct creds → 200 + cookie with `Secure` flag (when COOKIE_SECURE=true via patch)
      - login wrong password → 401
      - login wrong username → 401
      - login with `DASHBOARD_PASSWORD_SCRYPT=""` → 401 always
      - logout clears cookie
      - /auth/me without cookie → 401
      - /auth/me with cookie → 200 with username
    - `test_phase12_rate_limit.py` (~3 tests):
      - 5 failed logins from same IP within window: each returns 401
      - 6th attempt within window: returns 429
      - Successful login resets the counter (next failure starts fresh)
    - `test_phase12_session_store.py` (~4 tests):
      - create returns 43-char token
      - get returns same session
      - revoke removes session
      - expired session not returned (use short TTL via patch)
    - `test_phase12_device_pair.py` (~4 tests):
      - pair without session → 401
      - pair with session → 201 + valid config_json (base_url matches setting)
      - pair with name but missing demo user → 404
      - **No rotate-token endpoint exists** — assert `POST /devices/<id>/rotate-token` returns 404 (route absent)
    - `test_phase12_heartbeat_telemetry.py` (~3 tests):
      - heartbeat without telemetry: existing behavior unchanged
      - heartbeat with telemetry: Device row updated
      - subsequent heartbeat overwrites previous telemetry
    - `test_phase12_audio_metadata.py` (~5 tests):
      - audio request with no telemetry form fields: metadata captures server stages only
      - audio request with all telemetry: metadata `client` block populated
      - error path (invalid user_id): error log row written with metadata.error.layer="agent" or similar
      - stage_timings populated with non-zero values
      - response shape unchanged from Phase 11b
    - `test_phase12_observability_endpoints.py` (~7 tests):
      - /trace/{log_id} without session → 401
      - /trace/{log_id} valid id → 200 with structured RequestTrace
      - /trace/{log_id} unknown id → 404
      - /recent default returns 50 newest
      - /recent with device_id filter
      - /stats returns numeric percentiles
      - /devices returns array, no api_token in response
    - `test_phase12_device_token_gate.py` (~2 tests):
      - With `REQUIRE_DEVICE_TOKEN=true` (default): `/agent/audio` without `X-Device-Token` → 401
      - With valid `X-Device-Token` matching paired device: `/agent/audio` proceeds normally
  - Use existing `TestClient` + `StaticPool` SQLite engine pattern from `test_agent_audio_endpoint.py`.
  - For session-dependent tests: hit `/auth/login`, capture cookie, attach to subsequent requests.
  - For scrypt tests: keep `SCRYPT_N=2**14` (don't downgrade for speed). Each test ~50ms; 7 auth tests + 5 password tests + 3 rate-limit tests = ~750ms aggregate, acceptable.

  **Must NOT do**:
  - Don't introduce real Gemini calls in any test (network kill-switch enforced).
  - Don't use `unittest.mock.MagicMock` to skip auth — exercise real session store.
  - Don't downgrade scrypt parameters for faster tests; the cost of real KDF is the point.

  **Acceptance**: All ~33 new tests pass.

- [ ] 19. Full regression

  **What to do**:
  - Run `python -m pytest -q` — assert exit 0 with `(256 + ~33) passed`.
  - If any pre-existing test fails: REVERT the most recent wave, re-run, repeat until baseline restored. Document which wave broke what in this plan.

  **Must NOT do**:
  - Don't weaken any existing test to make new ones pass.

  **Acceptance**: ≥289 passed.

- [ ] 20. Migration round-trip

  **What to do**:
  - Add `app/tests/test_phase12_migration.py` with 1 test:
    - Use existing Alembic command via `subprocess` or programmatic API
    - On in-memory DB: `alembic upgrade head` → assert new columns exist
    - Then `alembic downgrade -1` → assert columns removed
  - Manual verification: `python -m alembic upgrade head; python -m alembic downgrade -1; python -m alembic upgrade head` succeeds without error.

  **Acceptance**: round-trip test passes.

- [ ] 21. Docs — PHASE_12_SUMMARY.md + ROADMAP + AGENTS

  **What to do**:
  - Create `docs/PHASE_12_SUMMARY.md`:
    - Status (shipped, test count)
    - What shipped (auth, observability endpoints, device pairing, telemetry capture)
    - Files added (list)
    - Files modified (list with one-line "why")
    - How to run end-to-end (include `python -m scripts.hash_dashboard_password` step)
    - Verification gates
    - Known issues
    - Caveats: single-user, scrypt-hashed password (stdlib), in-memory session, **internet-facing assumes external TLS termination (tunnel/reverse proxy)**, no rotate-token endpoint (manual procedure documented)
    - Manual token rotation procedure (DB UPDATE example or re-pair flow)
    - Recommended next phase (Phase 12-frontend OR Phase 11c ESP firmware)
  - Update `docs/ROADMAP.md`:
    - Mark Phase 12 (current) as shipped
    - Add Phase 12-frontend if separate (for `/observability` page implementation)
    - Phase 11c (ESP firmware) becomes next
  - Update `AGENTS.md`:
    - Append to "Where the canonical decisions live": `docs/PHASE_12_SUMMARY.md`, `docs/phase-12/BACKEND_BRIEF.md`, `docs/phase-12/ESP_BRIEF.md`
    - No new Hard Rule needed (no new hermetic invariant for Phase 12).

  **Acceptance**: all 3 doc updates committed.

---

## Final Verification Wave

- [ ] F1. **Plan compliance audit** — every Must Have present, every Must NOT Have absent. Grep `requirements.txt` for new entries (must be empty). Grep `app/auth/` for bcrypt/JWT/passlib/argon imports (must be absent). Grep `app/api/devices.py` for `rotate-token` route (must be absent).
- [ ] F2. **Backend regression** — `python -m pytest -q` reports 289+ passed (256 baseline + ~33 new), zero failures.
- [ ] F3. **Migration round-trip** — `alembic upgrade head` then `alembic downgrade -1` succeeds and tables return to Phase 11b shape.
- [ ] F4. **Manual smoke** — uvicorn started → run `python -m scripts.hash_dashboard_password --password admin` and paste into `.env` → curl `/auth/login` returns cookie with `Secure` flag → curl `/devices/pair` returns config_json → curl `/agent/audio` (with `X-Device-Token`) writes metadata → curl `/observability/recent` shows the request with stage timings populated.
- [ ] F5. **AR7 hermeticity preserved** — `test_audio_fake_hermeticity.py` still passes; observability endpoints don't import provider SDKs.
- [ ] F6. **Token gate works (default ON)** — out of the box (`REQUIRE_DEVICE_TOKEN=true`): request without `X-Device-Token` returns 401; request with valid paired token returns 200.
- [ ] F7. **Rate limit works** — 5 wrong logins from same IP within window: each 401; 6th returns 429. Successful login resets counter.
- [ ] F8. **Fail-closed empty creds** — with `DASHBOARD_PASSWORD_SCRYPT=""`: every login attempt 401, even with correct username.

## Commit Strategy

One commit per wave for reviewability:

- `phase-12: settings + alembic migration + schema extensions + scrypt helper`
- `phase-12: scrypt password hashing + in-memory session auth + login rate limit`
- `phase-12: stage-timing capture in agent helper and audio handler`
- `phase-12: device pairing + extended heartbeat (no rotate-token)`
- `phase-12: observability endpoints (trace/recent/stats/devices)`
- `phase-12: tests, docs, ROADMAP update`

## Success Criteria

### Verification Commands

```powershell
.\.venv\Scripts\Activate.ps1

# Migration round-trip
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head

# Tests
python -m pytest -q
# Expected: 289+ passed

# Forbidden-deps audit
findstr /R "bcrypt jwt argon passlib" requirements.txt
# Expected: no matches

# No rotate-token route audit
findstr /S "rotate-token rotate_token" app\api\
# Expected: no matches

# Manual smoke (uvicorn must be running)
# Step 1: generate hashed password and paste into .env as DASHBOARD_PASSWORD_SCRYPT
python -m scripts.hash_dashboard_password --password admin

# Step 2: login (note: in production behind tunnel, swap host for the public domain)
curl -X POST http://127.0.0.1:8765/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"admin"}' -c cookies.txt

# Step 3: pair device
curl -X POST http://127.0.0.1:8765/devices/pair `
  -H "Content-Type: application/json" `
  -b cookies.txt -d '{"name":"Test Device"}'

# Step 4: observe
curl http://127.0.0.1:8765/observability/recent?limit=10 -b cookies.txt
```

### Final Checklist

- [ ] All 21 tasks complete (4 split into 4a/4b)
- [ ] All tests pass (289+)
- [ ] Migration reversible
- [ ] No new Python dependency (stdlib `hashlib.scrypt` only)
- [ ] AR7 still enforced
- [ ] No `rotate-token` endpoint exists
- [ ] `REQUIRE_DEVICE_TOKEN` defaults to `true`
- [ ] `COOKIE_SECURE` defaults to `true`
- [ ] Login rate limit active (5 fails / 5 min / IP)
- [ ] `DASHBOARD_PASSWORD_SCRYPT=""` is fail-closed
- [ ] Brief acceptance criteria all met (BACKEND_BRIEF.md §"Acceptance criteria")

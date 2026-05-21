# Phase 12 — Observability Dashboard + Simple Auth (Backend) — SHIPPED

**Status**: backend done. Frontend follow-up shipped in Phase 13 (`/login`, `/observability`, "Pair New Device" modal).

**Test count**: 310 passed.

## What shipped

- **Internet-safe auth (single-user MVP)**
  - `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`
  - Password hashed with stdlib `hashlib.scrypt` (N=2^14, R=8, P=1, dklen=64, 32-byte salt)
  - Cookie `lyla_session`: `HttpOnly`, `SameSite=Lax`, `Secure` toggle via `COOKIE_SECURE` (default `true`)
  - Login rate limit: 5 fails / 5 min / IP, in-memory token bucket, `429` after threshold
  - Empty `DASHBOARD_PASSWORD_SCRYPT` is fail-closed (always 401)

- **Device pairing flow**
  - `POST /devices/pair` — session-gated, returns ready-to-paste `config_json`
  - **No rotate-token endpoint** (manual procedure for 1-device MVP)

- **Heartbeat telemetry**
  - `POST /devices/{device_code}/status` extended with optional `firmware_version`, `wifi_rssi_dbm`, `battery_pct`, `free_heap_bytes`
  - Backward-compatible: missing fields preserve previous values

- **Observability endpoints (session-gated)**
  - `GET /observability/trace/{log_id}` — full structured drill-down
  - `GET /observability/recent?limit=&device_id=&status=` — live tail
  - `GET /observability/stats?window=1h|24h|7d` — count, success/error split, p50/p95/p99 latency, top audio_codes
  - `GET /observability/devices` — device grid with `is_online` (60-second threshold)

- **Telemetry capture**
  - Stage timings (validate / stt / agent / classify / tts) recorded on every `/agent/audio` call
  - ESP-sent fields (`client_request_id`, `firmware_version`, `wifi_rssi_dbm`, `battery_pct`, `recording_duration_ms`) accepted as optional Form params
  - Stored in append-only `VoiceCommandLog.metadata_json` (server-internal only, NOT in user-facing response)
  - Error path also writes metadata with `error.layer`

- **Device-token gate**
  - `REQUIRE_DEVICE_TOKEN=true` (default ON) makes `X-Device-Token` mandatory for protected device/audio endpoints
  - `POST /agent/audio` and `GET /agent/audio/{log_id}/tts` are wired to `app/api/_auth_dependencies.require_device_token`

- **CLI helper**
  - `python -m scripts.hash_dashboard_password [--password X]` — generate `<salt_hex>:<hash_hex>` for `.env`

## Files added

- `alembic/versions/2026_05_0002_phase12_observability.py`
- `app/auth/__init__.py`
- `app/auth/passwords.py`
- `app/auth/session.py`
- `app/api/_rate_limit.py`
- `app/api/auth.py`
- `app/api/_auth_dependencies.py`
- `app/api/observability.py`
- `app/schemas/auth.py`
- `app/schemas/observability.py`
- `scripts/hash_dashboard_password.py`
- `app/tests/test_phase12_passwords.py` (8 tests)
- `app/tests/test_phase12_session_store.py` (6 tests)
- `app/tests/test_phase12_rate_limit.py` (5 tests)
- `app/tests/test_phase12_auth.py` (8 tests)
- `app/tests/test_phase12_device_pair.py` (4 tests)
- `app/tests/test_phase12_heartbeat_telemetry.py` (3 tests)
- `app/tests/test_phase12_audio_metadata.py` (5 tests)
- `app/tests/test_phase12_observability_endpoints.py` (8 tests)
- `app/tests/test_phase12_device_token_gate.py` (2 tests)

## Files modified

- `app/config.py` — 9 new settings (auth, rate limit, base_url, mvp_user_email)
- `.env.example` — Phase 12 block
- `app/models/voice_command_log.py` — `metadata_json`, `request_received_at`, `response_sent_at`
- `app/models/device.py` — `api_token`, `firmware_version`, `wifi_rssi_dbm`, `battery_pct`, `free_heap_bytes`
- `app/services/log_service.py` — accept metadata kwargs + new `update_voice_command_log_metadata`
- `app/services/device_service.py` — `pair_device`, `update_telemetry`
- `app/api/_agent_helpers.py` — capture stage timings in metadata + extend `AgentInvocation`
- `app/api/audio.py` — capture full telemetry from server + ESP-sent Form fields
- `app/api/devices.py` — extended heartbeat schema, `POST /devices/pair`
- `app/schemas/devices.py` — telemetry fields + `DevicePairRequest`/`DevicePairResponse`
- `app/schemas/dashboard.py` — `DeviceOut` extended with telemetry
- `app/main.py` — mount `auth` + `observability` routers
- `app/tests/test_schema_invariant.py` — Phase 12 columns added to reference set
- `app/tests/test_log_service.py` — bound float strategy to ±1e15 to fix flake

## How to run end-to-end

```powershell
# 1) Apply migration
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head

# 2) Generate dashboard password hash
python -m scripts.hash_dashboard_password --password admin
# Copy printed value into .env as DASHBOARD_PASSWORD_SCRYPT=<value>

# 3) Start backend
uvicorn app.main:app --port 8765

# 4) Login
curl -X POST http://127.0.0.1:8765/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"admin"}' -c cookies.txt

# 5) Pair a device
curl -X POST http://127.0.0.1:8765/devices/pair `
  -H "Content-Type: application/json" `
  -b cookies.txt -d '{"name":"Lyla Demo Unit"}'

# 6) Observe (after some /agent/audio traffic)
curl "http://127.0.0.1:8765/observability/recent?limit=10" -b cookies.txt
curl "http://127.0.0.1:8765/observability/stats?window=1h" -b cookies.txt
curl http://127.0.0.1:8765/observability/devices -b cookies.txt
```

## Verification gates

| Gate | Command | Expected |
|---|---|---|
| Full regression | `python -m pytest -q` | `310 passed` |
| Migration round-trip | `alembic upgrade head; alembic downgrade -1; alembic upgrade head` | clean |
| No new dependency | `findstr /R "bcrypt jwt argon passlib" requirements.txt` | no matches |
| No rotate-token | `findstr /S "rotate-token rotate_token" app\api\` | no matches |
| Hermetic | `app/tests/test_audio_fake_hermeticity.py` still passes | yes |

## Known issues

- `Device.api_token` was added by Phase 12 migration. Devices created before Phase 12 have `api_token = NULL` and cannot pass the `X-Device-Token` gate; pair them again via `POST /devices/pair` to mint a token.
- The device-token gate is wired for audio upload and cached TTS fetches. Local dev can keep `REQUIRE_DEVICE_TOKEN=false`; internet-facing deployments should keep it enabled and send `X-Device-Token` from ESP firmware.
- Login rate-limit state is in-memory and per-process; restarts reset the counter. Acceptable for single-instance MVP.

## Caveats

- **Single-user MVP.** No multi-user, no RBAC, no admin actions audit log.
- **scrypt-hashed password (stdlib).** No bcrypt/argon2/passlib. Replace transparently in the future by swapping `app/auth/passwords.py` internals.
- **In-memory session store.** Restart = re-login.
- **Internet-facing assumes external TLS termination.** App stays HTTP; tunnel / reverse proxy (Cloudflare Tunnel, Caddy, Nginx, hosting platform) handles certs.
- **No rotate-token endpoint.** Manual procedure documented below.

## Manual token rotation procedure (1-device MVP)

If a `device_token` is compromised, do one of:

1. **Pair a new device** via `POST /devices/pair`. Old device row stays in DB but its token is no longer in any `config.json`. Update SD card on the ESP with the new `config_json`.

2. **Direct DB rotate (dev only)**:
   ```sql
   UPDATE devices
   SET api_token = 'tk_live_' || lower(hex(randomblob(24)))
   WHERE id = '<device-id>';
   ```
   Then update the SD card manually.

Both paths require physically updating the SD card. There is no on-device rotate flow, by design.

## Recommended next phase

- **Phase 13 frontend** — completed `/login`, `/observability` (live tail + drill-down + device grid), and "Pair New Device" modal.
- **Phase 11c** — ESP firmware bringup against the new pair flow + token gate. Brief at `docs/phase-12/ESP_BRIEF.md`.

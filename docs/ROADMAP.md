# Roadmap

## Phase 0: Planning
- **Objective:** Establish project documentation, architecture, and configuration placeholders.
- **Main Steps:** Create README, architecture docs, scope, agent design, API draft, and database plan.
- **Milestone:** All planning documentation finalized.

## Phase 1: Backend Skeleton
- **Objective:** Setup FastAPI project structure.
- **Main Steps:** Initialize project, configure routers, setup dependency injection.
- **Milestone:** Basic API running and `/health` endpoint reachable.

## Phase 2: Database Schema
- **Objective:** Implement initial SQLite database.
- **Main Steps:** Setup SQLAlchemy, define models, configure Alembic for migrations.
- **Milestone:** Database models created and migrations working.

## Phase 3: Service Layer and Tools
- **Objective:** Build core business logic.
- **Main Steps:** Create services for managing tasks, expenses, and reminders.
- **Milestone:** CRUD operations verified via unit tests.

## Phase 4: Google ADK Agent Runtime
- **Objective:** Integrate Google ADK.
- **Main Steps:** Setup agent configuration, integrate tools from Phase 3, define system prompts.
- **Milestone:** Agent successfully processes static text commands via CLI/tests.

## Phase 5: Text Command Endpoint
- **Objective:** Expose agent functionality via REST API.
- **Main Steps:** Create `/agent/text` endpoint, wire it to the Google ADK runtime.
- **Milestone:** End-to-end text command processing via API.

## Phase 6: Scheduler
- **Objective:** Handle time-based events.
- **Main Steps:** Setup APScheduler or Celery for processing reminders and scheduled commands.
- **Milestone:** Background jobs running and logging correctly.

## Phase 7: Device Command Queue
- **Objective:** Enable backend-to-device communication.
- **Main Steps:** Create command tables, implement polling and acknowledgment endpoints.
- **Milestone:** `/devices/{device_code}/commands/pending` returns queued commands.

## Phase 8: Dashboard API
- **Objective:** Expose data for the frontend dashboard.
- **Main Steps:** Create read-only endpoints for tasks, expenses, and summaries.
- **Milestone:** Dashboard API fully functional.

## Phase 8.5: Integration Smoke Test (Deferred)
- **Status:** Spec written at `.kiro/specs/phase-8-5-integration-smoke-test/`; implementation deferred until after Phase 9.
- **Reason:** Frontend Phase 9 prioritized for demo readiness.

## Phase 9: Dashboard Frontend
- **Objective:** Build the web dashboard.
- **Main Steps:** Vite + React + TypeScript + Tailwind SPA at `frontend/`. Consumes existing FastAPI dashboard and `/agent/text` endpoints. No Next.js, no SSR, no BFF.
- **Milestone:** User can view summary, tasks, expenses, voice command logs, and devices, plus run agent commands manually from the browser.

## Phase 10: Audio Backend Foundation
- **Status:** Shipped. Hermetic foundation. `POST /agent/audio` accepts multipart upload, fake STT returns deterministic transcript, fake TTS emits silent WAV via stdlib `wave`.
- **Main Steps:** `app/audio/` package with provider seam (`SttProvider`/`TtsProvider` Protocols), `app/utils/audio_validation.py`, `POST /agent/audio` endpoint, AR7 hermeticity property.
- **Milestone:** Backend audio path testable end-to-end offline.
- **Runbook:** [`docs/AUDIO_BACKEND.md`](AUDIO_BACKEND.md).
- **Summary:** [`docs/PHASE_10_SUMMARY.md`](PHASE_10_SUMMARY.md).

## Phase 11a: Real Gemini STT + TTS
- **Status:** Shipped. `app/audio/stt_gemini.py` and `app/audio/tts_gemini.py` implement real providers via Gemini multimodal (STT) and Gemini TTS preview (voice=Leda) with deferred SDK imports preserving AR7.
- **Main Steps:** Provider classes, dispatcher fake|gemini in `stt.py`/`tts.py`, settings (`AUDIO_STT_PROVIDER_MODEL`, `AUDIO_TTS_PROVIDER_MODEL`, `AUDIO_TTS_VOICE`).
- **Milestone:** Real Indonesian voice command → transcript → agent → reply round-trip works in ~8.5s (success path) / ~13.5s (fallback_tts path).
- **Latency tooling:** [`scripts/measure_phase11_latency.py`](../scripts/measure_phase11_latency.py).

## Phase 11b: ESP-Ready TTS Cache + Directive (Current)
- **Status:** Shipped. `directive` field with `audio_code` enum classifies actions for ESP playback. TTS cache + binary fetch endpoint give ESP a way to retrieve dynamic audio bytes.
- **Main Steps:** `app/audio/tts_cache.py` (in-process LRU+TTL), `GET /agent/audio/{log_id}/tts`, `app/api/_audio_directive.py` (classifier), `X-Lyla-Protocol: 1` header, helper signature change to `AgentInvocation(result, log_id)`.
- **Milestone:** ESP firmware contract is frozen; backend ready for ESP integration. 256 tests pass.
- **Architecture:** [`docs/PHASE_11_ARCHITECTURE.md`](PHASE_11_ARCHITECTURE.md).
- **Backend spec:** [`docs/PHASE_11_BACKEND.md`](PHASE_11_BACKEND.md).
- **Firmware spec:** [`docs/PHASE_11_FIRMWARE.md`](PHASE_11_FIRMWARE.md).

## Phase 11c: ESP32 Firmware (Next)
- **Objective:** Build the ESP32-S3 firmware that captures audio, posts to `/agent/audio`, plays response per `directive.audio_code`.
- **Main Steps:** I2S input/output, microSD WAV cache, OLED face/screen rendering, WiFi + `WiFiClientSecure` + `setInsecure()`, state machine, JSON parser, telemetry fields, `X-Device-Token` header.
- **Milestone:** End-to-end voice interaction with hardware (record button → speech → DB update → speaker reply).
- **Contract (normative):** [`docs/ESP32_INTEGRATION_CONTRACT.md`](ESP32_INTEGRATION_CONTRACT.md).
- **Decision log:** [`docs/ESP32_INTEGRATION_ADR.md`](ESP32_INTEGRATION_ADR.md).
- **Brief (superseded in part):** [`docs/phase-12/ESP_BRIEF.md`](phase-12/ESP_BRIEF.md).

## Phase 12: Observability Dashboard + Simple Auth (Backend)
- **Status:** Shipped. Internet-safe single-user auth (scrypt-hashed, in-memory sessions, login rate-limit), device pairing flow, stage-by-stage telemetry capture, 4 observability endpoints (trace/recent/stats/devices), extended heartbeat schema, default-on `X-Device-Token` gate.
- **Main Steps:** `app/auth/passwords.py` (stdlib scrypt), `app/auth/session.py`, `app/api/auth.py`, `app/api/_rate_limit.py`, `app/api/_auth_dependencies.py`, `app/api/observability.py`, Alembic revision `0002`, telemetry capture in `_agent_helpers.py` + `audio.py`, `device_service.pair_device` + `update_telemetry`, `scripts/hash_dashboard_password.py` helper.
- **Milestone:** 305/305 tests passing. Operator can login, pair a device, and drill into any failed `/agent/audio` request to identify the failing layer (validate / stt / agent / classify / tts).
- **Summary:** [`docs/PHASE_12_SUMMARY.md`](PHASE_12_SUMMARY.md).
- **Backend brief:** [`docs/phase-12/BACKEND_BRIEF.md`](phase-12/BACKEND_BRIEF.md).

## Phase 12-frontend: Observability Frontend (Follow-up)
- **Objective:** Build the dashboard UI for the Phase 12 backend.
- **Main Steps:** `/login` route, `/observability` route (live tail + drill-down + device grid), "Pair New Device" modal on `/devices`, polling-based refresh.
- **Milestone:** Operator can troubleshoot voice failures within 5 seconds of looking at the live tail.

## Phase 13: Frontend BMO Redesign + Phase 12 UI Integration
- **Status:** Shipped. Vite/React frontend repaint dengan BMO mascot identity. Tambah landing page publik, halaman login Phase 12, halaman observability dengan live tail + drill-down drawer, modal pair device, dan AppNavbar baru menggantikan sidebar.
- **Main Steps:** Tailwind extended palette (11 BMO color tokens), 9 BMO face SVG dipindah ke `frontend/public/bmo/`, 24 React components baru (8 BMO base + 4 auth + 6 landing + 2 device + 5 observability + AppNavbar + EmptyState), 3 halaman baru (`/`, `/login`, `/app/observability`), 5 halaman dashboard direpaint, AuthGuard/PublicGuard cookie-based, API client refactor (`credentials: 'include'`), backend CORS adjustment 1 baris.
- **Milestone:** Frontend build 77 modules clean, backend regression 310 passed, BMO theme terapan ke seluruh UI, auth flow end-to-end working.
- **Summary:** [`docs/PHASE_13_SUMMARY.md`](PHASE_13_SUMMARY.md).
- **Brief:** [`docs/phase-13/FRONTEND_BRIEF.md`](phase-13/FRONTEND_BRIEF.md).

## Phase 13b: WhatsApp Notification
- **Objective:** Add external notification channels.
- **Main Steps:** Integrate WhatsApp Business API for reminders and daily summaries.
- **Milestone:** User receives automated reminders on WhatsApp.

## Phase 14: Testing and Demo
- **Objective:** Finalize project for presentation.
- **Main Steps:** Comprehensive testing, bug fixing, demo preparation.
- **Milestone:** Project ready for deployment and showcase.

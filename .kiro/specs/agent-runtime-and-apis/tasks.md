# Implementation Plan: Agent Runtime and APIs (Phase 4–8)

## Overview

Implementation berjalan bertahap: pertama setup dependency dan konfigurasi, lalu Agent Runtime + Fake Agent (Phase 4), kemudian endpoint `POST /agent/text` (Phase 5), Reminder Scheduler (Phase 6), Device Command Queue API (Phase 7), Minimal Dashboard API (Phase 8), dan terakhir cross-cutting tests + dokumentasi. Setiap implementasi tugas membungkus tool wrappers Phase 3 yang sudah ada — Service Layer dan tool wrappers tidak diubah kecuali penambahan kecil di `task_service` (`update_task`, `delete_task`).

Konvensi:
- Bahasa implementasi: Python (mengikuti stack Phase 0–3 yang sudah berjalan).
- Setiap PBT mereferensikan property dari `design.md` dan requirement clause yang divalidasinya.
- Semua sub-task wajib (termasuk test); konsisten dengan service-layer spec.

## Tasks

- [x] 1. Update dependencies dan konfigurasi proyek
  - [x] 1.1 Tambahkan `google-adk` dan `apscheduler` ke `requirements.txt`
    - Verifikasi versi `google-adk` yang tersedia via `pip index versions google-adk` (pin `>=1.0` jika ada stable, fallback `>=2.0a` dengan catatan)
    - Pin `apscheduler>=3.10`
    - _Requirements: 17.1, 17.2_

  - [x] 1.2 Perluas `Settings` di `app/config.py`
    - Tambahkan field `agent_mode: str = ""`, `scheduler_enabled: bool = False`, `scheduler_interval_seconds: int = 60`, `dashboard_auth_mode: str = "none"`, `dashboard_token: str = ""`
    - Pertahankan default semua setting Phase 0–3 (`app_env`, `database_url`, `google_api_key`, `google_adk_model`, `device_api_token`, `timezone`)
    - _Requirements: 7.3, 7.4, 14.1, 17.3, 17.5_

  - [x] 1.3 Dokumentasikan key baru di `.env.example`
    - Tambahkan baris untuk `AGENT_MODE`, `SCHEDULER_ENABLED`, `SCHEDULER_INTERVAL_SECONDS`, `DASHBOARD_AUTH_MODE`, `DASHBOARD_TOKEN` tanpa nilai rahasia
    - _Requirements: 17.4, 15.7_

- [x] 2. Phase 4 — Agent Runtime: result type dan Per-Request Tool Factory
  - [x] 2.1 Buat `AgentRunResult` dataclass di `app/agent/result.py`
    - Field: `reply: str`, `actions: list[dict]`, `device_feedback: dict | None`, `status: str`, `error: str | None = None`
    - Helper internal `_pick_device_feedback(actions)` memilih entry terakhir dengan `type=="device_command"` dan `success is True`, atau `None`
    - _Requirements: 6.5_

  - [x] 2.2 Implementasikan Per-Request Tool Factory di `app/agent/tool_factory.py`
    - Ekspor `build_tools(db, user_id, device_id) -> list` yang mengembalikan lima callable bernama `create_task`, `create_expense`, `set_reminder`, `get_today_summary`, `send_device_command`
    - Setiap callable hanya menerima Model-Visible Arguments sesuai Req 2.1; `db`/`user_id`/`device_id` di-bind via closure
    - Closure parsing string ISO 8601 → `datetime` aware sebelum diteruskan ke tool wrapper Phase 3; bila parsing gagal, kembalikan failure Tool Result Dict (jangan raise)
    - `send_device_command` short-circuit ke `{"success": False, "type": "device_command", "error": ...}` saat `device_id is None` tanpa memanggil service
    - Set `__name__` dan `__doc__` (Bahasa Indonesia singkat) tiap callable agar ADK menghasilkan skema yang benar
    - _Requirements: 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.3 Tulis property test di `app/tests/test_agent_runtime.py` untuk AR2
    - **Property AR2: Tool Schema Hides Injected Context**
    - **Validates: Requirements 2.1, 2.2**
    - Inspeksi `inspect.signature(tool).parameters` setiap tool yang dihasilkan `build_tools` → tidak boleh mengandung `db`, `user_id`, atau `device_id`

  - [x] 2.4 Tulis property test untuk AR3
    - **Property AR3: Bound Context Forwarded**
    - **Validates: Requirements 2.3, 2.4, 2.5**
    - Monkeypatch tool wrappers Phase 3 untuk merekam kwargs; verifikasi `db`/`user_id`/`device_id` yang sampai ke wrapper sama dengan yang di-bind, dan model-supplied `db`/`user_id`/`device_id` (via `**kwargs`) diabaikan

  - [x] 2.5 Tulis property test untuk AR4
    - **Property AR4: send_device_command without device_id short-circuits**
    - **Validates: Requirement 2.6**
    - Generator: kombinasi `face`/`sound`/`text`. Build tools dengan `device_id=None`. Asersi return dict `success=False`, `type="device_command"`, `error` non-empty, dan `device_service.queue_device_command` tidak terpanggil

- [x] 3. Phase 4 — Agent Runtime: ADK agent, fake, dispatcher
  - [x] 3.1 Implementasikan ADK agent builder di `app/agent/adk_agent.py`
    - Ekspor `build_taskbot_agent(*, model: str, tools: list)` yang membuat `google.adk.agents.Agent` bernama `taskbot_agent` tanpa `output_schema`
    - Sertakan instruction Bahasa Indonesia (≤1 kalimat output, jangan sebut nama tool/JSON, minta klarifikasi bila data hilang)
    - Import `google.adk` ditunda di file ini (jangan di `app/agent/__init__.py`)
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8_

  - [x] 3.2 Implementasikan Fake Agent runner di `app/agent/fake.py`
    - Fungsi `_run_fake(*, tools, text, timezone) -> AgentRunResult` deteksi intent berbasis keyword (`catat`/`tugas`, `makan`/`beli`/`bayar`+angka, `ingatkan`/`reminder`, `ringkasan`/`hari ini`)
    - Panggil callable dari `tools` yang sesuai; collect hasil ke `actions`
    - Bila tidak ada keyword cocok, kembalikan `AgentRunResult(reply="Maaf, aku belum mengerti perintah itu.", actions=[], device_feedback=None, status="success")`
    - Tidak boleh mengimpor modul `google.adk.*`
    - _Requirements: 3.1, 3.2, 3.6_

  - [x] 3.3 Implementasikan `runtime.run_text` dan `select_mode` di `app/agent/runtime.py`
    - `select_mode(settings)` mengikuti tabel Property AR5
    - `run_text(db, *, user_id, device_id, text, timezone)` membangun tools via `build_tools`, memilih `_run_real` atau `_run_fake`, mengembalikan `AgentRunResult`
    - `_run_real` memakai `Runner` + `InMemorySessionService` per-request; iterasi `runner.run_async(...)`, kumpulkan `function_response.response` ke `actions`, ambil teks final saat `event.is_final_response()`
    - Set `device_feedback` via helper `_pick_device_feedback`
    - _Requirements: 1.1, 1.7, 3.1, 3.2, 3.3, 3.4, 6.5_

  - [x] 3.4 Tulis property test untuk AR1 di `app/tests/test_agent_runtime.py`
    - **Property AR1: Tool Surface Identitas**
    - **Validates: Requirements 1.1, 1.3, 1.5**
    - Build agent via stub model identifier; periksa `agent.tools` punya tepat lima callable dengan `__name__` set sama dengan `{create_task, create_expense, set_reminder, get_today_summary, send_device_command}`

  - [x] 3.5 Tulis property test untuk AR5
    - **Property AR5: Mode Selection**
    - **Validates: Requirements 3.3, 3.4**
    - Hypothesis generator atas pasangan `(agent_mode, google_api_key)`; verifikasi tabel mapping di Property AR5

  - [x] 3.6 Tulis property test untuk AR6
    - **Property AR6: Fake Agent Hermeticity**
    - **Validates: Requirements 3.2, 3.5, 16.2, 16.3**
    - Setelah memanggil `_run_fake`, periksa `sys.modules` tidak mengandung `google.adk.runners`/`google.adk.agents`/`google.adk.sessions` (hanya valid bila `_run_fake` adalah satu-satunya import di test ini)

  - [x] 3.7 Tulis property test untuk AR7
    - **Property AR7: AgentRunResult device_feedback selection**
    - **Validates: Requirement 6.5**
    - Hypothesis generator atas list dict campuran `type`/`success`; asersi `_pick_device_feedback(actions)` memilih entry terakhir dengan `type=="device_command"` dan `success is True`, atau `None`

- [x] 4. Phase 4 — Manual run script
  - [x] 4.1 Implementasikan `scripts/run_agent_text.py`
    - `argparse` menerima posisi `text`, opsi `--user-id`, `--device-id` (juga membaca env `TASKBOT_USER_ID`/`TASKBOT_DEVICE_ID`)
    - Buka session via `SessionLocal()`, panggil `await run_text(...)`, print `AgentRunResult` JSON-friendly
    - Saat text kosong/whitespace: print usage ke stderr dan `sys.exit(2)`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 4.2 Tulis unit test untuk script di `app/tests/test_run_agent_text.py`
    - Verifikasi text kosong → exit non-zero + pesan ke stderr
    - Verifikasi `agent_mode == "fake"` mode berjalan tanpa import `google.adk`
    - _Requirements: 4.3, 4.4_

- [x] 5. Checkpoint — Ensure all agent runtime tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Phase 5 — `POST /agent/text` endpoint
  - [x] 6.1 Definisikan schema di `app/schemas/agent.py`
    - `AgentTextRequest`: `user_id: int`, `device_id: int | None = None`, `text: str` dengan validator non-blank, `timezone: str | None = None`
    - `AgentTextResponse`: `reply: str`, `actions: list[dict]`, `device_feedback: dict | None`
    - _Requirements: 5.1, 5.2_

  - [x] 6.2 Implementasikan `app/api/agent.py` dengan handler `POST /agent/text`
    - Validasi user/device existence (404 kalau tidak ada) sebelum memanggil runtime
    - Resolusi timezone: pakai field bila ada, fallback ke `settings.timezone`
    - Panggil `await run_text(...)` tepat sekali; pada exception persist log dengan `status="error"` lalu raise `HTTPException(500, "Agent runtime error")`
    - Sukses: persist `VoiceCommandLog` via `log_service.create_voice_command_log` (input_text, parsed_actions=result.actions, response_text=result.reply, status=result.status), kembalikan `{reply, actions, device_feedback}`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 6.3 Wire router agent ke `app/main.py`
    - `app.include_router(agent.router)` setelah router health
    - _Requirements: 5.1_

  - [x] 6.4 Tulis property test di `app/tests/test_agent_text_endpoint.py` untuk AT1
    - **Property AT1: Request validation table**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3**
    - Parametrize/hypothesis untuk: empty/whitespace text → 422; unknown user → 404; unknown device → 404; valid → 200 + tepat satu agent call + tepat satu log row. Monkeypatch `run_text` agar return deterministik

  - [x] 6.5 Tulis property test untuk AT2
    - **Property AT2: Log mirrors response**
    - **Validates: Requirements 6.2, 6.4**
    - Untuk respons 200, `VoiceCommandLog` row yang baru: `input_text == request.text`, `parsed_actions == response.actions`, `response_text == response.reply`, `status == "success"`

  - [x] 6.6 Tulis property test untuk AT3
    - **Property AT3: Error path persists log without leaking trace**
    - **Validates: Requirement 6.6**
    - Monkeypatch `run_text` agar raise; asersi 500, body tidak berisi stack trace, log row dengan `status=="error"` dan `response_text` mengandung pesan exception

  - [x] 6.7 Tulis property test untuk AT4
    - **Property AT4: device_feedback equals last successful device command action**
    - **Validates: Requirement 6.5**
    - Monkeypatch `run_text` agar mengembalikan `actions` dengan kombinasi entry; asersi `response.device_feedback` = entry terakhir bertype `device_command` & `success` True, atau `null`

- [x] 7. Phase 6 — Reminder Scheduler
  - [x] 7.1 Implementasikan WhatsApp Stub di `app/integrations/whatsapp.py`
    - `whatsapp_send_stub(reminder)` log line + return `{"sent": True, "stub": True}`
    - Tidak ada import `httpx`/`requests`/`urllib`
    - _Requirements: 8.6, 15.2_

  - [x] 7.2 Implementasikan `reminder_tick` di `app/scheduler/tick.py`
    - Signature: `reminder_tick(*, db_factory, whatsapp_send=None) -> dict` (return counters)
    - Default `whatsapp_send` ke `whatsapp_send_stub`
    - Panggil `reminder_service.list_due_reminders` sekali; iterasi setiap reminder
    - Routing channel: `device`/`both` → `device_service.queue_device_command`; `whatsapp`/`both` → `whatsapp_send`
    - Sukses semua dispatch → `mark_reminder_sent`; ada exception → catch + `mark_reminder_failed`, lanjut ke item berikutnya
    - Bila user tidak punya Device dan channel `"device"` (only) → skip dispatch, jangan transisi status
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 7.3 Implementasikan lifecycle scheduler di `app/scheduler/lifecycle.py`
    - `start_scheduler(app)` membuat `BackgroundScheduler(timezone=ZoneInfo("UTC"))`, menambahkan job `reminder_tick` dengan `trigger="interval", seconds=settings.scheduler_interval_seconds, id="reminder_tick", replace_existing=True`, lalu `start()`
    - Return scheduler agar caller bisa simpan ke `app.state.scheduler`
    - `stop_scheduler(app)` panggil `scheduler.shutdown(wait=False)` bila ada
    - _Requirements: 7.1, 7.2, 7.5, 7.7_

  - [x] 7.4 Wire FastAPI lifespan di `app/main.py`
    - Pakai `@asynccontextmanager` lifespan: pada startup, jika `settings.scheduler_enabled` → `start_scheduler` dan simpan di `app.state.scheduler`; pada shutdown, `stop_scheduler`
    - Pasang `FastAPI(lifespan=lifespan, ...)`
    - _Requirements: 7.5, 7.6, 7.7, 7.8_

  - [x] 7.5 Tulis property test di `app/tests/test_scheduler_tick.py` untuk RS2
    - **Property RS2: Tick processes all due reminders**
    - **Validates: Requirements 8.1, 8.5**
    - Hypothesis generator: list Due Reminder berukuran 0..n; mock `reminder_service.list_due_reminders`; asersi dipanggil tepat sekali dan dispatch dicoba untuk setiap reminder

  - [x] 7.6 Tulis property test untuk RS3
    - **Property RS3: Channel routing**
    - **Validates: Requirements 8.2, 8.3**
    - Hypothesis atas `channel ∈ {device, whatsapp, both}`; asersi `queue_device_command` dan `whatsapp_send` dipanggil sesuai

  - [x] 7.7 Tulis property test untuk RS4
    - **Property RS4: Status transition**
    - **Validates: Requirements 8.4, 8.5**
    - Inject `whatsapp_send` yang kadang raise; asersi reminder yang sukses → `SENT`, yang raise → `FAILED`, sisa reminder tetap diproses

  - [x] 7.8 Tulis property test untuk RS5
    - **Property RS5: No real WhatsApp call**
    - **Validates: Requirements 8.6, 15.2**
    - Bersama autouse socket kill-switch, asersi tick tidak menyentuh `httpx`/`requests`/`urllib`/host `graph.facebook.com`/`*.whatsapp.com`

  - [x] 7.9 Tulis property test untuk RS6
    - **Property RS6: Skip device-only when user has no device**
    - **Validates: Requirement 8.7**
    - Reminder `channel="device"` user tanpa Device → tidak panggil `queue_device_command`, tidak panggil whatsapp, status tetap `SCHEDULED`

  - [x] 7.10 Tulis integration test untuk RS1 (Lifecycle gating)
    - **Property RS1: Lifecycle gating**
    - **Validates: Requirements 7.5, 7.6, 7.7**
    - `with TestClient(app):` dengan `scheduler_enabled=True` → `app.state.scheduler` running; dengan `False` → tidak ada scheduler; setelah keluar context → tidak running

- [x] 8. Checkpoint — Ensure all scheduler and agent endpoint tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Phase 7 — Device Command Queue API
  - [x] 9.1 Definisikan schema di `app/schemas/devices.py`
    - `PendingCommandOut`, `AckResponse`, `DeviceStatusUpdate(status: str)`
    - _Requirements: 10.1, 11.1, 11.3_

  - [x] 9.2 Implementasikan `app/api/devices.py` dengan token dependency + tiga endpoint
    - Dependency `require_device_token` membandingkan header `X-Device-Token` dengan `settings.device_api_token`; mismatch → 401, tidak menyentuh DB
    - `GET /devices/{device_code}/commands/pending`: lookup device → 404 bila tidak ada; satu transaksi: ambil rows `PENDING` (`with_for_update()`), salin ke response, set `status=SENT` + `sent_at=now_utc()`, commit; return `[]` bila kosong
    - `POST /devices/{device_code}/commands/{command_id}/ack`: cek device + command (id milik device); panggil `device_service.ack_device_command`; return `{"success": true, "command_id": <id>}`; mismatch device atau command tidak ada → 404
    - `POST /devices/{device_code}/status`: validasi `status ∈ {online, offline}` (else 422); panggil `device_service.update_device_status`; return `{status, last_seen_at}`
    - Tidak melog nilai header token di response/log line
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 11.1, 11.2, 11.3, 11.4_

  - [x] 9.3 Wire router devices ke `app/main.py`
    - `app.include_router(devices.router)`
    - _Requirements: 9.1_

  - [x] 9.4 Tulis property test di `app/tests/test_devices_api.py` untuk DA1
    - **Property DA1: Token check precedes lookup**
    - **Validates: Requirements 9.2, 9.4**
    - Generator atas tiga route + header token salah/kosong; asersi 401 dan tidak ada baris DB yang dimutasi (snapshot before/after)

  - [x] 9.5 Tulis property test untuk DA2
    - **Property DA2: Unknown device_code → 404**
    - **Validates: Requirement 9.3**
    - Token valid, `device_code` random non-existent; asersi 404 untuk ketiga route

  - [x] 9.6 Tulis property test untuk DA3
    - **Property DA3: Atomic Mark-Sent invariant**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
    - Seed n Pending Command; `poll_1` lalu `poll_2`; asersi `poll_1` berisi semua pending dan setiap row yang dikembalikan kini `SENT` + `sent_at` set; `poll_2.body == []`

  - [x] 9.7 Tulis property test untuk DA4
    - **Property DA4: Ack happy-path and not-found**
    - **Validates: Requirements 11.1, 11.2**
    - Existing command_id milik device → 200 + transition ke `ACKNOWLEDGED`; command_id tidak ada / milik device lain → 404 + tidak ada mutasi

  - [x] 9.8 Tulis property test untuk DA5
    - **Property DA5: Status update validation**
    - **Validates: Requirements 11.3, 11.4**
    - Hypothesis untuk `payload.status`: anggota set valid → 200 + `status` & `last_seen_at` ter-update; di luar set → 422 + tidak ada mutasi

- [x] 10. Phase 8 — Minimal Dashboard API
  - [x] 10.1 Tambahkan helper `update_task` dan `delete_task` di `app/services/task_service.py`
    - `update_task(db, task_id, **patch)` hanya menerapkan field non-None; reuse validasi `create_task` (datetime aware, title non-blank, dll); `NotFoundError` bila task tidak ada
    - `delete_task(db, task_id)` hapus row; `NotFoundError` bila tidak ada
    - _Requirements: 12.4, 12.6, 12.7_

  - [x] 10.2 Definisikan schema di `app/schemas/dashboard.py`
    - `TaskOut`, `TaskPatch` (semua field optional), `ExpenseIn`, `ExpenseOut`, `SummaryOut(tasks_due_today, total_expenses_today)`, `LogOut`, `DeviceOut`
    - _Requirements: 12.1, 12.3, 13.1, 13.2, 13.3, 13.4, 13.5_

  - [x] 10.3 Implementasikan `app/api/dashboard.py` dengan auth dependency dan endpoint
    - Dependency `require_dashboard_auth` mengikuti `settings.dashboard_auth_mode` (`"none"` lewatkan; `"shared_header"` cek header `X-Dashboard-Token`)
    - `GET /dashboard/tasks` (`user_id`, optional `status`) → `task_service.list_tasks`
    - `PATCH /dashboard/tasks/{task_id}` → `task_service.update_task`
    - `DELETE /dashboard/tasks/{task_id}` → `task_service.delete_task`, return 204
    - `GET /dashboard/expenses` (`user_id`, optional `start_at`/`end_at` ISO 8601) → `expense_service.list_expenses`
    - `POST /dashboard/expenses` → `expense_service.create_expense`, return 201
    - `GET /dashboard/summary?user_id` reuse `get_today_summary_tool` (sama window Asia/Jakarta calendar-day)
    - `GET /dashboard/logs?user_id` ordered desc `created_at`
    - `GET /dashboard/devices?user_id` rows milik user
    - Validasi user existence → 404 untuk semua endpoint
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 14.1, 14.2, 14.3_

  - [x] 10.4 Tambahkan global exception handlers dan wire router dashboard
    - Buat `app/api/_errors.py` dengan handler untuk `ValidationError` → 422, `NotFoundError` → 404, `PermissionDeniedError` → 403
    - Daftarkan handler di `app/main.py` via `app.add_exception_handler(...)` dan `app.include_router(dashboard.router)`
    - _Requirements: 12.7, 13.6, 13.7_

  - [x] 10.5 Tulis property test di `app/tests/test_dashboard_api.py` untuk DB1
    - **Property DB1: User existence gate**
    - **Validates: Requirement 13.6**
    - Hypothesis atas semua endpoint dashboard; `user_id` random tidak ada → 404, tidak ada mutasi

  - [x] 10.6 Tulis property test untuk DB2
    - **Property DB2: List endpoints reflect service results**
    - **Validates: Requirements 12.1, 12.2, 13.1, 13.3**
    - Untuk seed task/expense/summary, response endpoint = serialisasi service result

  - [x] 10.7 Tulis property test untuk DB3
    - **Property DB3: Patch applies only supplied fields**
    - **Validates: Requirement 12.4**
    - Hypothesis subset field `TaskPatch`; asersi field S ter-update, field di luar S tetap pre-patch

  - [x] 10.8 Tulis property test untuk DB4
    - **Property DB4: Delete behavior**
    - **Validates: Requirements 12.6, 12.7**
    - Existing task_id → 204 + row hilang; missing → 404 + tidak ada mutasi

  - [x] 10.9 Tulis property test untuk DB5
    - **Property DB5: Validation propagation**
    - **Validates: Requirement 13.7**
    - Hypothesis input invalid (amount <= 0, naive datetime) → 422 + tidak ada mutasi

  - [x] 10.10 Tulis property test untuk DB6
    - **Property DB6: Auth mode behavior**
    - **Validates: Requirements 14.2, 14.3**
    - `dashboard_auth_mode="none"` → request tanpa header sukses; `="shared_header"` → tanpa/wrong token → 401, dengan token benar → sukses

- [x] 11. Cross-cutting tests
  - [x] 11.1 Tambahkan autouse network kill-switch di `app/tests/conftest.py`
    - Fixture `autouse=True` memonkeypatch `socket.socket` agar test default tidak bisa membuat outbound connection (skip untuk `127.0.0.1`/loopback bila perlu untuk TestClient — atau monkeypatch hanya `getaddrinfo` ke disallow non-local hosts)
    - **Validates: Properties AR6, RS5, X1 (Requirements 3.5, 8.6, 16.2, 16.3)**

  - [x] 11.2 Tulis property test untuk X2 di `app/tests/test_schema_invariant.py`
    - **Property X2: Schema unchanged**
    - **Validates: Requirement 15.8**
    - Snapshot set `(table_name, column_name, type)` dari `Base.metadata.tables` setelah Phase 4–8 = referensi Phase 3

- [x] 12. Documentation updates
  - [x] 12.1 Update `docs/AGENT_DESIGN.md`
    - Catat bahwa Tool Surface adalah Google ADK tools yang membungkus tool wrapper Phase 3, dan Fake Agent dipakai untuk test
    - _Requirements: 18.1_

  - [x] 12.2 Update `README.md`
    - Tambahkan: cara menjalankan `python -m scripts.run_agent_text`, cara mengaktifkan scheduler (`SCHEDULER_ENABLED=true`), cara memanggil `POST /agent/text`
    - _Requirements: 18.2_

  - [x] 12.3 Update `docs/ROADMAP.md`
    - Pindahkan marker `(Current)` ke Phase 8 (atau phase paling lanjut yang dirilis)
    - _Requirements: 18.3_

  - [x] 12.4 Catat keputusan `dashboard_auth_mode` MVP di `docs/ARCHITECTURE.md`
    - Pilihan terpilih: `"none"`, alasan: dashboard berjalan di lokal/VPS internal pada Phase 8; jalur `"shared_header"` tetap tersedia tanpa refactor saat dashboard publik
    - _Requirements: 14.4, 18.4_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks (including property tests) are required for this spec.
- Each task references specific sub-requirements (clause numbers) for traceability.
- Property-based tests cover universal correctness properties from `design.md`. Unit/integration tests inside the same files cover edge cases and example-based scenarios.
- Tool wrappers Phase 3 are not modified; only `task_service` gains additive helpers `update_task` and `delete_task`.
- Scheduler tick is a pure function for hermetic testing; `BackgroundScheduler` start/stop is gated by `settings.scheduler_enabled`.
- Phase 8 dashboard auth defaults to `"none"`; switching to `"shared_header"` is config-only.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "7.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "3.2", "6.1", "7.2", "9.1", "10.1", "10.2"] },
    { "id": 3, "tasks": ["3.3", "7.3", "9.2"] },
    { "id": 4, "tasks": ["4.1", "6.2", "10.3", "11.1"] },
    { "id": 5, "tasks": ["6.3"] },
    { "id": 6, "tasks": ["7.4"] },
    { "id": 7, "tasks": ["9.3"] },
    { "id": 8, "tasks": ["10.4"] },
    { "id": 9, "tasks": ["2.3", "4.2", "6.4", "7.5", "9.4", "10.5", "11.2", "12.1", "12.2", "12.3", "12.4"] },
    { "id": 10, "tasks": ["2.4", "6.5", "7.6", "9.5", "10.6"] },
    { "id": 11, "tasks": ["2.5", "6.6", "7.7", "9.6", "10.7"] },
    { "id": 12, "tasks": ["3.4", "6.7", "7.8", "9.7", "10.8"] },
    { "id": 13, "tasks": ["3.5", "7.9", "9.8", "10.9"] },
    { "id": 14, "tasks": ["3.6", "7.10", "10.10"] },
    { "id": 15, "tasks": ["3.7"] }
  ]
}
```

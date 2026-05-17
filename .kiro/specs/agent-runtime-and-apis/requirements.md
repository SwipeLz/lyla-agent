# Requirements Document

## Introduction

Spec gabungan ini mencakup Phase 4 sampai Phase 8 dari roadmap backend Taskbot. Phase 0–3 sudah selesai dan tidak boleh diulang: planning docs, FastAPI skeleton + `GET /health`, SQLAlchemy models + migrasi Alembic + SQLite + seed, dan **Service Layer + Tool Wrapper Layer** (62 tes lulus).

Yang ditambahkan di spec ini, di atas Phase 3 yang sudah ada:

- **Phase 4 — Google ADK Agent Runtime**: satu agent `taskbot_agent` (Bahasa Indonesia, jawaban satu kalimat) yang membungkus tool wrapper Phase 3 sebagai Google ADK tools, plus jalur fake/mock agent untuk CI tanpa `GOOGLE_API_KEY`.
- **Phase 5 — `POST /agent/text`**: endpoint HTTP yang memvalidasi user/device/text, menjalankan agent runner, mengeksekusi tools, mencatat `VoiceCommandLog`, dan mengembalikan reply + actions + device feedback.
- **Phase 6 — Reminder Scheduler**: APScheduler `BackgroundScheduler` dengan satu job periodik (default 60s) yang memproses Due Reminder lewat WhatsApp Stub dan device command queue.
- **Phase 7 — Device Command Queue API**: tiga endpoint untuk ESP32 dilindungi header `X-Device-Token` (pending poll dengan Atomic Mark-Sent, ack per command, status update).
- **Phase 8 — Minimal Dashboard API**: read/write endpoint untuk task, expense, summary, log, dan device, untuk konsumsi internal/dev (model auth ditandai sebagai open decision).

Spec ini tidak mengulang Service Layer atau Tool Wrapper Layer — keduanya direferensikan dari `.kiro/specs/service-layer/`. Tool wrapper baru tidak ditambahkan di spec ini; yang dilakukan Phase 4 adalah membungkus wrapper yang sudah ada sebagai ADK tools dengan **Injected Context** lewat closure/partial/factory.

Verifikasi Google ADK API resmi (paket, kelas `Agent`, `FunctionTool`, `Runner`, `SessionService`, integrasi FastAPI, perilaku `output_schema`) **ditangguhkan ke fase design** — di fase requirements ini hanya nama-nama dan kontrak yang ditetapkan; pemilihan API akhir akan diverifikasi via Google Developer Knowledge MCP sebelum tasks dibuat.

## Glossary

Istilah dari `.kiro/specs/service-layer/requirements.md` (`Service Layer`, `Tool Wrapper Layer`, `Task Service`, `Expense Service`, `Reminder Service`, `Device Service`, `Log Service`, `Service Exceptions`, `Aware Datetime`, `UTC Now`, `Status Constants`, `Channel`, `Pending Command`, `Due Reminder`, `Tool Result Dict`) **direuse apa adanya** dan tidak diredefinisi di sini.

Istilah baru yang diperkenalkan spec ini:

- **Agent Runtime**: Modul Python di `app/agent/` yang membangun dan menjalankan satu Google ADK agent bernama `taskbot_agent`. Mengekspos minimal: builder agent, builder tool list per request, dan fungsi runner sinkron yang menerima `(db, user_id, device_id, text)` dan mengembalikan `AgentRunResult`.
- **Tool Surface**: Himpunan persis lima tool yang terdaftar pada `taskbot_agent`: `create_task`, `create_expense`, `set_reminder`, `get_today_summary`, `send_device_command`. Set ini tetap; tidak boleh ada tool tambahan yang model-visible di Phase 4–8.
- **Model-Visible Argument**: Argumen sebuah tool yang muncul di skema fungsi yang dilihat model LLM. Hanya parameter primitif/JSON-friendly bisnis (mis. `title`, `amount`, `remind_at`) boleh menjadi Model-Visible Argument.
- **Injected Context**: Nilai-nilai yang ditambahkan oleh Agent Runtime ke pemanggilan tool wrapper di sisi server (`db: Session`, `user_id: int`, `device_id: int | None`) dan tidak boleh muncul di skema tool yang dilihat model.
- **Per-Request Tool Factory**: Fungsi di Agent Runtime yang menerima Injected Context dan mengembalikan list tool ADK yang sudah di-bind ke konteks tersebut (closure, `functools.partial`, atau equivalent). Dipanggil sekali per invocation `POST /agent/text`.
- **AgentRunResult**: Dataclass/dict dengan field `reply: str`, `actions: list[ToolResultDict]`, `device_feedback: dict | None`, `status: str` (`"success"` atau `"error"`), `error: str | None`.
- **Fake Agent**: Implementasi alternatif Agent Runtime yang **tidak** memanggil Gemini, dipakai oleh test dan oleh konfigurasi `app_env != "production"` ketika `GOOGLE_API_KEY` kosong. Fake Agent meng-deteksi intent berdasarkan keyword sederhana atau berdasarkan injection eksplisit dari test, lalu memanggil tool wrapper yang sama dengan Agent Runtime sebenarnya.
- **Agent Mode**: Konfigurasi runtime yang memilih antara `"real"` (Google ADK) dan `"fake"` (Fake Agent). Dikontrol via setting `agent_mode` (default `"fake"` saat `GOOGLE_API_KEY` kosong, `"real"` saat tersedia, dapat dioverride oleh test).
- **Voice Command Log Record**: Baris baru di tabel `VoiceCommandLog` yang dibuat oleh `POST /agent/text` melalui `Log Service`, berisi `input_text`, `parsed_actions` (list Tool Result Dict), `response_text`, `status`, `user_id`, `device_id`.
- **Reminder Scheduler**: Modul Python di `app/scheduler/` yang membungkus APScheduler `BackgroundScheduler`, mendaftarkan satu Scheduler Tick periodik, dan terikat ke lifecycle FastAPI startup/shutdown.
- **Scheduler Tick**: Satu eksekusi job periodik Reminder Scheduler. Setiap tick: query Due Reminder, untuk channel `device`/`both` panggil `device_service.queue_device_command`, untuk channel `whatsapp`/`both` panggil WhatsApp Stub, lalu `mark_reminder_sent` atau `mark_reminder_failed`.
- **Scheduler Interval**: Periode antar Scheduler Tick dalam detik. Dikontrol via setting `scheduler_interval_seconds` (default 60).
- **Scheduler Enabled Flag**: Setting boolean `scheduler_enabled` (default `False` di test/development, `True` di production). Saat `False`, scheduler tidak start meskipun aplikasi start.
- **WhatsApp Stub**: Fungsi Python di `app/integrations/whatsapp.py` yang **tidak** memanggil Cloud API mana pun. Default: log line + return `{"sent": True, "stub": True}`. Test boleh memonkeypatch ke perilaku error.
- **Device Token**: Nilai string dari `settings.device_api_token`. Dikirim oleh ESP32 sebagai HTTP header `X-Device-Token` pada Phase 7 endpoints.
- **Device Token Header**: HTTP header `X-Device-Token` yang nilainya harus persis sama dengan Device Token agar Phase 7 endpoint memproses request.
- **Atomic Mark-Sent**: Operasi pada `GET /devices/{device_code}/commands/pending` yang dalam satu transaksi DB: (a) mengambil semua Pending Command untuk device, (b) menyalin payload-nya ke response, (c) men-set status setiap command tersebut ke `DeviceCommandStatus.SENT` dan `sent_at = UTC Now`. Properti yang harus dijaga: dua poll berurutan untuk device yang sama tanpa Pending Command baru di antaranya menghasilkan response kedua kosong.
- **Dashboard Endpoint**: HTTP route di `app/api/dashboard.py` yang melayani konsumen internal/dev (web dashboard, debug CLI). Tidak melalui Agent Runtime; memanggil Service Layer langsung.
- **Dashboard Auth Mode**: Konfigurasi setting `dashboard_auth_mode` dengan nilai `"none"` (tanpa header, untuk MVP) atau `"shared_header"` (header `X-Dashboard-Token` harus cocok). Default dan keputusan akhir antara keduanya adalah **open decision** yang harus ditandai eksplisit di design.
- **Project Documentation**: File `README.md`, `docs/AGENT_DESIGN.md`, dan `docs/ROADMAP.md` di root proyek.

## Requirements

### Requirement 1: Agent Runtime: Single Agent and Tool Surface (Phase 4)

**User Story:** As a backend developer, I want a single Google ADK agent named `taskbot_agent` that exposes exactly five tools using the Phase 3 tool wrappers, so that text commands are routed to existing business logic without duplicating it.

#### Acceptance Criteria

1. THE Agent Runtime SHALL define exactly one ADK agent identified by the name `taskbot_agent`.
2. THE Agent Runtime SHALL configure `taskbot_agent` to use the Gemini model whose identifier equals `settings.google_adk_model`.
3. THE Agent Runtime SHALL register on `taskbot_agent` exactly the five tools forming the Tool Surface: `create_task`, `create_expense`, `set_reminder`, `get_today_summary`, `send_device_command`.
4. THE Agent Runtime SHALL implement each tool of the Tool Surface as a thin adapter that calls the corresponding Phase 3 tool wrapper from `app/tools/` and returns the resulting Tool Result Dict.
5. THE Agent Runtime SHALL NOT register any tool outside the Tool Surface on `taskbot_agent`.
6. THE Agent Runtime SHALL provide `taskbot_agent` with an Indonesian-language system instruction that constrains its responses to a single concise sentence appropriate for device-style output.
7. WHERE `agent_mode == "real"`, THE Agent Runtime SHALL construct `taskbot_agent` using the Google ADK Python SDK (`google.adk` package).
8. THE Agent Runtime SHALL NOT use LangChain, OpenClaw, ESP-Claw, Dify, or Flowise.

### Requirement 2: Agent Runtime: Tool Injection Contract (Phase 4 cross-cutting)

**User Story:** As a backend developer, I want the agent's tool schemas to expose only business arguments while infrastructure context is injected server-side, so that the model cannot fabricate or override `db`, `user_id`, or `device_id`.

#### Acceptance Criteria

1. THE Tool Surface SHALL expose to the model only the following Model-Visible Arguments per tool:
   - `create_task`: `title`, `course`, `deadline_at`, `reminder_at`, `priority`
   - `create_expense`: `amount`, `category`, `note`, `spent_at`
   - `set_reminder`: `title`, `remind_at`, `channel`, `task_id`
   - `get_today_summary`: (no arguments)
   - `send_device_command`: `face`, `sound`, `text`
2. THE Tool Surface SHALL NOT expose `db`, `user_id`, or `device_id` as Model-Visible Arguments on any tool.
3. THE Per-Request Tool Factory SHALL produce the tool list for one invocation by binding `db`, `user_id`, and `device_id` into each tool via closure, `functools.partial`, or an equivalent mechanism that prevents the model from supplying those values.
4. WHEN the Agent Runtime executes a tool of the Tool Surface during a single invocation, THE Agent Runtime SHALL forward the bound `db`, `user_id`, and `device_id` to the underlying Phase 3 tool wrapper without modification.
5. IF the model attempts to call a Tool Surface tool with an argument named `db`, `user_id`, or `device_id`, THEN THE Agent Runtime SHALL ignore that argument and SHALL use the Injected Context value instead.
6. WHERE the underlying tool wrapper is `send_device_command_tool` and `device_id` is `None`, THE Agent Runtime SHALL return a Tool Result Dict with `success = False`, `type = "device_command"`, and a non-empty `error`, and SHALL NOT call `device_service.queue_device_command`.

### Requirement 3: Agent Runtime: Fake Agent for Tests and CI (Phase 4 cross-cutting)

**User Story:** As a CI maintainer, I want the default test run to never call the real Gemini API, so that tests pass without `GOOGLE_API_KEY` and without external network access.

#### Acceptance Criteria

1. THE Agent Runtime SHALL provide a Fake Agent implementation that conforms to the same runner signature as the real agent and returns an `AgentRunResult`.
2. WHERE `agent_mode == "fake"`, THE Agent Runtime SHALL select the Fake Agent for all invocations and SHALL NOT import or initialize Google ADK clients that would require a network call.
3. WHEN the application starts and `settings.google_api_key` is empty, THE Agent Runtime SHALL default `agent_mode` to `"fake"`.
4. WHEN the application starts and `settings.google_api_key` is non-empty, THE Agent Runtime SHALL default `agent_mode` to `"real"`.
5. THE Test Suite SHALL be runnable end-to-end with `GOOGLE_API_KEY` unset and SHALL NOT make outbound network calls during a default `pytest` run.
6. THE Fake Agent SHALL invoke the same Phase 3 tool wrappers via the same Per-Request Tool Factory, so that side effects on the database and Tool Result Dicts are byte-for-byte equivalent to the real agent for the inputs the Fake Agent supports.

### Requirement 4: Agent Runtime: Manual Run Script (Phase 4)

**User Story:** As a backend developer, I want a CLI script to invoke the agent against a single text command, so that I can smoke-test the agent end-to-end without HTTP.

#### Acceptance Criteria

1. THE Project SHALL include a Python entry point invocable as `python -m scripts.run_agent_text "<text>"`.
2. WHEN `python -m scripts.run_agent_text "<text>"` is invoked with a non-empty `<text>` argument, THE Script SHALL open a database session against `settings.database_url`, resolve a developer `user_id` (via CLI flag or environment variable), invoke the Agent Runtime with that text, and print the resulting `AgentRunResult` to stdout in human-readable form.
3. IF `python -m scripts.run_agent_text` is invoked with no text argument, THEN THE Script SHALL exit with a non-zero status code and print a usage message to stderr.
4. WHERE `agent_mode == "fake"`, THE Script SHALL run successfully without contacting any external API.

### Requirement 5: `POST /agent/text` Endpoint: Request Validation (Phase 5)

**User Story:** As a frontend or device client, I want a single HTTP endpoint that accepts a text command and returns a structured reply, so that I can integrate without knowing about the agent runtime internals.

#### Acceptance Criteria

1. THE FastAPI Application SHALL expose a route `POST /agent/text` that accepts JSON with fields `user_id: int`, `device_id: int | None` (optional), `text: str`, and `timezone: str | None` (optional).
2. WHEN `POST /agent/text` is called with a `text` that is empty or contains only whitespace, THE FastAPI Application SHALL return HTTP 422 and SHALL NOT invoke the Agent Runtime.
3. WHEN `POST /agent/text` is called with a `user_id` that does not match an existing `User`, THE FastAPI Application SHALL return HTTP 404 and SHALL NOT invoke the Agent Runtime.
4. WHEN `POST /agent/text` is called with a non-`None` `device_id` that does not match an existing `Device`, THE FastAPI Application SHALL return HTTP 404 and SHALL NOT invoke the Agent Runtime.
5. WHERE the request body field `timezone` is supplied with a non-empty string, THE FastAPI Application SHALL pass that timezone to the Agent Runtime invocation context; otherwise THE FastAPI Application SHALL fall back to `settings.timezone`.

### Requirement 6: `POST /agent/text` Endpoint: Behavior and Logging (Phase 5)

**User Story:** As a developer, I want every agent call to be logged and to return the agent's reply, the tool actions executed, and any device feedback, so that the API is debuggable and observable.

#### Acceptance Criteria

1. WHEN `POST /agent/text` is called with valid request data, THE FastAPI Application SHALL invoke the Agent Runtime exactly once with the resolved `db`, `user_id`, `device_id`, `text`, and timezone, and SHALL receive an `AgentRunResult`.
2. WHEN the Agent Runtime returns an `AgentRunResult`, THE FastAPI Application SHALL persist exactly one Voice Command Log Record via `log_service.create_voice_command_log` with `input_text = request.text`, `parsed_actions = result.actions`, `response_text = result.reply`, and `status = result.status`.
3. WHEN persistence of the Voice Command Log Record succeeds, THE FastAPI Application SHALL respond with HTTP 200 and a JSON body containing keys `reply: str`, `actions: list`, and `device_feedback: object | null`.
4. THE response field `actions` SHALL equal `result.actions` and SHALL contain only Tool Result Dicts produced by the Phase 3 tool wrappers during this invocation, in invocation order.
5. THE response field `device_feedback` SHALL contain the most recent successful `send_device_command` Tool Result Dict from `result.actions` if any exists, otherwise SHALL be `null`.
6. IF the Agent Runtime raises an unhandled exception, THEN THE FastAPI Application SHALL return HTTP 500, SHALL persist a Voice Command Log Record with `status = "error"` and `response_text` containing the exception message, and SHALL NOT propagate raw stack traces to the client body.

### Requirement 7: Reminder Scheduler: Configuration and Lifecycle (Phase 6)

**User Story:** As a backend operator, I want a background scheduler that processes due reminders periodically, gated by a config flag, so that production runs notifications and tests do not.

#### Acceptance Criteria

1. THE Reminder Scheduler SHALL use APScheduler `BackgroundScheduler`.
2. THE Reminder Scheduler SHALL register exactly one periodic job whose trigger interval equals `settings.scheduler_interval_seconds`.
3. THE Project Configuration SHALL define `scheduler_interval_seconds: int` with default value `60`.
4. THE Project Configuration SHALL define `scheduler_enabled: bool` with default value `False`.
5. WHEN the FastAPI application startup event runs and `settings.scheduler_enabled` is `True`, THE Reminder Scheduler SHALL start its `BackgroundScheduler`.
6. WHEN the FastAPI application startup event runs and `settings.scheduler_enabled` is `False`, THE Reminder Scheduler SHALL NOT start its `BackgroundScheduler`.
7. WHEN the FastAPI application shutdown event runs, THE Reminder Scheduler SHALL shut down its `BackgroundScheduler` if it was started.
8. THE Test Suite SHALL run with `scheduler_enabled = False` by default.

### Requirement 8: Reminder Scheduler: Tick Behavior (Phase 6)

**User Story:** As a user, I want due reminders to be dispatched to the device queue and to WhatsApp according to their channel, so that I receive notifications.

#### Acceptance Criteria

1. WHEN a Scheduler Tick runs, THE Reminder Scheduler SHALL retrieve the list of Due Reminders via `reminder_service.list_due_reminders`.
2. WHEN a Scheduler Tick processes a Due Reminder whose `channel` is `"device"` or `"both"`, THE Reminder Scheduler SHALL invoke `device_service.queue_device_command` for the device associated with the reminder's user.
3. WHEN a Scheduler Tick processes a Due Reminder whose `channel` is `"whatsapp"` or `"both"`, THE Reminder Scheduler SHALL invoke the WhatsApp Stub for that reminder.
4. WHERE all dispatch calls for a Due Reminder return without raising, THE Reminder Scheduler SHALL invoke `reminder_service.mark_reminder_sent` for that reminder.
5. IF any dispatch call for a Due Reminder raises an exception, THEN THE Reminder Scheduler SHALL catch the exception, invoke `reminder_service.mark_reminder_failed` for that reminder, and continue processing remaining Due Reminders within the same tick.
6. THE Reminder Scheduler SHALL NOT call any real WhatsApp Cloud API endpoint at any time.
7. WHERE a Due Reminder's user has no associated `Device`, THE Reminder Scheduler SHALL skip device-channel dispatch for that reminder and continue with WhatsApp dispatch if applicable.

### Requirement 9: Device Command Queue API: Authentication (Phase 7)

**User Story:** As a security-conscious operator, I want the device-facing endpoints to require a shared token, so that an unauthenticated public client cannot drain the command queue or impersonate the device.

#### Acceptance Criteria

1. THE FastAPI Application SHALL expose three device-facing routes: `GET /devices/{device_code}/commands/pending`, `POST /devices/{device_code}/commands/{command_id}/ack`, and `POST /devices/{device_code}/status`.
2. WHEN any of the three device-facing routes is called without a Device Token Header or with a Device Token Header whose value differs from `settings.device_api_token`, THE FastAPI Application SHALL return HTTP 401 and SHALL NOT mutate any database row.
3. WHEN any of the three device-facing routes is called with `device_code` that does not match any `Device`, THE FastAPI Application SHALL return HTTP 404.
4. THE FastAPI Application SHALL NOT log the value of the Device Token Header in any response, error message, or log line.

### Requirement 10: Device Command Queue API: Pending Poll (Phase 7)

**User Story:** As an ESP32 device, I want one HTTP call to retrieve and consume my pending commands atomically, so that I never duplicate command execution after a successful poll.

#### Acceptance Criteria

1. WHEN `GET /devices/{device_code}/commands/pending` is called with a valid Device Token Header and an existing `device_code`, THE FastAPI Application SHALL perform an Atomic Mark-Sent and return HTTP 200 with a JSON list of objects, each containing fields `command_id: int`, `command_type: str`, `payload: object`, and `created_at: str`.
2. THE Atomic Mark-Sent SHALL include in its response only the commands whose status was `DeviceCommandStatus.PENDING` immediately before the operation.
3. WHEN `GET /devices/{device_code}/commands/pending` is called twice in succession with no new Pending Command queued in between, THE second response SHALL be an empty list `[]`.
4. WHILE the Atomic Mark-Sent is in progress, THE FastAPI Application SHALL hold a single database transaction that both reads pending rows and writes their `status = SENT` and `sent_at = UTC Now`, so that no concurrent caller observes a partially-updated state.

### Requirement 11: Device Command Queue API: Ack and Status (Phase 7)

**User Story:** As an ESP32 device, I want to acknowledge command execution and report my online/offline status, so that the backend can track liveness and command lifecycle.

#### Acceptance Criteria

1. WHEN `POST /devices/{device_code}/commands/{command_id}/ack` is called with a valid Device Token Header, an existing `device_code`, and a `command_id` belonging to that device, THE FastAPI Application SHALL invoke `device_service.ack_device_command` and return HTTP 200 with a JSON body `{"success": true, "command_id": <command_id>}`.
2. IF `POST /devices/{device_code}/commands/{command_id}/ack` is called with a `command_id` that does not exist or does not belong to the supplied `device_code`, THEN THE FastAPI Application SHALL return HTTP 404 and SHALL NOT mutate any row.
3. WHEN `POST /devices/{device_code}/status` is called with a valid Device Token Header, an existing `device_code`, and a JSON body `{"status": "<value>"}` where `<value>` is in `{"online", "offline"}`, THE FastAPI Application SHALL invoke `device_service.update_device_status` and return HTTP 200 with a JSON body containing the updated `status` and `last_seen_at`.
4. IF `POST /devices/{device_code}/status` is called with a `status` value outside `{"online", "offline"}`, THEN THE FastAPI Application SHALL return HTTP 422 and SHALL NOT mutate any row.

### Requirement 12: Dashboard API: Tasks (Phase 8)

**User Story:** As a dashboard developer, I want HTTP endpoints to list, update, and delete tasks for a user, so that the dashboard frontend can manage tasks without re-implementing service logic.

#### Acceptance Criteria

1. THE FastAPI Application SHALL expose `GET /dashboard/tasks` accepting query parameters `user_id: int` (required) and `status: str` (optional).
2. WHEN `GET /dashboard/tasks` is called with a valid `user_id`, THE FastAPI Application SHALL return HTTP 200 with a JSON list of tasks for that user, optionally filtered by `status`, using `task_service.list_tasks`.
3. THE FastAPI Application SHALL expose `PATCH /dashboard/tasks/{task_id}` accepting a JSON body with optional fields `status`, `title`, `course`, `deadline_at`, `reminder_at`, `priority`.
4. WHEN `PATCH /dashboard/tasks/{task_id}` is called with a `task_id` that exists and a JSON body whose fields satisfy the same validation rules as `task_service.create_task`, THE FastAPI Application SHALL update only the supplied fields and return HTTP 200 with the updated task.
5. THE FastAPI Application SHALL expose `DELETE /dashboard/tasks/{task_id}` that deletes the task by id.
6. WHEN `DELETE /dashboard/tasks/{task_id}` is called with a `task_id` that exists, THE FastAPI Application SHALL delete that task row and return HTTP 204.
7. IF `PATCH /dashboard/tasks/{task_id}` or `DELETE /dashboard/tasks/{task_id}` is called with a `task_id` that does not exist, THEN THE FastAPI Application SHALL return HTTP 404 and SHALL NOT mutate any row.

### Requirement 13: Dashboard API: Expenses, Summary, Logs, Devices (Phase 8)

**User Story:** As a dashboard developer, I want endpoints to read and create expenses, fetch a daily summary, list voice command logs, and list devices for a user, so that the dashboard frontend can show the full picture without bypassing the service layer.

#### Acceptance Criteria

1. THE FastAPI Application SHALL expose `GET /dashboard/expenses` accepting query parameters `user_id: int` (required), `start_at: str` (optional ISO 8601), `end_at: str` (optional ISO 8601), and SHALL return the result of `expense_service.list_expenses` for those bounds.
2. THE FastAPI Application SHALL expose `POST /dashboard/expenses` accepting a JSON body with fields `user_id: int`, `amount: int`, and optional `category`, `note`, `spent_at`, and SHALL return HTTP 201 with the created expense after invoking `expense_service.create_expense`.
3. THE FastAPI Application SHALL expose `GET /dashboard/summary` accepting query parameter `user_id: int`, and SHALL return a JSON object with `tasks_due_today: int` and `total_expenses_today: int` computed using the same Asia/Jakarta calendar-day window as `get_today_summary_tool`.
4. THE FastAPI Application SHALL expose `GET /dashboard/logs` accepting query parameter `user_id: int`, and SHALL return the matching `VoiceCommandLog` rows ordered by most recent first.
5. THE FastAPI Application SHALL expose `GET /dashboard/devices` accepting query parameter `user_id: int`, and SHALL return the `Device` rows belonging to that user.
6. WHEN any Dashboard Endpoint is called with a `user_id` that does not match an existing `User`, THE FastAPI Application SHALL return HTTP 404.
7. IF any Dashboard Endpoint receives a request whose body or query violates Service Layer validation rules (for example `amount <= 0`, naive datetime), THEN THE FastAPI Application SHALL return HTTP 422 and SHALL NOT mutate any row.

### Requirement 14: Dashboard API: Authentication Decision (Phase 8 open decision)

**User Story:** As a project lead, I want the Dashboard API authentication model to be an explicit, recorded decision rather than an accidental default, so that the security posture of the dashboard is intentional.

#### Acceptance Criteria

1. THE Project Configuration SHALL define `dashboard_auth_mode` with allowed values `"none"` and `"shared_header"` and a documented default.
2. WHERE `dashboard_auth_mode == "none"`, THE FastAPI Application SHALL serve all Dashboard Endpoints without checking any authentication header.
3. WHERE `dashboard_auth_mode == "shared_header"`, THE FastAPI Application SHALL require an `X-Dashboard-Token` header on every Dashboard Endpoint, whose value must equal a configured token, and SHALL return HTTP 401 on mismatch.
4. THE Design Document SHALL flag the choice between `"none"` and `"shared_header"` as an Open Decision and SHALL state which mode is selected for MVP and the rationale.

### Requirement 15: Cross-Cutting: Scope Boundaries (Non-Goals)

**User Story:** As a project maintainer, I want the boundaries of this combined spec to be explicit, so that subsequent phases stay independently deliverable.

#### Acceptance Criteria

1. THE Combined Phase 4–8 Deliverable SHALL NOT introduce audio recording, speech-to-text, or text-to-speech functionality.
2. THE Combined Phase 4–8 Deliverable SHALL NOT call any real WhatsApp Cloud API endpoint; the WhatsApp Stub SHALL be the only WhatsApp-shaped integration.
3. THE Combined Phase 4–8 Deliverable SHALL NOT introduce a long-term AI memory store or vector database.
4. THE Combined Phase 4–8 Deliverable SHALL NOT introduce frontend code or ESP32 firmware.
5. THE Combined Phase 4–8 Deliverable SHALL NOT add LangChain, OpenClaw, ESP-Claw, Dify, or Flowise to `requirements.txt` or to any source file.
6. THE Combined Phase 4–8 Deliverable SHALL NOT change SQLite as the default database; `database_url` SHALL continue to default to a SQLite URL.
7. THE Combined Phase 4–8 Deliverable SHALL NOT hardcode secrets in source files; values such as `device_api_token`, dashboard tokens, and `google_api_key` SHALL be read from configuration only.
8. THE Combined Phase 4–8 Deliverable SHALL NOT modify Phase 2 database schema columns; new tables or columns are out of scope unless explicitly added to a later requirement in this document.

### Requirement 16: Cross-Cutting: Test Policy

**User Story:** As a CI maintainer, I want the new tests to remain hermetic and fast, so that the existing 62-test green build stays green and continuous integration does not depend on Gemini availability.

#### Acceptance Criteria

1. THE Test Suite SHALL preserve the passing state of all 62 existing tests after Phase 4–8 changes are merged.
2. THE Test Suite SHALL NOT require `GOOGLE_API_KEY` to be set for any test that runs by default.
3. THE Test Suite SHALL NOT make outbound network calls during a default `pytest` run.
4. THE Test Suite SHALL include integration tests for `POST /agent/text` that exercise the Fake Agent end-to-end against the in-memory SQLite database, including: success path, missing user, missing device, blank text, and Agent Runtime error path.
5. THE Test Suite SHALL include unit tests for the Reminder Scheduler tick logic that verify due-reminder dispatch, channel routing, success/failure transitions, and continuation after exception, executed without starting the actual `BackgroundScheduler`.
6. THE Test Suite SHALL include integration tests for the three Phase 7 device endpoints that verify the Device Token check, the Atomic Mark-Sent invariant (two consecutive polls return non-overlapping command sets), ack on existing and missing commands, and status update with valid and invalid values.
7. THE Test Suite SHALL include integration tests for each Dashboard Endpoint covering at least: success path, missing user, and validation error path where applicable.
8. THE Test Suite SHALL configure scheduler-related tests with `scheduler_enabled = False` and SHALL invoke the tick function directly when verifying tick behavior.

### Requirement 17: Cross-Cutting: Dependencies and Configuration

**User Story:** As a backend developer, I want the dependency additions and new config keys for Phase 4–8 to be explicit, so that environment setup is deterministic.

#### Acceptance Criteria

1. THE Project Dependencies SHALL include the official Google ADK Python SDK package and APScheduler.
2. THE Project Dependencies SHALL include any additional Google packages required transitively by the Google ADK SDK; the specific package list SHALL be verified and pinned in the design document, not in this requirements document.
3. THE Project Configuration SHALL extend `Settings` with the keys `agent_mode: str`, `scheduler_enabled: bool`, `scheduler_interval_seconds: int`, and `dashboard_auth_mode: str`, each with a default value documented in the design.
4. THE `.env.example` File SHALL document every new configuration key introduced by this spec without populating any secret value.
5. THE Project Configuration SHALL preserve the existing settings `app_env`, `database_url`, `google_api_key`, `google_adk_model`, `device_api_token`, and `timezone` without changing their defaults.

### Requirement 18: Cross-Cutting: Documentation Updates

**User Story:** As a future contributor, I want the project docs to reflect the Phase 4–8 delta, so that the current state of the project is clear at a glance.

#### Acceptance Criteria

1. WHEN Phase 4–8 implementation is complete, THE Project Documentation SHALL state in `docs/AGENT_DESIGN.md` that the Tool Surface is registered as Google ADK tools wrapping the existing Phase 3 plain-Python tool wrappers, and that a Fake Agent is used for tests.
2. WHEN Phase 4–8 implementation is complete, THE Project Documentation SHALL document in `README.md` how to run `python -m scripts.run_agent_text`, how to enable the scheduler, and how to call `POST /agent/text`.
3. WHEN Phase 4–8 implementation is complete, THE Project Documentation SHALL move the `(Current)` marker in `docs/ROADMAP.md` to reflect the most advanced phase delivered by this spec.
4. WHEN Phase 4–8 implementation is complete, THE Project Documentation SHALL record the chosen `dashboard_auth_mode` for MVP and its rationale in either `docs/ARCHITECTURE.md` or the design document referenced by it.

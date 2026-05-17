# Requirements Document

## Introduction

Phase 8.5 menambahkan **Smoke Test Backend** sebagai gate manual sebelum frontend Phase 9 dibangun. Phase 0–8 sudah selesai (186/186 test lulus) dan tidak boleh diredesain oleh spec ini.

Tujuan Phase 8.5: memberi sinyal PASS/FAIL cepat yang melatih wiring nyata — DB, Service Layer, Agent Runtime, dashboard read path, dan device command queue — tanpa membutuhkan `GOOGLE_API_KEY` dan tanpa keluar ke jaringan secara default. Spec ini bersifat aditif: tidak ada schema baru, tidak ada migrasi, tidak ada method service-layer baru, tidak ada endpoint HTTP baru.

Deliverable yang diatur spec ini:

1. **`scripts/smoke_test_backend.py`** — CLI yang dijalankan sebagai `python -m scripts.smoke_test_backend`, dengan flag opsional `--real-agent` dan `--verbose`.
2. **`docs/SMOKE_TEST.md`** — dokumentasi cara pakai, prasyarat, exit code, dan tabel failure umum (gaya `03-runbook.md`).
3. (Opsional) **`app/tests/test_smoke_flow.py`** — hanya jika menambah nilai di luar CLI; keputusan akhir ditunda ke design.

Yang **bukan** target Phase 8.5 (akan diuraikan eksplisit di Requirement 12):

- Tidak ada testing level HTTP (uvicorn tidak distart). Service Layer + Agent Runtime sudah cukup.
- Tidak ada kode frontend (Phase 9).
- Tidak ada schema baru, tidak ada migrasi.
- Tidak ada method service-layer baru. Jika script butuh query yang tidak ada, gap dicatat di design tetapi tidak ditambahkan.
- Tidak ada pengiriman WhatsApp riil. WhatsApp Stub tetap satu-satunya jalur.
- Tidak ada integrasi CI. Manual gate saja.

Spec ini mereuse Glossary dari `.kiro/specs/service-layer/requirements.md` dan `.kiro/specs/agent-runtime-and-apis/requirements.md` (`Service Layer`, `Tool Wrapper Layer`, `Tool Result Dict`, `Agent Runtime`, `Per-Request Tool Factory`, `AgentRunResult`, `Fake Agent`, `Agent Mode`, `Reminder Scheduler`, `Scheduler Tick`, `WhatsApp Stub`, `Pending Command`, `Atomic Mark-Sent`) tanpa redefinisi. Istilah baru diperkenalkan di bagian Glossary di bawah.

## Glossary

- **Smoke Test Backend**: Harness CLI manual end-to-end yang didefinisikan oleh spec ini. File entry point: `scripts/smoke_test_backend.py`. Invocation default: `python -m scripts.smoke_test_backend`.
- **Smoke Step**: Satu unit pass/fail berlabel yang dilaporkan Smoke Test Backend dalam tabel ringkasan output. Setiap requirement di spec ini memetakan ke satu atau lebih Smoke Step bernama.
- **Smoke Run**: Satu eksekusi Smoke Test Backend dari awal sampai exit code dicetak.
- **Demo Fixture**: Data seed yang dibuat oleh `scripts/seed_dev.py` — `User` dengan `email = "demo@taskbot.local"` dan `Device` dengan `device_code = "TASKBOT-DEMO-001"`. Smoke Test Backend mengandalkan literal ini.
- **Smoke Demo User**: Baris `User` yang `email`-nya cocok dengan literal Demo Fixture.
- **Smoke Demo Device**: Baris `Device` yang `device_code`-nya cocok dengan literal Demo Fixture.
- **Smoke Settings Override**: Mekanisme in-process yang memaksa `settings.agent_mode = "fake"` (default) atau `settings.agent_mode = "real"` (saat `--real-agent` diberikan), tanpa menyentuh file `.env`.
- **Real-Agent Mode (Smoke)**: Mode opsional Smoke Run yang dipilih dengan flag `--real-agent`. Memaksa Agent Mode ke `"real"` dan mengizinkan call ke Gemini.
- **Verbose Mode (Smoke)**: Mode opsional Smoke Run yang dipilih dengan flag `--verbose`. Saat aktif, kegagalan mencetak full traceback Python di stderr.
- **Smoke Output Contract**: Bentuk output dan exit code yang dihasilkan Smoke Test Backend, didefinisikan di Requirement 10.
- **Smoke Exit Code**: Bilangan bulat yang dikembalikan oleh proses ke shell — `0` (PASS), `1` (FAIL umum), `2` (`--real-agent` tanpa `GOOGLE_API_KEY`), `3` (Demo Fixture hilang).
- **Smoke Network Hermeticity**: Properti bahwa Smoke Run default (tanpa `--real-agent`) tidak mengirim request keluar ke jaringan apa pun.
- **Smoke Test Documentation**: File `docs/SMOKE_TEST.md` yang didefinisikan oleh Requirement 11.

## Requirements

### Requirement 1: Configuration Loading and Settings Override

**User Story:** As a backend developer, I want the smoke test to use the project's existing settings loader and to default to fake mode regardless of `.env`, so that running the smoke test never requires editing `.env` or supplying a Gemini key.

#### Acceptance Criteria

1. THE Smoke Test Backend SHALL load configuration exclusively via the existing `app.config.settings` object, which itself reads only the single project-root `.env`; no other `.env` file SHALL be consulted.
2. WHEN the Smoke Test Backend starts a Smoke Run without the `--real-agent` flag, THE Smoke Test Backend SHALL apply a Smoke Settings Override that sets `settings.agent_mode` to `"fake"` before any Smoke Step executes, regardless of the value present in `.env`.
3. THE Smoke Test Backend SHALL NOT create, modify, delete, or rename the `.env` file on disk under any flag combination during a Smoke Run.
4. WHEN the Smoke Test Backend starts a Smoke Run with the `--real-agent` flag, THE Smoke Test Backend SHALL apply a Smoke Settings Override that sets `settings.agent_mode` to `"real"` before any Smoke Step executes.
5. WHERE the Smoke Run is in default mode (no `--real-agent`), THE Smoke Test Backend SHALL NOT require `settings.google_api_key` to be set or non-empty; an unset or empty `google_api_key` SHALL NOT block any Smoke Step in default mode.
6. WHEN the Smoke Run terminates for any reason, THE Smoke Test Backend SHALL restore `settings.agent_mode` to its pre-override value before the process exits.
7. IF the Smoke Settings Override cannot be applied for any reason, THEN THE Smoke Test Backend SHALL record the override failure as a failing Smoke Step per the Smoke Output Contract and SHALL continue to execute remaining Smoke Steps using whatever `settings.agent_mode` value is currently in effect.

### Requirement 2: Real-Agent Opt-In with Graceful Key-Missing Exit

**User Story:** As a developer, I want `--real-agent` to fail fast with a clear message when no Gemini key is configured, so that I never see a stack trace for a configuration mistake.

#### Acceptance Criteria

1. WHEN the Smoke Test Backend is invoked with `--real-agent` and `settings.google_api_key` is unset, an empty string, or a whitespace-only string, THE Smoke Test Backend SHALL write to stderr a single-line message indicating that `GOOGLE_API_KEY` is required for `--real-agent` and that the Smoke Run is aborting.
2. WHEN the Smoke Test Backend is invoked with `--real-agent` and `settings.google_api_key` is unset, empty, or whitespace-only, THE Smoke Test Backend SHALL exit with Smoke Exit Code `2` before executing any Smoke Step.
3. IF `settings.google_api_key` is unset, empty, or whitespace-only during a `--real-agent` Smoke Run, THEN THE Smoke Test Backend SHALL NOT print a Python traceback to either stdout or stderr.
4. WHEN the Smoke Test Backend is invoked with `--real-agent` and `settings.google_api_key` is non-empty (more than whitespace), THE Smoke Test Backend SHALL proceed to execute every Smoke Step defined by Requirements 3–9 in declared order; failures encountered during initialization of components other than the Gemini key SHALL be reported as failing Smoke Steps per the Smoke Output Contract but SHALL NOT prevent other independent Smoke Steps from executing.

### Requirement 3: Database Connection and Demo Fixture Discovery

**User Story:** As a developer, I want the smoke test to find the seeded demo user and device or tell me exactly how to seed them, so that I never have to grep for the right command.

#### Acceptance Criteria

1. WHEN the Smoke Run begins (after the Smoke Settings Override of Requirement 1 has been applied), THE Smoke Test Backend SHALL open exactly one database session by calling `app.db.SessionLocal()` against `settings.database_url` before any Smoke Step that reads or writes data executes.
2. THE Smoke Test Backend SHALL look up the Smoke Demo User by querying `User` rows where `email == "demo@taskbot.local"` and SHALL accept the lookup as successful only when exactly one matching row is returned.
3. THE Smoke Test Backend SHALL look up the Smoke Demo Device by querying `Device` rows where `device_code == "TASKBOT-DEMO-001"` and SHALL accept the lookup as successful only when exactly one matching row is returned.
4. IF the Smoke Demo User lookup returns zero matching rows, OR the Smoke Demo Device lookup returns zero matching rows, THEN THE Smoke Test Backend SHALL print to stderr a message that names which Demo Fixture row is missing and that includes the literal commands `python -m alembic upgrade head` and `python -m scripts.seed_dev`, and SHALL exit with Smoke Exit Code `3`.
5. IF the Smoke Test Backend exits with Smoke Exit Code `3`, THEN THE Smoke Test Backend SHALL NOT execute any Smoke Step defined by Requirements 4–9, and SHALL close the database session opened in clause 1 before the process exits.

### Requirement 4: Agent Runtime End-to-End Invocation in Fake Mode

**User Story:** As a developer, I want one real call through `run_text` against the demo user, so that I know the per-request Tool Factory, the Fake Agent dispatch, and the Service Layer all line up.

#### Acceptance Criteria

1. WHILE the Smoke Run is in default mode, THE Smoke Test Backend SHALL invoke `app.agent.runtime.run_text` exactly once during the Smoke Run with arguments `db = <smoke session>`, `user_id = <Smoke Demo User id>`, `device_id = <Smoke Demo Device id>`, `text = "catat makan siang 20000"`, and `timezone = settings.timezone`.
2. THE Smoke Test Backend SHALL `await` the coroutine returned by `run_text` with a 30-second timeout and capture the resulting `AgentRunResult`.
3. WHEN the `AgentRunResult` is captured, THE Smoke Test Backend SHALL verify `AgentRunResult.status` equals the string `"success"`.
4. WHEN the `AgentRunResult` is captured, THE Smoke Test Backend SHALL verify `AgentRunResult.reply` is a string whose `.strip()` length is between `1` and `10_000` characters inclusive.
5. WHEN the `AgentRunResult` is captured, THE Smoke Test Backend SHALL verify `AgentRunResult.actions` is a list whose length is between `1` and `50` inclusive and whose every element is a `dict` containing the keys `"success"` and `"type"`.
6. WHEN the `AgentRunResult` is captured, THE Smoke Test Backend SHALL verify `AgentRunResult.actions` contains at least one element whose `"type"` equals the literal `"expense"` and whose `"success"` is the boolean `True`.
7. IF the `await` in clause 2 raises an exception or times out, OR any verification in clauses 3–6 fails, THEN THE Smoke Test Backend SHALL record this Smoke Step as failing per the Smoke Output Contract.
8. IF this Smoke Step is recorded as failing, THEN THE Smoke Test Backend SHALL skip the Smoke Steps defined by Requirements 5 and 6 and SHALL continue to execute the Smoke Steps defined by Requirements 7 and 8.

### Requirement 5: VoiceCommandLog Persistence Verification

**User Story:** As a developer, I want the smoke test to confirm a VoiceCommandLog row was written, so that I know the audit-log pipeline is not silently broken.

#### Acceptance Criteria

1. WHEN the Smoke Step defined by Requirement 4 returns a successful `AgentRunResult`, THE Smoke Test Backend SHALL query the `VoiceCommandLog` table for rows whose `user_id` equals the Smoke Demo User id, whose `input_text` equals the literal `"catat makan siang 20000"`, and whose `status` equals the literal `"success"`.
2. THE Smoke Test Backend SHALL verify the query in clause 1 returns at least one matching row created during the current Smoke Run.
3. IF the query in clause 1 returns zero matching rows, THEN THE Smoke Test Backend SHALL record this Smoke Step as failing per the Smoke Output Contract, and the failure record SHALL include the matching-row count and the three query values (`user_id`, `input_text`, `status`).

### Requirement 6: Dashboard Summary Read-Back

**User Story:** As a developer, I want the smoke test to verify the dashboard read path sees the new expense, so that the read side is exercised without starting uvicorn.

#### Acceptance Criteria

1. WHEN the Smoke Step defined by Requirement 4 returns a successful `AgentRunResult`, THE Smoke Test Backend SHALL invoke `app.tools.summary_tools.get_today_summary_tool(db, user_id = <Smoke Demo User id>)` exactly once with a 5-second wall-clock ceiling, and SHALL capture the returned Tool Result Dict.
2. WHEN the Tool Result Dict is captured, THE Smoke Test Backend SHALL verify `"success"` is the boolean `True`.
3. WHEN the Tool Result Dict is captured, THE Smoke Test Backend SHALL verify `"type"` equals the literal `"summary"`.
4. WHEN the Tool Result Dict is captured, THE Smoke Test Backend SHALL verify `"total_expenses_today"` is a Python `int` (not `bool`, `float`, or `str`) whose value is between `20_000` and `2_147_483_647` inclusive.
5. WHILE this Smoke Step is executing, THE Smoke Test Backend SHALL NOT open a TCP socket to the FastAPI application and SHALL NOT instantiate any HTTP client targeting `app.main:app`.
6. IF the call in clause 1 raises an exception or exceeds the 5-second ceiling, THEN THE Smoke Test Backend SHALL record this Smoke Step as failing per the Smoke Output Contract and SHALL skip clauses 2–4.
7. IF any verification in clauses 2–4 fails, THEN THE Smoke Test Backend SHALL record this Smoke Step as failing per the Smoke Output Contract; the failure record SHALL identify which field failed and the observed value, and the Smoke Test Backend SHALL continue to execute the Smoke Steps defined by Requirements 7 and 8.

### Requirement 7: Device Command Queue Lifecycle

**User Story:** As a developer, I want the smoke test to walk a command from PENDING to SENT to ACKNOWLEDGED, so that I know the device queue lifecycle works end-to-end against the Smoke Demo Device.

#### Acceptance Criteria

1. THE Smoke Test Backend SHALL invoke `app.services.device_service.queue_device_command(db, device_id = <Smoke Demo Device id>, command_type = "show_text", payload = {"text": "smoke"})` and capture the returned `DeviceCommand`; THE Smoke Test Backend SHALL verify the captured row's `id` is a non-empty string and its initial `status` equals `DeviceCommandStatus.PENDING`.
2. THE Smoke Test Backend SHALL invoke `app.services.device_service.list_pending_device_commands(db, device_code = "TASKBOT-DEMO-001")` and verify the returned list contains exactly one entry whose `id` matches the Pending Command captured in clause 1.
3. THE Smoke Test Backend SHALL invoke `app.services.device_service.mark_device_command_sent(db, command_id = <captured command id>)` and verify the returned row has `id` matching the captured command and `status` equal to `DeviceCommandStatus.SENT`; THE Smoke Test Backend SHALL then re-invoke `list_pending_device_commands(db, device_code = "TASKBOT-DEMO-001")` and verify the returned list contains zero entries with the captured command id (Atomic Mark-Sent).
4. THE Smoke Test Backend SHALL invoke `app.services.device_service.ack_device_command(db, command_id = <captured command id>)` and verify the returned row has `id` matching the captured command and `status` equal to `DeviceCommandStatus.ACKNOWLEDGED`.
5. WHEN every verification in clauses 1–4 succeeds, THE Smoke Test Backend SHALL record this Smoke Step as passing per the Smoke Output Contract.
6. IF any service call in clauses 1–4 raises an exception, returns `None`, exceeds a 5-second per-call wall-clock ceiling, or fails any verification, THEN THE Smoke Test Backend SHALL record this Smoke Step as failing per the Smoke Output Contract; the failure record SHALL identify which clause and which assertion failed.

### Requirement 8: Scheduler Tick Smoke (No BackgroundScheduler)

**User Story:** As a developer, I want one synchronous `reminder_tick` call to confirm the scheduler code is callable without starting APScheduler, so that I do not introduce real timer flakiness into the smoke test.

#### Acceptance Criteria

1. THE Smoke Test Backend SHALL invoke `app.scheduler.tick.reminder_tick(db_factory = app.db.SessionLocal)` exactly once during the Smoke Run, with a 10-second wall-clock ceiling on the call.
2. WHEN the call returns, THE Smoke Test Backend SHALL verify the call returned without raising an exception and within the 10-second ceiling.
3. WHEN the call returns, THE Smoke Test Backend SHALL verify the returned value is a `dict` whose key set equals exactly `{"sent", "failed", "skipped"}` and whose every value is a non-negative Python `int` (excluding `bool`).
4. THE Smoke Test Backend SHALL NOT instantiate or start any APScheduler scheduler instance (including `BackgroundScheduler`, `BlockingScheduler`, or `AsyncIOScheduler`) during the Smoke Run, and SHALL NOT leave any APScheduler thread alive when the Smoke Run exits; importing APScheduler classes without instantiating them is permitted.
5. IF the call in clause 1 raises, exceeds the 10-second ceiling, returns a non-`dict`, returns a `dict` whose key set differs from `{"sent", "failed", "skipped"}`, or returns a value that is not a non-negative `int`, THEN THE Smoke Test Backend SHALL record this Smoke Step as failing per the Smoke Output Contract; the failure record SHALL identify which check failed and SHALL include the observed value or exception type.

### Requirement 9: Network Hermeticity in Default Mode

**User Story:** As a CI maintainer who might one day wrap this in a runner, I want the default smoke test to make zero outbound network calls, so that it is safe to run anywhere.

#### Acceptance Criteria

1. WHILE the Smoke Run is in default mode, neither `google.adk` nor `google.genai` nor any submodule of either SHALL be present in `sys.modules` after the Smoke Run finishes that was not already there before the Smoke Run started.
2. WHILE the Smoke Run is in default mode, THE Smoke Test Backend SHALL NOT issue any outbound HTTP, HTTPS, TCP, UDP, or DNS request to a non-loopback destination (i.e. anything outside `127.0.0.0/8` or `::1`); HTTP/HTTPS requests to non-loopback destinations SHALL remain prohibited regardless of any flag combination.
3. IF Smoke Network Hermeticity is violated during a default-mode Smoke Run, THEN THE Smoke Test Backend SHALL record the violating Smoke Step as failing per the Smoke Output Contract, the failure record SHALL identify the destination that was attempted, and the Smoke Test Backend SHALL preserve any database rows already created before the violation.
4. WHERE the Smoke Run uses the `--real-agent` flag, network requests to the Gemini API SHALL be routed exclusively through the existing Agent Runtime real path defined by `app/agent/runtime.py`; no other module SHALL initiate Gemini traffic during the Smoke Run, and `google.adk` / `google.genai` MAY be imported by that real path.
5. THE Smoke Test Backend SHALL enforce Smoke Network Hermeticity using mechanisms that remain active when the script is run as a plain Python process (not under pytest); THE Smoke Test Backend SHALL NOT depend on the autouse network kill-switch fixture defined in `app/tests/conftest.py`.

### Requirement 10: Smoke Output Contract and Exit Codes

**User Story:** As a developer reading the terminal output, I want a fixed table format and predictable exit codes, so that I (or a script) can decide PASS/FAIL at a glance.

#### Acceptance Criteria

1. THE Smoke Output Contract output SHALL be printed in the order: (a) summary table, (b) final status line. THE summary table SHALL include one row per Smoke Step defined by Requirements 3–8 in the order those Smoke Steps were declared, each row pairing the Smoke Step's name with either the literal `PASS` or the literal `FAIL`.
2. WHEN every Smoke Step defined by Requirements 3–8 records a pass during a Smoke Run, THE Smoke Test Backend SHALL print to stdout the literal final line `SMOKE TEST: PASS` after the summary table and SHALL exit with Smoke Exit Code `0`.
3. WHEN at least one Smoke Step defined by Requirements 3–8 records a failure during a Smoke Run, THE Smoke Test Backend SHALL print to stdout the summary table whose failing rows additionally include a single-line exception message bounded to 200 characters (longer messages truncated with a trailing `…`).
4. WHEN at least one Smoke Step records a failure during a Smoke Run, THE Smoke Test Backend SHALL print to stdout the literal final line `SMOKE TEST: FAIL` after the summary table and SHALL exit with Smoke Exit Code `1`.
5. WHERE Verbose Mode (Smoke) is active and a Smoke Step fails, THE Smoke Test Backend SHALL additionally print the full Python traceback for that failure to stderr after the summary table.
6. WHERE Verbose Mode (Smoke) is not active and a Smoke Step fails, THE Smoke Test Backend SHALL NOT print a Python traceback for that failure on stdout or stderr.
7. THE Smoke Test Backend SHALL NOT delete or modify any database row it created during a Smoke Run, so that subsequent inspection by the developer is possible.

### Requirement 11: Smoke Test Documentation (`docs/SMOKE_TEST.md`)

**User Story:** As a new contributor, I want one doc that tells me when to run the smoke test, what it costs, and how to read the output, so that I do not need to read the script source first.

#### Acceptance Criteria

1. THE Project SHALL include a Smoke Test Documentation file at `docs/SMOKE_TEST.md`.
2. THE Smoke Test Documentation SHALL contain a "Purpose" section that states Phase 8.5 is a manual gate before Phase 9 frontend work and that lists the categories the Smoke Test Backend exercises (database, Service Layer, Agent Runtime in fake mode, dashboard read path, device command queue, Reminder Scheduler tick).
3. THE Smoke Test Documentation SHALL list as prerequisites the literal commands `python -m alembic upgrade head` and `python -m scripts.seed_dev`, in that order.
4. THE Smoke Test Documentation SHALL document the default invocation as the literal `python -m scripts.smoke_test_backend`.
5. THE Smoke Test Documentation SHALL document the Real-Agent Mode (Smoke) invocation as the literal `python -m scripts.smoke_test_backend --real-agent` and SHALL state explicitly that this mode contacts the Gemini API, requires `GOOGLE_API_KEY` set in the project-root `.env`, and may incur cost or quota usage.
6. THE Smoke Test Documentation SHALL contain an exit-code table mapping `0` → `PASS`, `1` → `FAIL`, `2` → `missing GOOGLE_API_KEY for --real-agent`, and `3` → `missing Demo Fixture`.
7. THE Smoke Test Documentation SHALL contain a "Common failures" markdown table with at least three columns (`Symptom`, `Likely cause`, `Fix`) and at minimum one row per non-zero Smoke Exit Code, styled after the runbook in `.kiro/steering/03-runbook.md`.
8. THE Smoke Test Documentation SHALL state explicitly that the Smoke Test Backend is a manual gate and is not wired into any CI pipeline.
9. THE Smoke Test Documentation SHALL contain a "Reading the output" section that shows an example PASS summary table, an example FAIL summary table with a one-line exception message, and the location of full tracebacks (`--verbose` to stderr).

### Requirement 12: Non-Goals (Scope Guard)

**User Story:** As a maintainer, I want non-goals stated as testable constraints, so that future contributors do not silently broaden the scope of Phase 8.5.

#### Acceptance Criteria

1. THE Smoke Test Backend SHALL NOT start uvicorn or bind any TCP port during a Smoke Run.
2. THE Smoke Test Backend SHALL NOT issue any HTTP request to the FastAPI application during a Smoke Run.
3. THE Smoke Test Backend SHALL NOT add new database tables, columns, or Alembic migration files.
4. THE Smoke Test Backend SHALL NOT add new methods to any module under `app/services/`.
5. WHERE the Smoke Test Backend needs a database read that the existing Service Layer does not expose, THE Phase 8.5 Design Document SHALL document the gap and SHALL NOT introduce a new service-layer method to satisfy it; this restriction applies only to undocumented database-read gaps and does not prohibit non-database service additions outside the scope of this spec.
6. THE Smoke Test Backend SHALL NOT call the real WhatsApp Cloud API; it relies on the existing WhatsApp Stub via `app.scheduler.tick.reminder_tick`.
7. THE Phase 8.5 Deliverables SHALL NOT include any frontend code, asset, or build artifact.
8. THE Phase 8.5 Deliverables SHALL NOT modify the existing `agents/taskbot_agent/` dev-only ADK package.

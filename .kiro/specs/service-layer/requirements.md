# Requirements Document

## Introduction

Phase 3 dari pengembangan backend Taskbot menambahkan **Service Layer** dan **Tool Wrapper Layer** di atas data layer yang sudah ada (Phase 2). Service Layer berisi business logic murni untuk task akademik, pengeluaran, reminder, device command queue, dan voice command audit log. Tool Wrapper Layer adalah pembungkus tipis yang nanti dipanggil oleh Google ADK di Phase 4 — pada Phase 3 ini wrappernya hanya fungsi Python biasa yang mengembalikan dictionary ramah agent.

Phase 3 secara eksplisit **tidak** mencakup Google ADK, agent runtime, endpoint `/agent/text`, scheduler, dashboard, ESP firmware, STT/TTS, atau WhatsApp. Tujuannya: business logic dapat diuji penuh tanpa AI sehingga integrasi ADK di phase berikutnya menjadi minimal-risk.

## Glossary

- **Service Layer**: Modul Python di `app/services/` yang berisi business logic murni, tidak bergantung pada framework AI atau HTTP. Setiap service menerima `db: Session` dan parameter primitif/Python objects.
- **Tool Wrapper Layer**: Modul Python di `app/tools/` yang membungkus pemanggilan service layer dan mengembalikan dictionary ramah agent (`{"success": bool, "type": str, ...}`). Bukan tool Google ADK.
- **Task Service**: Modul `app/services/task_service.py`.
- **Expense Service**: Modul `app/services/expense_service.py`.
- **Reminder Service**: Modul `app/services/reminder_service.py`.
- **Device Service**: Modul `app/services/device_service.py`.
- **Log Service**: Modul `app/services/log_service.py`.
- **Service Exceptions**: Class custom di `app/services/exceptions.py`: `NotFoundError`, `ValidationError`, `PermissionDeniedError`.
- **Serialization Helper**: Modul `app/utils/serialization.py` yang mengubah SQLAlchemy model menjadi dict.
- **Aware Datetime**: `datetime.datetime` yang memiliki `tzinfo` non-`None`.
- **UTC Now**: `datetime.now(timezone.utc)`.
- **Status Constants**: Konstanta string di `app/models/constants.py` (`TaskStatus`, `DeviceStatus`, `ReminderStatus`, `DeviceCommandStatus`).
- **Channel**: Salah satu dari nilai `"whatsapp"`, `"device"`, `"both"` yang menyatakan kanal pengiriman reminder.
- **Pending Command**: `DeviceCommand` dengan `status == DeviceCommandStatus.PENDING`.
- **Due Reminder**: `Reminder` dengan `status == ReminderStatus.SCHEDULED` dan `remind_at <= now`.
- **Tool Result Dict**: Dictionary dengan key minimal `success: bool`, `type: str`, dan `message: str`. Pada sukses, mengandung `id` dari objek yang dibuat. Pada gagal, mengandung `error: str`.

## Requirements

### Requirement 1 — Task Service

**User Story:** As a backend developer, I want a `Task Service` that creates, lists, and updates academic tasks, so that the agent layer can manipulate tasks without touching ORM details.

#### Acceptance Criteria

1. WHEN `create_task` is invoked with a valid `user_id`, a non-empty `title`, and optional fields, THE Task Service SHALL persist a new `Task` row with `status = TaskStatus.PENDING` and return the created `Task` object.
2. WHEN `create_task` is invoked with a non-`None` `reminder_at`, THE Task Service SHALL also persist a `Reminder` row linked to the new task with the same `user_id`, `remind_at = reminder_at`, and `status = ReminderStatus.SCHEDULED`.
3. IF `create_task` is invoked with a `title` that is empty or contains only whitespace, THEN THE Task Service SHALL raise `ValidationError` and persist no rows.
4. IF `create_task` is invoked with a `user_id` that does not match an existing `User`, THEN THE Task Service SHALL raise `NotFoundError` and persist no rows.
5. IF `create_task` is invoked with `deadline_at` or `reminder_at` that is not an Aware Datetime, THEN THE Task Service SHALL raise `ValidationError` and persist no rows.
6. IF `create_task` is invoked with a `reminder_at` that is earlier than UTC Now, THEN THE Task Service SHALL raise `ValidationError` and persist no rows.
7. WHEN `list_tasks` is invoked with a `user_id`, THE Task Service SHALL return only `Task` rows whose `user_id` matches the argument.
8. WHERE the `status` argument of `list_tasks` is non-`None`, THE Task Service SHALL further restrict the returned rows to those whose `status` equals the argument.
9. WHEN `mark_task_done` is invoked with a `task_id` that exists and belongs to the supplied `user_id`, THE Task Service SHALL set that task's `status` to `TaskStatus.DONE` and return the updated `Task`.
10. IF `mark_task_done` is invoked with a `task_id` that does not exist, THEN THE Task Service SHALL raise `NotFoundError`.
11. IF `mark_task_done` is invoked with a `task_id` whose `user_id` does not match the supplied `user_id`, THEN THE Task Service SHALL raise `PermissionDeniedError`.

### Requirement 2 — Expense Service

**User Story:** As a backend developer, I want an `Expense Service` that records expenses and produces simple summaries, so that the agent layer can record and report spending.

#### Acceptance Criteria

1. WHEN `create_expense` is invoked with a valid `user_id` and a positive integer `amount`, THE Expense Service SHALL persist a new `Expense` row and return the created `Expense` object.
2. IF `create_expense` is invoked with `amount` less than or equal to zero, THEN THE Expense Service SHALL raise `ValidationError` and persist no rows.
3. IF `create_expense` is invoked with a `user_id` that does not match an existing `User`, THEN THE Expense Service SHALL raise `NotFoundError` and persist no rows.
4. IF `create_expense` is invoked with a `spent_at` that is not `None` and not an Aware Datetime, THEN THE Expense Service SHALL raise `ValidationError` and persist no rows.
5. WHERE `spent_at` is `None`, THE Expense Service SHALL set the persisted row's `spent_at` to UTC Now.
6. WHEN `list_expenses` is invoked, THE Expense Service SHALL return only `Expense` rows whose `user_id` matches the argument and whose `spent_at` falls within the optional `[start_at, end_at]` window when those bounds are supplied.
7. WHEN `get_expense_summary` is invoked, THE Expense Service SHALL return a dictionary with key `total` equal to the sum of `amount` over the matching rows and key `count` equal to the number of matching rows.
8. WHERE `get_expense_summary` is invoked and there are no matching rows, THE Expense Service SHALL return `{"total": 0, "count": 0}`.

### Requirement 3 — Reminder Service

**User Story:** As a backend developer, I want a `Reminder Service` that creates reminders and tracks their delivery status, so that scheduled work in later phases can dispatch and finalize them.

#### Acceptance Criteria

1. WHEN `create_reminder` is invoked with a valid `user_id`, a non-empty `title`, an Aware Datetime `remind_at` not earlier than UTC Now, and a `channel` in `{"whatsapp", "device", "both"}`, THE Reminder Service SHALL persist a new `Reminder` row with `status = ReminderStatus.SCHEDULED` and return the created `Reminder` object.
2. IF `create_reminder` is invoked with a `title` that is empty or contains only whitespace, THEN THE Reminder Service SHALL raise `ValidationError` and persist no rows.
3. IF `create_reminder` is invoked with a `user_id` that does not match an existing `User`, THEN THE Reminder Service SHALL raise `NotFoundError` and persist no rows.
4. IF `create_reminder` is invoked with `remind_at` that is not an Aware Datetime, THEN THE Reminder Service SHALL raise `ValidationError` and persist no rows.
5. IF `create_reminder` is invoked with `remind_at` earlier than UTC Now, THEN THE Reminder Service SHALL raise `ValidationError` and persist no rows.
6. IF `create_reminder` is invoked with a `channel` outside `{"whatsapp", "device", "both"}`, THEN THE Reminder Service SHALL raise `ValidationError` and persist no rows.
7. IF `create_reminder` is invoked with a non-`None` `task_id` that does not match an existing `Task` belonging to the supplied `user_id`, THEN THE Reminder Service SHALL raise `NotFoundError` or `PermissionDeniedError` and persist no rows.
8. WHEN `list_due_reminders` is invoked, THE Reminder Service SHALL return only `Reminder` rows where `status = ReminderStatus.SCHEDULED` and `remind_at <= now`, where `now` defaults to UTC Now when not supplied.
9. WHEN `mark_reminder_sent` is invoked with an existing `reminder_id`, THE Reminder Service SHALL set that reminder's `status` to `ReminderStatus.SENT`.
10. WHEN `mark_reminder_failed` is invoked with an existing `reminder_id`, THE Reminder Service SHALL set that reminder's `status` to `ReminderStatus.FAILED`.
11. IF `mark_reminder_sent` or `mark_reminder_failed` is invoked with a `reminder_id` that does not exist, THEN THE Reminder Service SHALL raise `NotFoundError`.

### Requirement 4 — Device Service

**User Story:** As a backend developer, I want a `Device Service` that queues commands to ESP devices and tracks their lifecycle, so that the agent and the polling endpoint in later phases can rely on a single source of truth.

#### Acceptance Criteria

1. WHEN `get_device_by_code` is invoked with a `device_code` that matches an existing `Device`, THE Device Service SHALL return that `Device` object.
2. IF `get_device_by_code` is invoked with a `device_code` that does not match any `Device`, THEN THE Device Service SHALL raise `NotFoundError`.
3. WHEN `queue_device_command` is invoked with an existing `device_id`, a non-empty `command_type`, and a `payload` dictionary, THE Device Service SHALL persist a new `DeviceCommand` row with `status = DeviceCommandStatus.PENDING` and return the created `DeviceCommand` object.
4. IF `queue_device_command` is invoked with a `device_id` that does not match an existing `Device`, THEN THE Device Service SHALL raise `NotFoundError` and persist no rows.
5. IF `queue_device_command` is invoked with a `command_type` that is empty or contains only whitespace, THEN THE Device Service SHALL raise `ValidationError` and persist no rows.
6. IF `queue_device_command` is invoked with a `payload` that is not a Python `dict`, THEN THE Device Service SHALL raise `ValidationError` and persist no rows.
7. WHEN `list_pending_device_commands` is invoked with an existing `device_code`, THE Device Service SHALL return only `DeviceCommand` rows linked to that device whose `status` equals `DeviceCommandStatus.PENDING`.
8. WHEN `mark_device_command_sent` is invoked with an existing `command_id`, THE Device Service SHALL set that command's `status` to `DeviceCommandStatus.SENT` and `sent_at` to UTC Now.
9. WHEN `ack_device_command` is invoked with an existing `command_id`, THE Device Service SHALL set that command's `status` to `DeviceCommandStatus.ACKNOWLEDGED` and `acknowledged_at` to UTC Now.
10. WHEN `update_device_status` is invoked with an existing `device_code` and a valid `DeviceStatus` value, THE Device Service SHALL set that device's `status` to the argument and `last_seen_at` to UTC Now.
11. IF `update_device_status` is invoked with a `status` value not in `{DeviceStatus.ONLINE, DeviceStatus.OFFLINE}`, THEN THE Device Service SHALL raise `ValidationError`.

### Requirement 5 — Log Service

**User Story:** As a backend developer, I want a `Log Service` that records audit logs of agent interactions, so that future phases can debug parsing and tool calls.

#### Acceptance Criteria

1. WHEN `create_voice_command_log` is invoked with a non-empty `input_text`, THE Log Service SHALL persist a new `VoiceCommandLog` row and return the created object.
2. IF `create_voice_command_log` is invoked with an `input_text` that is empty or contains only whitespace, THEN THE Log Service SHALL raise `ValidationError` and persist no rows.
3. IF `create_voice_command_log` is invoked with a non-`None` `user_id` that does not match an existing `User`, THEN THE Log Service SHALL raise `NotFoundError` and persist no rows.
4. IF `create_voice_command_log` is invoked with a non-`None` `device_id` that does not match an existing `Device`, THEN THE Log Service SHALL raise `NotFoundError` and persist no rows.
5. IF `create_voice_command_log` is invoked with a `parsed_actions` value that is not JSON-serializable, THEN THE Log Service SHALL raise `ValidationError` and persist no rows.
6. WHEN `create_voice_command_log` is invoked with a `parsed_actions` dictionary or list, THE Log Service SHALL persist that value verbatim in the `parsed_actions` JSON column.

### Requirement 6 — Tool Wrapper Layer

**User Story:** As a backend developer, I want plain Python tool wrappers that produce agent-friendly dictionaries, so that the same surface can be reused by Google ADK in Phase 4 with minimal change.

#### Acceptance Criteria

1. WHEN `create_task_tool` is invoked with valid arguments, THE Tool Wrapper Layer SHALL call `task_service.create_task` and return a Tool Result Dict with `success = True`, `type = "task"`, and `id` equal to the created task id.
2. WHEN `create_expense_tool` is invoked with valid arguments, THE Tool Wrapper Layer SHALL call `expense_service.create_expense` and return a Tool Result Dict with `success = True`, `type = "expense"`, and `id` equal to the created expense id.
3. WHEN `set_reminder_tool` is invoked with valid arguments, THE Tool Wrapper Layer SHALL call `reminder_service.create_reminder` and return a Tool Result Dict with `success = True`, `type = "reminder"`, and `id` equal to the created reminder id.
4. WHEN `send_device_command_tool` is invoked with at least one of `face`, `sound`, or `text` non-`None`, THE Tool Wrapper Layer SHALL build a `payload` dictionary from the supplied fields, call `device_service.queue_device_command`, and return a Tool Result Dict with `success = True`, `type = "device_command"`, and `id` equal to the created command id.
5. IF `send_device_command_tool` is invoked with `face`, `sound`, and `text` all `None`, THEN THE Tool Wrapper Layer SHALL return a Tool Result Dict with `success = False` and a non-empty `error`, and SHALL NOT call `device_service.queue_device_command`.
6. WHEN `get_today_summary_tool` is invoked with a valid `user_id`, THE Tool Wrapper Layer SHALL return a Tool Result Dict with `success = True`, `type = "summary"`, `tasks_due_today` (integer count of tasks whose `deadline_at` falls within the current Asia/Jakarta calendar day), and `total_expenses_today` (sum of expenses whose `spent_at` falls within the same window).
7. IF any underlying service raises `ValidationError`, `NotFoundError`, or `PermissionDeniedError` during a tool wrapper call, THEN THE Tool Wrapper Layer SHALL catch the exception and return a Tool Result Dict with `success = False`, the same `type` value as the success case, and an `error` field containing the exception message.

### Requirement 7 — Service Exceptions and Serialization

**User Story:** As a backend developer, I want a small set of typed service exceptions and a minimal serialization helper, so that error handling and tool dictionary construction stay consistent.

#### Acceptance Criteria

1. THE Service Exceptions module SHALL define exactly three exception classes: `NotFoundError`, `ValidationError`, and `PermissionDeniedError`, each derived from `Exception`.
2. THE Serialization Helper SHALL provide a function `model_to_dict(obj)` that returns a `dict` whose keys are the SQLAlchemy column names of `obj` and whose values are the corresponding column values, with `datetime` values rendered as ISO 8601 strings.
3. WHEN `model_to_dict` is invoked with `None`, THE Serialization Helper SHALL return `None`.

### Requirement 8 — Timezone Handling

**User Story:** As a backend developer, I want timestamps stored in UTC and presented in Asia/Jakarta when needed, so that user-facing time arithmetic stays consistent.

#### Acceptance Criteria

1. WHEN any service persists a timestamp it generates internally (for example default `spent_at`, `sent_at`, `acknowledged_at`, `last_seen_at`), THE Service Layer SHALL use UTC Now.
2. WHEN `get_today_summary_tool` computes the "today" window, THE Tool Wrapper Layer SHALL use the Asia/Jakarta calendar day, with the start at 00:00 Asia/Jakarta and the end at 24:00 Asia/Jakarta of the current day, both converted to UTC for database comparison.
3. THE Service Layer SHALL accept Aware Datetime values in any timezone for fields supplied by callers and SHALL persist them without altering their absolute instant in time.

### Requirement 9 — Test Coverage

**User Story:** As a backend developer, I want service-layer and tool-wrapper tests using a temporary SQLite database, so that business logic regressions are caught before integration with Google ADK.

#### Acceptance Criteria

1. THE Test Suite SHALL include a test file for each of: task service, expense service, reminder service, device service, log service, and tool wrappers.
2. THE Test Suite SHALL use an in-memory SQLite database isolated per test run, and SHALL NOT read or write the file `taskbot.db`.
3. THE Test Suite SHALL preserve the passing state of the existing `test_config.py`, `test_health.py`, and `test_models.py` tests.
4. THE Test Suite SHALL include at least one property-based test per declared correctness property in the design document, configured to run at least 100 examples per property.

### Requirement 10 — Scope Boundaries (Non-Goals)

**User Story:** As a project maintainer, I want Phase 3 to refuse scope creep, so that subsequent phases stay independently deliverable.

#### Acceptance Criteria

1. THE Phase 3 deliverable SHALL NOT introduce any dependency on Google ADK, LangChain, or other agent frameworks in `requirements.txt`.
2. THE Phase 3 deliverable SHALL NOT add HTTP routes beyond those already present in `app/api/`.
3. THE Phase 3 deliverable SHALL NOT introduce a scheduler, background worker, or message queue.
4. THE Phase 3 deliverable SHALL NOT add real WhatsApp, STT, TTS, or ESP firmware integration.
5. THE Phase 3 deliverable SHALL preserve compatibility with the existing SQLite schema and Alembic migration head.

### Requirement 11 — Documentation

**User Story:** As a future contributor, I want the docs to reflect the Phase 3 delta, so that the current state of the project is clear at a glance.

#### Acceptance Criteria

1. WHEN Phase 3 implementation is complete, THE Project Documentation SHALL include in `README.md` a note that the service layer is implemented and a command for running the test suite.
2. WHEN Phase 3 implementation is complete, THE Project Documentation SHALL state in `docs/AGENT_DESIGN.md` that the tool wrappers are plain Python and that Google ADK integration is deferred to Phase 4.
3. WHEN Phase 3 implementation is complete, THE Project Documentation SHALL mark Phase 3 as the current phase in `docs/ROADMAP.md`.

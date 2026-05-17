# Phase 3 — Service Layer: Delivery Summary

## 1. Files Created / Modified

### Created (new files)

| File | Description |
|------|-------------|
| `app/services/exceptions.py` | `NotFoundError`, `ValidationError`, `PermissionDeniedError` |
| `app/services/expense_service.py` | `create_expense`, `list_expenses`, `get_expense_summary` |
| `app/services/reminder_service.py` | `create_reminder`, `list_due_reminders`, `mark_reminder_sent`, `mark_reminder_failed` |
| `app/services/device_service.py` | `get_device_by_code`, `queue_device_command`, `list_pending_device_commands`, `mark_device_command_sent`, `ack_device_command`, `update_device_status` |
| `app/services/log_service.py` | `create_voice_command_log` |
| `app/utils/__init__.py` | Package init (`# Init`) |
| `app/utils/timezone.py` | `now_utc()`, `jakarta_today_window_utc()`, `JAKARTA` constant |
| `app/utils/serialization.py` | `model_to_dict()` |
| `app/tools/task_tools.py` | `create_task_tool` — Tool Result Dict wrapper |
| `app/tools/expense_tools.py` | `create_expense_tool` — Tool Result Dict wrapper |
| `app/tools/reminder_tools.py` | `set_reminder_tool` — Tool Result Dict wrapper |
| `app/tools/device_tools.py` | `send_device_command_tool` — Tool Result Dict wrapper |
| `app/tools/summary_tools.py` | `get_today_summary_tool` — Tool Result Dict wrapper |
| `app/tests/test_task_service.py` | PBTs T1–T5 + unit tests |
| `app/tests/test_expense_service.py` | PBTs E1–E5 + unit tests |
| `app/tests/test_reminder_service.py` | PBTs R1–R6 + unit tests |
| `app/tests/test_device_service.py` | PBTs D1–D6 + unit tests |
| `app/tests/test_log_service.py` | PBTs L1–L3 + unit test |
| `app/tests/test_tool_wrappers.py` | PBTs TW1–TW7 |
| `app/tests/test_utils_properties.py` | PBTs U1–U2 |
| `app/tests/test_service_exceptions.py` | Unit tests for exception classes |

### Modified (existing files updated)

| File | Change |
|------|--------|
| `requirements.txt` | Added `hypothesis>=6.100` |
| `app/services/task_service.py` | Already existed; verified against spec (no changes needed) |
| `app/tests/conftest.py` | Already existed; verified in-memory SQLite fixture (no changes needed) |
| `README.md` | Updated current phase to Phase 3, added service/tool layer note, updated test command |
| `docs/AGENT_DESIGN.md` | Added Phase 3 Implementation Status section |
| `docs/ROADMAP.md` | Moved `(Current)` marker from Phase 0 to Phase 3 |

---

## 2. Migration Command

Phase 3 adds **no new database tables or columns**. The schema is unchanged from Phase 2.

No new migration is needed. To apply existing migrations from scratch:

```bash
alembic upgrade head
```

---

## 3. Seed Command

```bash
python -m scripts.seed_dev
```

> Note: the seed script is a Phase 2 artifact. Phase 3 adds no new seed data requirements.

---

## 4. Test Command

Run the full test suite (62 tests, ~50 seconds):

```bash
python -m pytest app/tests/ -v
```

Run only service-layer tests:

```bash
python -m pytest app/tests/test_task_service.py app/tests/test_expense_service.py app/tests/test_reminder_service.py app/tests/test_device_service.py app/tests/test_log_service.py app/tests/test_tool_wrappers.py app/tests/test_utils_properties.py app/tests/test_service_exceptions.py -v
```

Expected result: **62 passed, 0 failed**.

---

## 5. What Is Intentionally Not Implemented Yet

The following items are **explicitly out of scope for Phase 3** (per `requirements.md` Requirement 10 — Scope Boundaries):

| Item | Deferred to |
|------|-------------|
| **Google ADK integration** — tool wrappers in `app/tools/` are plain Python functions, not ADK tool objects | Phase 4 |
| **`/agent/text` HTTP endpoint** — no new API routes added | Phase 5 |
| **Scheduler / background worker** — no APScheduler, Celery, or cron jobs | Phase 6 |
| **WhatsApp notification dispatch** — `channel` field is stored but no actual sending | Phase 6+ |
| **STT / TTS processing** — no audio pipeline | Phase 10 |
| **ESP32 firmware / device polling endpoint** — `DeviceCommand` queue is ready but no HTTP polling route | Phase 7 |
| **Dashboard API endpoints** — no read-only REST endpoints for frontend | Phase 8 |
| **`TaskStatus.CANCELLED` and `ReminderStatus.CANCELLED`** — constants exist in models but no service function transitions to them | Phase 4+ |
| **`DeviceCommandStatus.FAILED`** — constant exists but no service function sets it | Phase 4+ |
| **Agent logging** — `VoiceCommandLog` can be written via `log_service`, but the agent runner that calls it does not exist yet | Phase 5 |

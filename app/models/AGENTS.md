# app/models/ — SQLAlchemy ORM

## OVERVIEW
ORM models for users, devices, tasks, expenses, reminders, voice command logs, and the device command queue. SQLite-backed; Alembic-managed.

## FILES

```
constants.py            # status enums, channel literals, etc.
user.py                 # User
device.py               # Device (owned by user, has device_code + token)
device_command.py       # DeviceCommand queue rows (polled by ESP32)
task.py                 # academic Task with deadline/reminder
expense.py              # Expense (positive int rupiah)
reminder.py             # Reminder + status (PENDING|SENT|FAILED)
voice_command_log.py    # VoiceCommandLog — append-only audit
```

## HARD CONVENTIONS

- **UUID primary keys** — all `id` columns are `String(36)` UUIDs (not auto-int). Pydantic schemas at the API edge validate them. Service-layer code MUST not assume `int`.
- **Timezone-aware `DateTime(timezone=True)`** — store UTC-equivalent; convert at the edge using `app/utils/timezone.py`. Default user tz is `Asia/Jakarta`.
- **`VoiceCommandLog` is append-only** — `POST /agent/text` writes a row even on the 500 error path. Don't introduce mutating updates.
- **Reminder status enum is a contract with the scheduler.** `app/scheduler/tick.py` flips PENDING → SENT|FAILED. Don't rename without updating the tick.

## MIGRATIONS

Every model change needs an Alembic revision in `alembic/versions/`. UUID columns must be created as `String(36)` to stay portable to PostgreSQL later (don't use SQLite-only types).

## ANTI-PATTERNS

- Using `Integer` for `id` — breaks every layer above (services, schemas, tools all assume `str`).
- Naive `datetime` columns — strips tzinfo, breaks scheduler windowing.
- Mutating `VoiceCommandLog` rows after insert.
- Adding a new model without an Alembic revision — `alembic upgrade head` will silently match an old schema.

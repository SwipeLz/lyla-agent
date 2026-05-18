# app/services/ — Business Logic

## OVERVIEW
Sync SQLAlchemy services. Raise typed exceptions. Never know about HTTP, never know about LLM tools.

## FILES

```
exceptions.py        # NotFoundError, ValidationError, PermissionDeniedError
task_service.py      # academic tasks
expense_service.py   # expense entries (positive int rupiah)
reminder_service.py  # reminders + due-list query for scheduler
device_service.py    # device + command queue (used by ESP32 polling)
log_service.py       # VoiceCommandLog persistence (always log, even on error)
```

## EXCEPTION CONTRACT

All services raise from `exceptions.py` only:

| Exception | When | Maps to |
|-----------|------|---------|
| `NotFoundError` | row not found by id | HTTP 404 |
| `ValidationError` | invalid input (negative amount, bad date, missing field) | HTTP 422 |
| `PermissionDeniedError` | row exists but user has no access | HTTP 403 |

Mapping is centralized in `app/api/_errors.py`. Don't raise `HTTPException` here.

## RULES

- **Sync only.** `Session` is sync; service functions are `def`, not `async def`.
- **No catching of own exceptions.** Tools/api decide how to respond.
- **UUID `id` columns**, never int. Use `str(uuid)` parsed via Pydantic at API boundary.
- **Timezone-aware datetimes.** Use `app/utils/timezone.py` helpers; default tz is `Asia/Jakarta`.
- **Reminder due-list** is the scheduler's read interface — don't change shape without checking `app/scheduler/tick.py`.

## ANTI-PATTERNS

- Returning `None` for "not found" instead of raising `NotFoundError` — tools/api can't distinguish error vs empty.
- Mutating model objects without `db.flush()`/`commit()` (commit is owned by the caller, but flush before reading back generated values).
- Adding HTTP-layer concerns (status codes, request ids) here.

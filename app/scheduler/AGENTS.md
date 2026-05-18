# app/scheduler/ — Reminder Scheduler

## OVERVIEW
APScheduler `BackgroundScheduler` that ticks every `SCHEDULER_INTERVAL_SECONDS` and dispatches due reminders to the device command queue and/or WhatsApp stub. **Opt-in** — disabled by default so tests and dev runs don't fire side effects.

## FILES

```
lifecycle.py   # start_scheduler(app) / stop_scheduler(app), tied to FastAPI lifespan
tick.py        # the single tick function: query → dispatch → update status
__init__.py
```

## TICK CONTRACT

Per tick:

1. Call `reminder_service.list_due_reminders(now)` (sync, sees current DB state).
2. For each due reminder, dispatch by `channel`:
   - `device` → enqueue `DeviceCommand` for the user's device.
   - `whatsapp` → call `app/integrations/whatsapp.py` stub (no real network).
   - `both` → both of the above.
3. Mark reminder `SENT` on success, `FAILED` on dispatch error. Never leave it `PENDING` after a successful pass.

If `list_due_reminders` raises, log and let the next tick retry — don't crash the scheduler.

## CONFIG (project-root `.env`)

```
SCHEDULER_ENABLED=false              # default; pytest depends on this
SCHEDULER_INTERVAL_SECONDS=60
```

`main.py` lifespan reads `settings.scheduler_enabled` once at startup. To toggle, edit `.env` and restart `uvicorn`.

## ANTI-PATTERNS

- **Default `SCHEDULER_ENABLED=true`** — would break the test suite, which assumes no background ticks.
- **Crashing the tick on a single bad reminder** — wrap each dispatch; one bad row must not stop the others.
- **Leaving reminders `PENDING` after dispatch attempt** — services and tests assume terminal state per pass.
- **Calling outbound WhatsApp APIs** — `whatsapp.py` is a stub. Real integration is deferred.
- **Async tick fn** — APScheduler's `BackgroundScheduler` is sync; keep the tick `def`, not `async def`.

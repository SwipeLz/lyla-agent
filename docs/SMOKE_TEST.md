# Smoke Test (Phase 8.5)

## Purpose

Phase 8.5 is a **manual gate** that must pass before Phase 9 frontend work
begins. The Smoke Test Backend is a single CLI (`python -m
scripts.smoke_test_backend`) that exercises the wiring between the Phase 0–8
backend layers in one process, without starting `uvicorn` and without
requiring `GOOGLE_API_KEY` in default mode. It is intentionally fast and
hermetic so that any contributor can run it locally before declaring the
backend ready for the next phase.

The Smoke Test Backend exercises the following categories:

- database (SQLite via the project's `app.db.SessionLocal`)
- Service Layer (`app/services/*`)
- Agent Runtime in fake mode (`app/agent/runtime.py` with
  `settings.agent_mode = "fake"`)
- dashboard read path (`app/tools/summary_tools.get_today_summary_tool`)
- device command queue (PENDING → SENT → ACKNOWLEDGED lifecycle)
- Reminder Scheduler tick (`app/scheduler/tick.reminder_tick`, called
  synchronously, without starting APScheduler)

## Prerequisites

Run these two commands once, in this order, before the first Smoke Run:

1. Apply database migrations:

   ```cmd
   python -m alembic upgrade head
   ```

2. Seed the demo user and device that the Smoke Test Backend looks up:

   ```cmd
   python -m scripts.seed_dev
   ```

## Running

### Default (fake agent, hermetic)

The default Smoke Run uses the fake agent (`agent_mode = "fake"`) and does
not contact any external service. It is the mode every contributor should
run before declaring backend work ready for the next phase.

```cmd
python -m scripts.smoke_test_backend
```

### With the real Gemini agent

Pass `--real-agent` to swap the fake agent for the production Google ADK +
Gemini path. Use this sparingly — it is the same code path that
`POST /agent/text` uses in production.

```cmd
python -m scripts.smoke_test_backend --real-agent
```

Notes:

- contacts the Gemini API
- requires `GOOGLE_API_KEY` set in the project-root `.env`
- may incur cost or quota usage

### Verbose tracebacks

By default a failing Smoke Step prints only a one-line summary. Pass
`--verbose` to also print the full Python traceback for each FAIL step to
stderr, which is useful when triaging an unexpected failure.

```cmd
python -m scripts.smoke_test_backend --verbose
```

## Exit codes

The Smoke Test Backend exits with one of four distinct codes so that shell
scripts and CI runners (when wired up later) can branch on the failure
category without parsing stdout.

| Code | Meaning                                       |
| ---- | --------------------------------------------- |
| 0    | PASS                                          |
| 1    | FAIL                                          |
| 2    | missing GOOGLE_API_KEY for --real-agent       |
| 3    | missing Demo Fixture                          |

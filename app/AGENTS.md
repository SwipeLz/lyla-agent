# app/ — Production Runtime

## OVERVIEW
FastAPI app + Google ADK agent runtime. All production traffic flows through here. Layered: models → services → tools → agent → api.

## STRUCTURE

```
agent/         # ADK runtime, per-request tool factory, fake agent — see agent/AGENTS.md
api/           # FastAPI handlers + central error mapping — see api/AGENTS.md
integrations/  # WhatsApp stub (no real network call)
models/        # SQLAlchemy ORM, UUID PKs
scheduler/     # APScheduler tick + lifecycle, gated by SCHEDULER_ENABLED
schemas/       # Pydantic request/response, one file per domain
services/      # Business logic — see services/AGENTS.md
tools/         # Phase 3 tool wrappers — see tools/AGENTS.md
tests/         # 186 tests — see tests/AGENTS.md
utils/         # timezone, serialization
config.py      # Settings (pydantic-settings) — single .env, absolute path
db.py          # Session factory
main.py        # FastAPI app + lifespan (starts scheduler if enabled)
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Add ORM table | `models/*.py` + Alembic revision |
| Add business rule | `services/*.py` (raise typed exception) |
| Add tool | `tools/*.py` + register in `agent/tool_factory.py` |
| Add API route | `api/*.py` + `app.include_router(...)` in `main.py` |
| Add Pydantic schema | `schemas/<domain>.py` |
| Map exception → HTTP | `api/_errors.py` (do NOT raise HTTPException in handlers) |

## LAYER RULES (hard)

- **Layer call direction**: api → agent → tools → services → models. Never upward.
- **Services raise** typed exceptions from `services/exceptions.py` (`NotFoundError`, `ValidationError`, `PermissionDeniedError`). Never raise `HTTPException` in services.
- **Tools never raise.** Catch service exceptions inside the wrapper, return failure Tool Result Dict.
- **API handlers async, services sync.** Don't make services async.
- **Importing `app.agent` MUST stay light.** No `google.adk.*` at module load — fake mode hermeticity depends on this. Heavy SDK imports go in `agent/adk_agent.py` and `agent/runtime.py` only.

## ANTI-PATTERNS

- Bypassing services to query `models/` directly from `api/` or `tools/`.
- Raising `HTTPException` outside `api/` — break the central error mapping.
- Catching the wrong exception type in tool wrappers (always re-check `services/exceptions.py`).
- Adding a tool without updating `agent/tool_factory.py` order AND `agents/taskbot_agent/agent.py` stub — parity test fails.

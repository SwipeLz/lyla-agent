---
inclusion: always
---

# Lyla-Taskbot — Project Overview

## What this is

A Bahasa Indonesia voice/text task assistant for students. The user speaks
or types short commands (e.g. *"catat tugas matematika besok"*) and a Google
ADK agent decomposes them into tool calls against a SQLite-backed service
layer. An ESP32 device polls a command queue for short feedback (face,
sound, text); a small dashboard API serves the same data to a web UI.

## Architecture in one paragraph

FastAPI app (`app/`) exposes:
- `POST /agent/text` — the main entry point. Builds a per-request Google ADK
  agent with five tool closures (`create_task`, `create_expense`,
  `set_reminder`, `get_today_summary`, `send_device_command`) bound to the
  request's `db`/`user_id`/`device_id`. Returns a structured
  `AgentRunResult`.
- `/devices/{device_code}/...` — token-gated API the ESP32 polls.
- `/dashboard/...` — task/expense/summary endpoints for the web UI.

A separate package `agents/taskbot_agent/` exists **only** so the ADK CLI
(`adk web`/`adk run`) can discover a top-level `root_agent`. It uses stub
tools — no DB writes — purely for prompt iteration. Production traffic
never touches it.

## Layered design

1. **Models** (`app/models/`) — SQLAlchemy ORM. UUID primary keys.
2. **Services** (`app/services/`) — business logic, raises typed exceptions
   (`ValidationError`, `NotFoundError`, `PermissionDeniedError`).
3. **Tools** (`app/tools/`) — wrap services into Tool Result Dicts; never
   raise; always return `{"success": bool, "type": str, ...}`.
4. **Agent** (`app/agent/`) — runtime, tool factory, ADK builder, fake
   agent, result type.
5. **API** (`app/api/`) — thin FastAPI handlers, validation, error mapping.

## Where the canonical decisions live

- `.kiro/specs/agent-runtime-and-apis/` — Phase 4–8 (current).
- `.kiro/specs/service-layer/` — Phase 3.
- `docs/ARCHITECTURE.md` — durable architectural decisions.
- `docs/AGENT_DESIGN.md` — agent contract and tool surface.
- `docs/ROADMAP.md` — phase status (`(Current)` marker).
- `docs/PHASE*_SUMMARY.md` — what was actually shipped per phase.

If a spec and a doc disagree, **the spec wins** (specs are normative).

## Tech stack

- Python 3.14, FastAPI, SQLAlchemy 2.x, SQLite, Alembic.
- Google ADK (`google-adk>=1.0`) + Gemini.
- APScheduler for reminder ticks.
- Hypothesis for property-based tests, pytest as runner.

## Language conventions

- **Code, docstrings, comments:** English.
- **Agent system prompt + user-facing text:** Bahasa Indonesia.
- **Spec/design docs:** mostly Bahasa Indonesia in `.kiro/specs/`, English
  in `docs/`. Don't translate without being asked.

## Status snapshot (2026-05)

- Phases 0–8 complete. 186/186 tests passing.
- Production agent runtime works through `POST /agent/text`.
- Dev ADK Web UI works via `agents/taskbot_agent/`.
- Single project-root `.env` is the source of truth for `GOOGLE_API_KEY`
  and `GOOGLE_ADK_MODEL` (currently `gemini-3-flash-preview`).

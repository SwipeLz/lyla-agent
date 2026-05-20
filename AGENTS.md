# PROJECT KNOWLEDGE BASE — Lyla / Taskbot

**Generated:** 2026-05-17
**Commit:** afbdb7b
**Branch:** main

Single-file context handoff for the project. Hard rules are normative.
Specs in `.kiro/specs/` win over docs in `docs/` when they disagree.

---

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
- `.kiro/specs/phase-8-5-integration-smoke-test/` — **Phase 8.5 (in-flight)**.
- `docs/ARCHITECTURE.md` — durable architectural decisions.
- `docs/AGENT_DESIGN.md` — agent contract and tool surface.
- `docs/ROADMAP.md` — phase status (`(Current)` marker).
- `docs/PHASE*_SUMMARY.md` — what was actually shipped per phase.
- `docs/FRONTEND_DASHBOARD.md` — frontend SPA runbook (Phase 9).
- `docs/AUDIO_BACKEND.md` — audio backend runbook (Phase 10).
- `docs/SMOKE_TEST.md` — Phase 8.5 smoke-test runbook.
- `docs/PHASE_12_SUMMARY.md` — Phase 12 (observability + auth) shipped artifacts.
- `docs/phase-12/BACKEND_BRIEF.md` — Phase 12 backend brief.
- `docs/phase-12/ESP_BRIEF.md` — Phase 12 ESP firmware brief.

**Before answering "what changed?" / "what was done in phase N?" / "how do I run X?" — read `docs/` first.** The phase summary files (`PHASE_*_SUMMARY.md`) are the ground truth for shipped work; the runbooks are the ground truth for operator workflows. Only fall back to grepping source code or git log if the answer is not in `docs/`.

If a spec and a doc disagree, **the spec wins** (specs are normative).

When you need to search external library/framework docs, use **Context7**.

**For anything touching Google ADK (`google.adk.*`, agent runtime, tool
schema, ADK CLI, Gemini integration), consult the
`google-developer-knowledge` MCP first** (`search_documents` →
`get_documents`). ADK's API surface evolves and the steering files only
capture project-specific gotchas, not the canonical contract. Verify
against Google's docs before changing `app/agent/runtime.py`,
`app/agent/adk_agent.py`, `app/agent/tool_factory.py`, or
`agents/taskbot_agent/agent.py`.

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
- **Phase 8.5 (Integration Smoke Test Backend) is in-flight.** See
  "Current work" below.

---

## Hard rules (don't break these without an explicit user request)

1. **Per-request tool factory.** Each `POST /agent/text` builds fresh tool
   closures via `app.agent.tool_factory.build_tools(db, user_id, device_id)`.
   Never bind context globally; never share an `Agent` across requests.
2. **Hermetic fake agent.** `app/agent/fake.py` and any test file that
   exercises `agent_mode="fake"` MUST NOT import `google.adk.*`. Property
   AR6 (`test_agent_fake_hermeticity.py`) enforces this.
3. **Tools never raise.** Every callable returned by `build_tools` returns
   a Tool Result Dict on both success and failure. Service-layer
   exceptions are caught inside the Phase 3 wrappers in `app/tools/`.
4. **No `typing.Any` in tool signatures.** ADK builds JSON schema via
   `inspect.signature`; `Any` triggers
   `typing.Any cannot be used with isinstance()`. Use concrete types
   (`str | None`, etc.) or omit the annotation on `**_kwargs`.
5. **No `output_schema` on the Agent.** It disables tool-calling on Gemini
   2.x and is unreliable elsewhere. Structured output is assembled by the
   runtime from the event stream.
6. **Single `.env`.** `app/config.py` resolves `.env` by absolute path
   (project root). Don't introduce per-package `.env` files. The dev
   agent loads the same root `.env` into `os.environ` for ADK auth.
7. **Dev agent ↔ prod agent parity.** `agents/taskbot_agent/agent.py`
   imports `INSTRUCTION` and the model from `app.*`. Tool names, order,
   and signatures must match `app.agent.tool_factory`. The parity tests
   in `app/tests/test_dev_agent_parity.py` enforce this.
8. **Audio module hermeticity (AR7).** `app/audio/stt.py`,
   `app/audio/tts.py`, and `app/audio/_seam.py` MUST NOT import any
   provider SDK (`google.cloud.speech`, `google.cloud.texttospeech`,
   `openai`, `whisper`, `elevenlabs`, `deepgram`, `assemblyai`) and MUST
   NOT import `google.adk.*`. Real-provider modules
   (`app/audio/stt_gemini.py`, `app/audio/tts_gemini.py`) MAY import
   provider SDK but ONLY via deferred imports inside method bodies —
   mirroring `app/agent/runtime.py::_run_real`. Module-level provider
   SDK imports remain forbidden everywhere in `app/audio/`. Property is
   enforced by `app/tests/test_audio_fake_hermeticity.py`.

## Soft conventions

- **Type hints everywhere**, including private helpers.
- **Docstrings in English**, even on Indonesian-facing code.
- **UUID strings** for all `id` columns. Never assume `int`.
- **Tool Result Dict shape:** `{"success": bool, "type": str, ...}`.
  On failure include `"error": str`. On `send_device_command` success
  include the original `command` payload so AT4 can verify
  `device_feedback`.
- **Pydantic schemas** in `app/schemas/`, one file per domain.
- **Errors → HTTP** mapped centrally in `app/api/_errors.py`.
- **Async-only** in API handlers and the agent runtime; service layer
  is sync (SQLAlchemy session).

## Testing conventions

- Property-based tests (Hypothesis) for invariants. Use `@given`, bound
  numeric ranges to avoid JSON precision issues (±(2^53−1) for ints).
- Use the autouse network kill-switch fixture in `app/tests/conftest.py`.
  Don't disable it; if you need real network in a test, add an explicit
  `monkeypatch.setattr` in that test only.
- Run the full suite before declaring a task done:
  `python -m pytest -q`.

## Git etiquette

- Don't commit `.env`. The `.gitignore` excludes it.
- Don't commit `*.db`, `__pycache__/`, `.hypothesis/`, `.adk/`.
- Keep `.env.example` in sync when adding new settings.
- Don't push to `main` directly. Always a feature branch + PR.

---

## Runbook — common commands

All commands assume CWD = project root unless noted.

### First-time setup

```cmd
:: 1. Install deps
pip install -r requirements.txt

:: 2. Create .env from the template and fill in GOOGLE_API_KEY
copy .env.example .env

:: 3. Apply migrations
alembic upgrade head

:: 4. Seed a demo user + device (prints the IDs you need)
python -m scripts.seed_dev
```

### Run the production server

```cmd
uvicorn app.main:app --reload
```

Then:
- Swagger UI: <http://localhost:8000/docs>
- Health: <http://localhost:8000/healthz>
- Main agent endpoint: `POST /agent/text`

### Talk to the production agent

Three options, all hit real services + DB:

```cmd
:: A) Manual CLI (easiest for smoke tests)
python -m scripts.run_agent_text "catat tugas matematika besok"

:: B) cURL
curl -X POST http://localhost:8000/agent/text ^
  -H "Content-Type: application/json" ^
  -d "{\"user_id\":\"<uuid>\",\"device_id\":\"<uuid>\",\"text\":\"...\"}"

:: C) Open /docs and use "Try it out" on POST /agent/text
```

### Run the ADK Dev UI

```cmd
:: From PROJECT ROOT (the parent of agents/), not from inside agents/
adk web --port 8000
:: Then open http://localhost:8000 and pick "taskbot_agent" in the dropdown
```

If the dropdown shows top-level project folders (`app`, `docs`, `scripts`)
instead of `taskbot_agent`, you are running `adk web` from the wrong
directory.

### Tests

```cmd
:: Full suite
python -m pytest -q

:: Just one area
python -m pytest app/tests/test_agent_runtime.py -v

:: Parity (dev agent vs prod factory)
python -m pytest app/tests/test_dev_agent_parity.py -v
```

### Change the Gemini model

Edit one line in the project root `.env`:

```bash
GOOGLE_ADK_MODEL=gemini-3-flash-preview
```

Restart `uvicorn` and/or `adk web`.

### Toggle scheduler / dashboard auth

Same root `.env`:

```bash
SCHEDULER_ENABLED=true            # background reminder ticks
SCHEDULER_INTERVAL_SECONDS=60

DASHBOARD_AUTH_MODE=shared_header # or "none" for MVP
DASHBOARD_TOKEN=<random-string>
```

### Common failures & fixes

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` from `adk web` | Run from project root, not `agents/`. Or use the `sys.path` bootstrap that already exists in `agents/taskbot_agent/agent.py`. |
| Toast: `typing.Any cannot be used with isinstance()` | Don't use `typing.Any` in tool signatures. Use concrete types. |
| `gemini-X model not found` | The `GOOGLE_ADK_MODEL` value isn't a valid alias for your API key. Try `gemini-2.5-flash` as a fallback. |
| `_make_subprocess_transport NotImplementedError` (Windows) | Use `adk web --no-reload`. |
| Dev agent dropdown empty after edits | Restart `adk web`. It caches modules. |
| Tests pass locally but `adk web` is silent | Real UI shows errors as toasts; check the terminal where `adk web` runs for the actual traceback. |

---

## Current work — Phase 8.5 (Integration Smoke Test Backend)

**Status:** in-flight. Spec at `.kiro/specs/phase-8-5-integration-smoke-test/`.
Read the three files in this order before touching anything:

1. `requirements.md` — 12 normative requirements + glossary
2. `design.md` — components, sequence, decisions
3. `tasks.md` — leaf tasks with Req ↔ Property mapping

### What Phase 8.5 ships

Exactly two new files. Strictly additive:

- `scripts/smoke_test_backend.py` — single-file CLI (~400 LOC).
  Invoked as `python -m scripts.smoke_test_backend [--real-agent] [--verbose]`.
  Runs six Smoke Steps in order: Demo Fixture Lookup → Agent Runtime (fake)
  → VoiceCommandLog Persistence → Dashboard Summary Read-Back →
  Device Command Lifecycle → Scheduler Tick.
- `docs/SMOKE_TEST.md` — runbook-style usage doc (English).

### Hard constraints (Phase 8.5 specific, on top of the global hard rules)

- **No changes** under `app/`, `agents/taskbot_agent/`, `app/migrations/`,
  or `requirements.txt`.
- **No new service-layer methods.** Database-read gaps are documented in
  `design.md` §"Database-Read Gap Audit" and filled by inline ORM queries
  in the script (Req 12.4, 12.5).
- **No new pytest test.** `app/tests/test_smoke_flow.py` is explicitly
  NOT added (`design.md` §13). The existing 186 tests remain the only
  pytest regression gate.
- **No uvicorn boot, no HTTP client to `app.main:app`.** Dashboard
  read-back goes directly through `app.tools.summary_tools.get_today_summary_tool`
  in-process. The script must NOT import `httpx`, `requests`,
  `urllib.request`, `uvicorn`, or `fastapi.testclient`.
- **Network hermeticity in default mode.** The script installs its own
  `socket.*` monkeypatch (does NOT depend on the autouse fixture in
  `app/tests/conftest.py`). Loopback always allowed; Gemini hosts
  allowed only with `--real-agent`. Post-run `sys.modules` diff catches
  any new `google.adk.*` / `google.genai.*` import in default mode.
- **No APScheduler instance.** Step 6 calls `app.scheduler.tick.reminder_tick(db_factory=SessionLocal)`
  directly. The script must NOT import `BackgroundScheduler`,
  `BlockingScheduler`, or `AsyncIOScheduler`, and must NOT call
  `app.scheduler.lifecycle.start_scheduler`.
- **No `.env` mutation.** `_SmokeSettingsOverride` is a context manager
  that mutates `app.config.settings.agent_mode` in-memory only and
  restores it on exit. Never `open(".env", "w")`, `dotenv.set_key`, etc.

### Demo fixtures (literals the script depends on)

- `User.email == "demo@taskbot.local"`
- `Device.device_code == "TASKBOT-DEMO-001"`

Both are produced by `python -m scripts.seed_dev`. Missing → exit code 3
with stderr message containing both `python -m alembic upgrade head` and
`python -m scripts.seed_dev` literals.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | PASS |
| 1 | FAIL |
| 2 | `--real-agent` without `GOOGLE_API_KEY` |
| 3 | Demo Fixture missing |

### Acceptance gate (Definition of Done)

- 5 manual runs pass (default PASS, exit 3 on missing fixture, exit 2 on
  missing key, injected failure under `--verbose` shows traceback,
  optional `--real-agent` smoke).
- Static audit grep clean for forbidden patterns (Property 3, 13, 16,
  19, 21).
- `python -m pytest -q` still reports `186 passed`.
- `git diff --stat` shows only the two new files.


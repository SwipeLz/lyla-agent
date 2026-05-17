# Handover — Lyla-Taskbot

Single entry point for anyone (human or AI) picking up this repo. If you read
this top-to-bottom you'll have enough context to keep building without asking
"how does X work" for most things.

> **For Kiro on a different account:** the steering files in
> `.kiro/steering/` are loaded into every conversation automatically when
> you open this repo. You don't need to do anything extra.

---

## What is this?

A Bahasa Indonesia task assistant for students. A Google ADK agent (Gemini)
turns short Indonesian commands into tool calls against a SQLite service
layer. An ESP32 device polls a command queue; a small dashboard API serves
the web UI.

See **`.kiro/steering/01-project-overview.md`** for the architecture.

## Status (as of 2026-05)

- **Phases 0–8 complete.** 186/186 tests passing.
- Production agent reachable via `POST /agent/text`.
- ADK Web dev UI reachable via `agents/taskbot_agent/`.
- Single project-root `.env` controls model + API key.
- Current Gemini model: `gemini-3-flash-preview` (override in `.env`).

## Read order

1. `README.md` — quickstart.
2. `.kiro/steering/01-project-overview.md` — architecture.
3. `.kiro/steering/02-conventions.md` — hard + soft coding rules.
4. `.kiro/steering/03-runbook.md` — every command you'll need.
5. `docs/ARCHITECTURE.md` — durable design decisions.
6. `docs/AGENT_DESIGN.md` — agent contract.
7. `docs/ADK_DEV_UI.md` — dev UI workflow + dual-agent rationale.
8. `docs/PHASE4_8_SUMMARY.md` — what shipped in the current phase.
9. `.kiro/specs/agent-runtime-and-apis/` — normative requirements + design
   for the current phase. **Specs win when in doubt.**

## Quick reference (full version in the runbook steering)

```cmd
pip install -r requirements.txt
copy .env.example .env             :: then add your GOOGLE_API_KEY
alembic upgrade head
python -m scripts.seed_dev         :: prints user_id / device_id
uvicorn app.main:app --reload      :: http://localhost:8000/docs
```

Three ways to talk to the production agent:

```cmd
:: A) CLI
python -m scripts.run_agent_text "catat tugas matematika besok"

:: B) Swagger UI: http://localhost:8000/docs → POST /agent/text → Try it out

:: C) cURL (paste UUIDs from seed_dev)
curl -X POST http://localhost:8000/agent/text -H "Content-Type: application/json" ^
  -d "{\"user_id\":\"<uuid>\",\"device_id\":\"<uuid>\",\"text\":\"...\"}"
```

Iterate on the prompt with the ADK Dev UI:

```cmd
:: From PROJECT ROOT (the parent of agents/), not from inside agents/
adk web --port 8000
:: Pick "taskbot_agent" in the dropdown
```

## Layout cheatsheet

```
app/                       # production runtime
├── agent/                 # runtime, tool factory, ADK builder, fake agent
├── api/                   # FastAPI handlers (agent, devices, dashboard)
├── models/                # SQLAlchemy ORM (UUID PKs)
├── schemas/               # Pydantic request/response models
├── scheduler/             # APScheduler tick + lifecycle
├── services/              # business logic (raises typed exceptions)
├── tools/                 # service wrappers → Tool Result Dicts
└── tests/                 # 186 tests, ~27 property-based

agents/taskbot_agent/      # ADK Dev UI shell — stub tools only
.kiro/specs/               # normative requirements + design + tasks
.kiro/steering/            # auto-loaded into every Kiro session
.vscode/settings.json      # workspace-level trusted commands for Kiro
docs/                      # human-readable architecture + summaries
scripts/                   # seed_dev, run_agent_text CLI
alembic/                   # migrations
```

## Key decisions (from recent sessions)

These are nuances not always obvious from reading the code alone.

### Dual-agent split

- **Production agent** lives in `app/agent/` and is built **per HTTP
  request** so it can inject `db`/`user_id`/`device_id` into the tool
  closures. There is no module-level `Agent` instance.
- **Dev agent** lives in `agents/taskbot_agent/` and exposes a
  module-level `root_agent` purely so `adk web`/`adk run` can find it.
  Its tools are **stubs** — they don't write to the DB.
- The two share `INSTRUCTION` and `settings.google_adk_model` by import,
  so there's nothing to keep in sync manually. Tool name/order/signature
  parity is locked by `app/tests/test_dev_agent_parity.py`.
- ADK Web is officially "development only"; production traffic must go
  through `POST /agent/text`, never through the dev shell.

### Single source of truth for env

- `app/config.py` resolves `.env` by absolute path (project root), so it
  works from any CWD (uvicorn from root, pytest, `adk web` from
  `agents/`, scripts in `scripts/`).
- The dev agent additionally calls `dotenv.load_dotenv(<root>/.env)` so
  ADK's own `os.environ["GOOGLE_API_KEY"]` lookup works.
- **Don't add per-package `.env` files.** Edit only the project root one.

### Things that bit us, captured here so you don't repeat them

- ADK builds tool JSON schema via `inspect.signature`. `typing.Any` in a
  tool param triggers `typing.Any cannot be used with isinstance()`.
  Always use concrete types or unannotated `**_kwargs`.
- `output_schema` on the `Agent` disables tool calling on Gemini 2.x
  (and is unreliable elsewhere). We assemble structured output from the
  event stream instead, in `app/agent/runtime.py`.
- ADK CLI tools must be run from the **parent** of the agents folder.
  Running `adk web` inside `agents/` makes the dropdown list random
  project subfolders as "apps".
- The fake agent must remain hermetic — do not import `google.adk.*`
  anywhere it can be reached. Property AR6
  (`app/tests/test_agent_fake_hermeticity.py`) enforces this.
- Hypothesis ints can break JSON precision. Bound numeric strategies to
  ±(2^53 − 1).

## What's next

Open suggestions, not commitments:

- Replace the WhatsApp stub (`app/integrations/whatsapp.py`) with the
  real Graph API integration.
- Build the dashboard frontend against `/dashboard/*`.
- Promote `dashboard_auth_mode` from `"none"` to `"shared_header"` (or
  JWT) before exposing the dashboard publicly.
- Add agent memory / multi-turn session state — currently every request
  uses a fresh `InMemorySessionService` and a random `session_id`.
- Wire real device hardware tests against the existing
  `/devices/{device_code}/...` endpoints.

## How to package this for another AI

If you're handing this off to a one-shot AI (ChatGPT, Claude.ai), upload
in this order; it's enough for them to be productive:

1. `HANDOVER.md` (this file)
2. `.kiro/steering/01-project-overview.md`
3. `.kiro/steering/02-conventions.md`
4. `.kiro/steering/03-runbook.md`
5. `.kiro/specs/agent-runtime-and-apis/requirements.md`
6. `.kiro/specs/agent-runtime-and-apis/design.md`
7. `docs/ARCHITECTURE.md`
8. `docs/AGENT_DESIGN.md`
9. `docs/PHASE4_8_SUMMARY.md`
10. The specific source files relevant to whatever you're asking about.

If it's another **Kiro** session on a different account, just clone the
repo. The steering files are auto-loaded.

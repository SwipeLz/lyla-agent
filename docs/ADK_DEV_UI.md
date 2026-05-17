# ADK Dev UI Guide

This document explains the **dual-agent setup** in this project and how to use
the ADK developer tools (`adk web`, `adk run`, `adk api_server`) to iterate on
the LLM behaviour interactively.

---

## TL;DR

- **Production agent** lives in `app/agent/` and runs through `POST /agent/text`.
- **Dev agent** lives in `agents/taskbot_agent/` and is only used by ADK CLI tools.
- They share the same **system instruction** and **tool signatures** by import.
- Dev tools are **stubs** (no DB writes); for real DB execution use the API.

```bash
# 1) Put your API key in .env at the project root
# 2) From the project root:
adk web --port 8000
# 3) Open http://localhost:8000 and pick "taskbot_agent" in the dropdown
```

---

## Why Two Agents?

The production runtime needs request-scoped context — `db`, `user_id`,
`device_id` — bound into the tools. We do that with a **per-request factory**:

```python
# app/agent/runtime.py
async def run_text(db, *, user_id, device_id, text, timezone):
    tools = build_tools(db, user_id, device_id)   # closures bind context
    agent = build_taskbot_agent(model=..., tools=tools)
    # ... run via google.adk.runners.Runner
```

The ADK CLI tools (`adk web` etc.) discover agents differently. They
**import a module** at process-start and read a top-level `root_agent`
symbol — long before any HTTP request exists, so there's nothing to bind.

This is a fundamental shape mismatch between:

| Concern              | Production runtime                          | ADK CLI tools                       |
| -------------------- | ------------------------------------------- | ----------------------------------- |
| Agent lifetime       | Built fresh per HTTP request                | Imported once at process start      |
| Tool context         | `db`/`user_id`/`device_id` bound in closure | None — single shared session        |
| Multi-user           | Yes (different users per request)           | No (single dev session)             |
| Recommended for      | Production deployment                       | Development & debugging only        |

ADK's own docs say it explicitly:

> *ADK Web is not meant for use in production deployments. You should use ADK
> Web for development and debugging purposes only.*

So we keep the two paths separate but synchronised.

---

## Repository Layout

```
Lyla-Taskbot/
├── app/                        # ─── Production runtime ───
│   ├── agent/
│   │   ├── adk_agent.py        # build_taskbot_agent(model, tools) factory
│   │   │                         # ── exports INSTRUCTION (shared constant)
│   │   ├── tool_factory.py     # build_tools(db, user_id, device_id) — closures
│   │   ├── runtime.py          # run_text() entry point
│   │   ├── fake.py             # hermetic fake agent (no ADK import)
│   │   └── result.py           # AgentRunResult dataclass
│   └── api/agent.py            # POST /agent/text handler
│
├── agents/                     # ─── ADK Dev UI agents ───
│   └── taskbot_agent/
│       ├── __init__.py         # `from . import agent`  ← ADK discovery
│       └── agent.py            # root_agent = Agent(...)  ← ADK discovery
│                                 # ── imports INSTRUCTION & model from app.*
│                                 # ── loads project-root .env into os.environ
│
└── app/tests/
    └── test_dev_agent_parity.py  # locks dev/prod parity (3 tests)
```

The `agents/` directory is the ADK convention — running `adk web` from
inside it makes ADK enumerate every immediate subfolder containing a
`__init__.py`.

---

## How Drift Is Prevented

The dev agent **imports** rather than copies the parts that must match:

```python
# agents/taskbot_agent/agent.py
from app.agent.adk_agent import INSTRUCTION    # same Indonesian system prompt
from app.config import settings                # same model identifier

root_agent = Agent(
    name="taskbot_agent",
    model=settings.google_adk_model,
    instruction=INSTRUCTION,
    tools=_DEV_TOOLS,
)
```

Tool *signatures* (names + parameters) are guarded by parity tests:

```python
# app/tests/test_dev_agent_parity.py
def test_dev_agent_tool_names_match_production_order(): ...
def test_dev_agent_tool_signatures_match_production(): ...
def test_dev_agent_uses_production_instruction(): ...
```

Run them whenever you touch either file:

```bash
pytest app/tests/test_dev_agent_parity.py -v
```

If you add a 6th tool to production, these tests fail until you mirror it
in the dev agent. That's the safety net.

---

## What the Dev Tools Do (and Don't Do)

The five stub functions in `agents/taskbot_agent/agent.py` are intentionally
**fake**: they validate arguments and return well-shaped Tool Result Dicts,
but they do **not** write to the database.

| Tool                  | Dev stub behaviour                                  |
| --------------------- | --------------------------------------------------- |
| `create_task`         | Echoes the task fields back as a success dict       |
| `create_expense`      | Validates `amount > 0`, then echoes back            |
| `set_reminder`        | Validates `channel`, then echoes back               |
| `get_today_summary`   | Returns hard-coded fake counts                      |
| `send_device_command` | Validates at least one of `face/sound/text` is set  |

This is enough to:

- Iterate on the Indonesian system prompt and watch how Gemini decomposes
  user requests into tool calls.
- Sanity-check tool argument names, types, and Indonesian docstrings.
- Spot prompt regressions before they reach production tests.

For **real** end-to-end runs against the SQLite DB, use either:

```bash
# Option A — the FastAPI endpoint
curl -X POST http://localhost:8000/agent/text \
  -H "Content-Type: application/json" \
  -d '{"user_id":"...","device_id":"...","text":"catat tugas matematika besok"}'

# Option B — the manual CLI
python -m scripts.run_agent_text "catat tugas matematika besok"
```

Both go through `app.agent.runtime.run_text` and exercise the real Phase 3
service layer.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

`google-adk>=1.0` is already in `requirements.txt`.

### 2. Provide a Google API key

Edit the **project root** `.env` file:

```bash
GOOGLE_API_KEY=YOUR_KEY_HERE
GOOGLE_ADK_MODEL=gemini-3-flash-preview   # or any other supported Gemini model
```

That single file is the source of truth for both production (`uvicorn`) and
the dev UI (`adk web`). Get a free key from
<https://aistudio.google.com/app/apikey>.

> No per-agent `.env` is required. The dev agent module loads the project
> root `.env` automatically via ``python-dotenv`` so ADK's auth works from
> any CWD.

### 3. Verify discovery

```bash
python -c "from agents.taskbot_agent import agent; print(agent.root_agent.name)"
# Expected: taskbot_agent
```

---

## Running the Dev UI

Always run from the **project root** (which is the parent of `agents/`):

```bash
adk web --port 8000
```

Then:

1. Open <http://localhost:8000>
2. In the top-left dropdown, select **`taskbot_agent`**
3. Type a request, e.g. *"catat tugas matematika besok jam 10"*
4. Use the **Events** tab to inspect every function call, its arguments, and
   the model's response

> **Windows note.** If you hit `_make_subprocess_transport NotImplementedError`,
> use `adk web --no-reload` instead.

### Other ADK entry points

```bash
# Terminal-only chat
adk run agents/taskbot_agent

# Local REST server (for cURL testing without our FastAPI app)
adk api_server agents/taskbot_agent
```

---

## Common Workflow

1. Want to tweak the system prompt? Edit `INSTRUCTION` in
   `app/agent/adk_agent.py`. The dev agent picks it up automatically on the
   next reload.
2. Restart `adk web` (Ctrl+C and re-run) to reload the prompt.
3. Try a few user messages in the UI; inspect tool calls in the Events tab.
4. Once happy, stop `adk web`, restart `uvicorn app.main:app`, and test the
   real endpoint with the same prompts.
5. Run the parity tests before committing:

   ```bash
   pytest app/tests/test_dev_agent_parity.py app/tests/test_agent_runtime.py
   ```

---

## Production-Readiness Checklist

The dev agent does **not** affect production. The production runtime
(`app/agent/`) remains:

- [x] Built per-request with bound context
- [x] Backed by real Phase 3 service-layer tools
- [x] Covered by 27+ property-based tests (Hypothesis)
- [x] Hermetically separable from ADK in fake mode (Property AR6)
- [x] Wired through `POST /agent/text` and `scripts/run_agent_text.py`

The only thing the dev agent adds is a **separate, parallel surface** for
interactive experimentation. Deployments should not bundle or expose
`agents/` at all.

---

## Troubleshooting

| Symptom                                                          | Likely cause / fix                                                                                |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `taskbot_agent` not in dropdown                                  | You ran `adk web` from the wrong directory. Run from project root (parent of `agents/`).          |
| `ImportError: cannot import name 'INSTRUCTION'`                  | Editable install missing. Run `pip install -e .` or just `pip install -r requirements.txt`.       |
| Tool calls fail with "API key not valid"                         | The project-root `.env` has no `GOOGLE_API_KEY`, or the key is expired.                           |
| Parity test fails after a refactor                               | Update `agents/taskbot_agent/agent.py` to mirror the new tool name/signature in the prod factory. |
| `_make_subprocess_transport NotImplementedError` (Windows)       | Use `adk web --no-reload`.                                                                        |
| Dev tools are returning fake numbers                             | That's by design. Use `POST /agent/text` for real DB execution.                                   |

---

## File Index

| File                                       | Purpose                                                            |
| ------------------------------------------ | ------------------------------------------------------------------ |
| `agents/taskbot_agent/__init__.py`         | ADK discovery hook (`from . import agent`)                         |
| `agents/taskbot_agent/agent.py`            | Module-level `root_agent` with stub tools                          |
| `.env` (project root)                      | Single source of truth for `GOOGLE_API_KEY` and `GOOGLE_ADK_MODEL` |
| `app/agent/adk_agent.py`                   | Production agent factory + shared `INSTRUCTION` constant            |
| `app/agent/tool_factory.py`                | Production per-request tool builder (5 closures)                   |
| `app/tests/test_dev_agent_parity.py`       | 3 tests preventing dev/prod drift                                  |
| `docs/ADK_DEV_UI.md` *(this file)*         | Workflow guide                                                     |

# agents/taskbot_agent/ — ADK Dev UI Shell

## OVERVIEW
**Dev-only**. Exists so `adk web` / `adk run` can discover a top-level `root_agent`. Tools here are **stubs** — they validate args and return Tool Result Dicts but DO NOT touch the database. Production traffic goes through `POST /agent/text`, never here.

## FILES

```
agent.py       # root_agent + 5 stub tools, mirrors prod tool signatures
__init__.py
```

## DRIFT PREVENTION

These are imported from production (do NOT redefine locally):

- `INSTRUCTION` ← `app.agent.adk_agent.INSTRUCTION`
- model ← `app.config.settings.google_adk_model`

Tool **names, order, and signatures** must match `app.agent.tool_factory.build_tools(...)`. Parity is locked by `app/tests/test_dev_agent_parity.py`. Add or rename a tool in `app/agent/tool_factory.py` → mirror it here in the same order with the same parameter types.

## PATH BOOTSTRAP

`agent.py` prepends `<project_root>` to `sys.path` and calls `dotenv.load_dotenv(<root>/.env)` so `adk web` can be run from any CWD without a per-package `.env`. Do NOT add `agents/taskbot_agent/.env` — `.gitignore` excludes per-agent envs intentionally.

## RUNNING

From PROJECT ROOT (the parent of `agents/`):

```bash
adk web --port 8000          # dropdown will show "taskbot_agent"
# Windows: adk web --no-reload  (works around _make_subprocess_transport)
```

If the dropdown lists `app`, `docs`, `scripts` instead of `taskbot_agent`, you're running from inside `agents/`. Stop and run from project root.

## ANTI-PATTERNS

- **Adding a per-agent `.env`** — `.gitignore` already excludes it; would create two sources of truth.
- **Wiring the stubs to a real DB** — defeats the purpose; production has its own factory.
- **Routing real requests here** — production must use `POST /agent/text`.
- **Renaming/reordering a tool here without updating `app/agent/tool_factory.py`** — parity test fails.
- **Local copies of `INSTRUCTION`** — must always be imported from `app.agent.adk_agent`.

---
inclusion: always
---

# Runbook — common commands

All commands assume CWD = project root unless noted.

## First-time setup

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

## Run the production server

```cmd
uvicorn app.main:app --reload
```

Then:
- Swagger UI: <http://localhost:8000/docs>
- Health: <http://localhost:8000/healthz>
- Main agent endpoint: `POST /agent/text`

## Talk to the production agent

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

## Run the ADK Dev UI

```cmd
:: From PROJECT ROOT (the parent of agents/), not from inside agents/
adk web --port 8000
:: Then open http://localhost:8000 and pick "taskbot_agent" in the dropdown
```

If the dropdown shows top-level project folders (`app`, `docs`, `scripts`)
instead of `taskbot_agent`, you are running `adk web` from the wrong
directory.

## Tests

```cmd
:: Full suite
python -m pytest -q

:: Just one area
python -m pytest app/tests/test_agent_runtime.py -v

:: Parity (dev agent vs prod factory)
python -m pytest app/tests/test_dev_agent_parity.py -v
```

## Change the Gemini model

Edit one line in the project root `.env`:

```bash
GOOGLE_ADK_MODEL=gemini-3-flash-preview
```

Restart `uvicorn` and/or `adk web`.

## Toggle scheduler / dashboard auth

Same root `.env`:

```bash
SCHEDULER_ENABLED=true            # background reminder ticks
SCHEDULER_INTERVAL_SECONDS=60

DASHBOARD_AUTH_MODE=shared_header # or "none" for MVP
DASHBOARD_TOKEN=<random-string>
```

## Common failures & fixes

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` from `adk web` | Run from project root, not `agents/`. Or use the `sys.path` bootstrap that already exists in `agents/taskbot_agent/agent.py`. |
| Toast: `typing.Any cannot be used with isinstance()` | Don't use `typing.Any` in tool signatures. Use concrete types. |
| `gemini-X model not found` | The `GOOGLE_ADK_MODEL` value isn't a valid alias for your API key. Try `gemini-2.5-flash` as a fallback. |
| `_make_subprocess_transport NotImplementedError` (Windows) | Use `adk web --no-reload`. |
| Dev agent dropdown empty after edits | Restart `adk web`. It caches modules. |
| Tests pass locally but `adk web` is silent | Real UI shows errors as toasts; check the terminal where `adk web` runs for the actual traceback. |


## Trusted Commands & Tools (auto-approval)

This repo ships with a workspace-level setting at
`.vscode/settings.json` that pre-approves the common shell commands used
in this project (`python *`, `pytest *`, `alembic *`, `uvicorn *`,
`adk *`, `git *`, etc.) so Kiro can run them without prompting.

### How precedence works

| Layer | File | Wins over |
|---|---|---|
| Workspace | `.vscode/settings.json` (this repo) | User-level |
| User | `%APPDATA%\Kiro\User\settings.json` | — |

A pattern in the workspace file applies to every account that clones the
repo. A pattern in the user file applies only to your machine.

### Add a new trusted command for everyone

1. Open `.vscode/settings.json`.
2. Add a glob pattern to `kiroAgent.trustedCommands`. E.g.
   `"npm run lint *"` would auto-approve `npm run lint`, `npm run lint --fix`,
   etc.
3. Commit.

### Add a personal trusted command (not committed)

Edit `%APPDATA%\Kiro\User\settings.json` and add to the same array
there. Don't commit user-level settings.

### Glob syntax cheat sheet

- `cmd *` matches `cmd <anything>` including no args.
- `cmd` (no `*`) matches the exact command only.
- Backslashes need escaping in JSON: `".venv\\Scripts\\python.exe *"`.

### Sync between accounts

Workspace file is auto-synced via git. For user-level patterns, just
copy the `kiroAgent.trustedCommands` and `kiroAgent.trustedTools` keys
from the source account's `%APPDATA%\Kiro\User\settings.json` to the
target account's same file.

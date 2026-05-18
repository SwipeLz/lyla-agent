# scripts/ — CLI Entry Points

## OVERVIEW
Operator-facing scripts. All run as `python -m scripts.<name>` from the project root so `app.*` imports resolve.

## FILES

```
seed_dev.py            # creates a demo user + device, prints UUIDs to stdout
run_agent_text.py      # send a single text command through the production agent
smoke_test_backend.py  # end-to-end smoke against a running uvicorn
__init__.py
```

## USAGE

```bash
# Seed (run once after alembic upgrade head)
python -m scripts.seed_dev
# → prints user_id and device_id; copy these for the next steps

# Talk to the production agent (real DB, fake or real Gemini)
python -m scripts.run_agent_text "catat tugas matematika besok" \
  --user-id <uuid> [--device-id <uuid>]

# Or rely on env fallbacks
$env:TASKBOT_USER_ID="<uuid>"
$env:TASKBOT_DEVICE_ID="<uuid>"
python -m scripts.run_agent_text "ringkasan hari ini"

# Force hermetic / offline run
$env:AGENT_MODE="fake"; python -m scripts.run_agent_text "..."
```

## CONTRACT

- **`run_agent_text`** prints a JSON `{reply, actions, device_feedback, status}` line to stdout. Empty/whitespace text exits non-zero with a usage message on stderr.
- **`seed_dev`** is idempotent enough for dev — re-running creates a fresh demo set; don't rely on stable IDs across runs.
- **`smoke_test_backend`** assumes uvicorn is already running on `localhost:8000`.

## ANTI-PATTERNS

- Running scripts as `python scripts/run_agent_text.py` — `app.*` import fails. Always use `python -m scripts.<name>`.
- Adding production logic here — scripts are thin orchestrators around `app.*`.
- Hardcoding UUIDs from a previous `seed_dev` run — re-seeding changes them.
- Bypassing `run_agent_text` to call `app.agent.runtime` directly in scripts — duplicates the CLI's argument/env handling.

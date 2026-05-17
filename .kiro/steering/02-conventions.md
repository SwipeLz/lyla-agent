---
inclusion: always
---

# Coding Conventions

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

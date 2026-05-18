# app/tools/ — Tool Wrappers

## OVERVIEW
Phase 3 layer. Plain Python wrappers around services that NEVER raise and ALWAYS return a Tool Result Dict. Exposed to the LLM through `app/agent/tool_factory.py`.

## FILES

```
task_tools.py      # create_task wrapper
expense_tools.py   # create_expense wrapper (positive int rupiah)
reminder_tools.py  # set_reminder wrapper (channel: whatsapp|device|both)
summary_tools.py   # get_today_summary wrapper
device_tools.py    # send_device_command wrapper
```

## TOOL RESULT DICT (universal contract)

```python
# Success
{"success": True, "type": "task", "task_id": "<uuid>", "message": "...", ...}

# Failure
{"success": False, "type": "task", "error": "<short Indonesian or English string>"}
```

- `type` is the domain string (`task`, `expense`, `reminder`, `summary`, `device_command`).
- On success, include the created object's id and any field needed by callers.
- **`send_device_command` success MUST echo the original `command` payload** so AT4 (`/agent/text` integration) can verify `device_feedback`.
- On failure, include `error: str`. Never include stack traces.

## RULES

- **Tools never raise.** Wrap every service call in try/except for the typed exceptions in `services/exceptions.py`. Convert each to a failure Tool Result Dict.
- **No `typing.Any`** in the wrapper signature — ADK builds JSON schema via `inspect.signature` and crashes. Use concrete types or unannotated `**_kwargs`.
- **Validate at the boundary.** Cheap validations (channel enum, non-empty title) can fail fast here without entering the service.
- **Identical signatures in dev shell.** `agents/taskbot_agent/agent.py` mirrors these signatures (with stub bodies). Parity is enforced by `app/tests/test_dev_agent_parity.py` — keep names, order, and types in lockstep.

## ANTI-PATTERNS

- Returning `None` or raising — breaks the agent runtime contract.
- Adding business logic here. Logic belongs in `services/`; tools just wrap.
- Forgetting to echo `command` in `send_device_command` success — `device_feedback` test fails silently.
- Different param order between this file and the dev stub — parity test fails.

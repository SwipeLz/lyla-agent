# app/agent/ — Agent Runtime

## OVERVIEW
Agent runtime: per-request ADK agent, tool factory with closure-injected context, hermetic fake agent for tests, structured result type.

## FILES

```
__init__.py        # MUST stay light. No google.adk imports here.
adk_agent.py       # INSTRUCTION (Indonesian system prompt) + ADK Agent builder
fake.py            # Hermetic keyword-detection agent. NO google.adk imports.
result.py          # AgentRunResult dataclass {reply, actions, device_feedback}
runtime.py         # run_text() entry, dispatches to real or fake by AGENT_MODE
tool_factory.py    # build_tools(db, user_id, device_id) → 5 closures
```

## CONTRACT

`run_text(text, db, user_id, device_id, mode) -> AgentRunResult`

- `mode="real"` → builds an ADK `Agent` per call with fresh closures, runs event stream, assembles `AgentRunResult` from events (NOT from `output_schema`).
- `mode="fake"` → keyword-routes to the same tool callables. No network. No google-adk import reachable.
- Mode auto-resolves: `real` if `GOOGLE_API_KEY` set, else `fake`.

## INJECTED CONTEXT

`db`, `user_id`, `device_id` are bound to tool callables via closure in `build_tools(...)`. They do NOT appear in the JSON schema the LLM sees. If the model passes them in `**kwargs`, the runtime ignores them and uses the closure values.

`device_id is None` → `send_device_command` short-circuits to failure Tool Result Dict without entering `services/`.

## ANTI-PATTERNS

- **Importing `google.adk.*` in `fake.py` or `__init__.py`** → breaks hermeticity. AR6 test enforces.
- **Module-level `Agent` instance** → forbidden. Always per-request via the factory.
- **`output_schema` on `Agent`** → kills tool-calling on Gemini 2.x. Assemble result from events.
- **`typing.Any` in tool signatures** → ADK schema build crashes. Concrete types only.
- **Drift in `INSTRUCTION` or model name** → dev shell imports both, so edit here only.

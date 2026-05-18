# app/tests/ — Test Suite

## OVERVIEW
186 tests, ~27 property-based (Hypothesis). Pytest as runner. Network is killed by an autouse fixture; fake-mode agent runs offline by design.

## CRITICAL FIXTURES (in `conftest.py`)

- **Network kill-switch (autouse)** — patches socket-level egress. Don't disable globally. If a single test genuinely needs network, add a scoped `monkeypatch.setattr` in that test only.
- **In-memory SQLite + Alembic-applied schema** — every test gets a fresh DB.

## SPECIAL TESTS (do NOT delete or weaken)

| File | Why it exists |
|------|---------------|
| `test_agent_fake_hermeticity.py` | Property AR6: fake agent path must not import `google.adk.*`. Enforces hermeticity. |
| `test_dev_agent_parity.py` | Locks tool names, order, and signatures between `app/agent/tool_factory.py` (prod) and `agents/taskbot_agent/agent.py` (dev shell). |
| `test_schema_invariant.py` | Property tests on Pydantic schemas — bound numerics to ±(2^53−1) for JSON precision. |
| `test_utils_properties.py` | Timezone + serialization invariants (Hypothesis). |

## CONVENTIONS

- **Hypothesis numeric strategies** must be bounded: `st.integers(min_value=-(2**53-1), max_value=2**53-1)`. Unbounded ints break JSON precision and the test fails non-deterministically.
- **Use the autouse network kill-switch.** Tests that hit Gemini are forbidden by default (fake mode is the test path).
- **Run the full suite before declaring done:** `python -m pytest -q`. 186/186 must pass.
- **Don't catch `ValidationError` from `app.services.exceptions`** in tests just to "make it pass" — adjust the input or fix the service.

## ANTI-PATTERNS

- Deleting a failing property test "to unblock" — it's catching a real bug. Diagnose root cause.
- Mocking `google.adk.*` to test fake mode — hermeticity test would still fail because the import itself happens at module load. Use real fake-mode path.
- Adding a tool without updating `test_dev_agent_parity.py` expectations.
- Importing `google.adk.*` from a test module that exercises `agent_mode="fake"`.

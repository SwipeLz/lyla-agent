# Agent Verification Guide

## Quick Answer: Where is the Agent Code?

All agent code is in **`app/agent/`** directory:

```
app/agent/
├── __init__.py              # Public exports
├── result.py                # AgentRunResult dataclass (output structure)
├── tool_factory.py          # Per-request tool builder (5 tools with injected context)
├── adk_agent.py             # Google ADK agent builder (real mode)
├── fake.py                  # Keyword-based agent (fake mode for testing)
└── runtime.py               # Mode selector & dispatcher (entry point)
```

---

## How to Confirm the Agent is Well-Defined

### 1. **Check the Agent Output Structure** (`result.py`)
The agent returns a standardized `AgentRunResult` with:
- `reply`: Single-sentence Indonesian response
- `actions`: List of tool invocations (Tool Result Dicts)
- `device_feedback`: Last successful device command (if any)
- `status`: "success" or "error"
- `error`: Error message (if status="error")

**Verification:**
```bash
# Read the result structure
cat app/agent/result.py
```

### 2. **Check the Five Tools are Defined** (`tool_factory.py`)
The agent has exactly **5 tools** with injected context:

1. **`create_task`** – Create a task with title, course, deadline, reminder
2. **`create_expense`** – Record an expense with amount, note, timestamp
3. **`set_reminder`** – Set a reminder with text, channel, time
4. **`get_today_summary`** – Get today's task/expense counts
5. **`send_device_command`** – Send a command to the paired device

**Verification:**
```bash
# Check tool definitions
grep -n "def create_task\|def create_expense\|def set_reminder\|def get_today_summary\|def send_device_command" app/agent/tool_factory.py
```

### 3. **Check Mode Selection** (`runtime.py`)
The agent supports **two modes**:

- **Real Mode** (`agent_mode="real"` or auto-detected via `GOOGLE_API_KEY`)
  - Uses Google ADK + Gemini model
  - Imports deferred to function body (hermetic)
  
- **Fake Mode** (`agent_mode="fake"`)
  - Keyword-based agent for testing
  - Never imports Google SDK

**Verification:**
```bash
# Check mode selection logic
grep -A 20 "def select_mode" app/agent/runtime.py
```

### 4. **Check the ADK Agent Configuration** (`adk_agent.py`)
The real agent is built with:
- **Name:** `taskbot_agent`
- **Model:** Configurable (default: `gemini-3-flash-preview`)
- **Instruction:** Indonesian system prompt (enforces 1-sentence replies)
- **Tools:** The 5 tools from tool_factory

**Verification:**
```bash
# Check agent builder
cat app/agent/adk_agent.py | grep -A 30 "def build_taskbot_agent"
```

### 5. **Check the Entry Point** (`runtime.py`)
The public function is `run_text()`:

```python
async def run_text(
    db,
    *,
    user_id,
    device_id,
    text: str,
    timezone: str | None,
) -> AgentRunResult:
```

This is called by:
- `POST /agent/text` endpoint (`app/api/agent.py`)
- Manual CLI (`scripts/run_agent_text.py`)

**Verification:**
```bash
# Check the entry point
grep -A 10 "async def run_text" app/agent/runtime.py
```

---

## Run Tests to Verify Agent is Well-Defined

### Test Suite for Agent Runtime

All agent tests are in `app/tests/`:

```bash
# Run all agent tests
pytest app/tests/test_agent_runtime.py -v
pytest app/tests/test_agent_text_endpoint.py -v
pytest app/tests/test_agent_fake_hermeticity.py -v
```

### Key Properties Tested

| Property | What It Verifies | Test File |
|----------|------------------|-----------|
| **AR1** | Tool Surface has exactly 5 tools | `test_agent_runtime.py` |
| **AR2** | Tool schemas hide injected context | `test_agent_runtime.py` |
| **AR3** | Bound context forwarded correctly | `test_agent_runtime.py` |
| **AR4** | `send_device_command` short-circuits when no device | `test_agent_runtime.py` |
| **AR5** | Mode selection follows the table | `test_agent_runtime.py` |
| **AR6** | Fake agent never imports Google SDK | `test_agent_fake_hermeticity.py` |
| **AR7** | `device_feedback` picks last successful device command | `test_agent_runtime.py` |

---

## Quick Smoke Test

### 1. Run the Agent from CLI
```bash
# Set environment
export TASKBOT_USER_ID="user-123"
export TASKBOT_DEVICE_ID="device-456"
export AGENT_MODE=fake  # Use fake mode (no API key needed)

# Run a command
python -m scripts.run_agent_text "catat tugas matematika besok"
```

Expected output:
```
AgentRunResult(
    reply="Tugas matematika dicatat untuk besok.",
    actions=[...],
    device_feedback=None,
    status="success",
    error=None
)
```

### 2. Call the API
```bash
curl -X POST http://localhost:8000/agent/text \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "device_id": "device-456",
    "text": "Berapa pengeluaran hari ini?",
    "timezone": "Asia/Jakarta"
  }'
```

Expected response:
```json
{
  "reply": "Hari ini Anda belum ada pengeluaran.",
  "actions": [...],
  "device_feedback": null,
  "status": "success",
  "error": null
}
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    POST /agent/text                         │
│                   (app/api/agent.py)                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │   run_text() [runtime.py]          │
        │   - Builds 5 tools                 │
        │   - Selects mode (real/fake)       │
        └────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
    ┌─────────────┐              ┌──────────────┐
    │ Real Mode   │              │  Fake Mode   │
    │ (ADK)       │              │  (Keyword)   │
    │             │              │              │
    │ _run_real() │              │ _run_fake()  │
    │ - Gemini    │              │ - No SDK     │
    │ - Tools     │              │ - Hermetic   │
    └─────────────┘              └──────────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │   AgentRunResult                   │
        │   - reply (1 sentence)             │
        │   - actions (tool results)         │
        │   - device_feedback (last cmd)     │
        │   - status (success/error)         │
        └────────────────────────────────────┘
```

---

## Configuration

### Environment Variables

```bash
# Agent mode selection
AGENT_MODE=                    # "" (auto), "real", or "fake"

# Google ADK (real mode only)
GOOGLE_API_KEY=               # Required for real mode
GOOGLE_ADK_MODEL=gemini-3-flash-preview  # Model to use

# Device API token (for device commands)
DEVICE_API_TOKEN=             # Shared secret for device endpoints
```

### Settings (`app/config.py`)

```python
class Settings:
    agent_mode: str = ""                    # Mode selection
    google_api_key: str = ""                # Google API key
    google_adk_model: str = "gemini-3-flash-preview"  # Model
    device_api_token: str = ""              # Device token
```

---

## Summary

✅ **Agent is well-defined when:**

1. ✓ `app/agent/result.py` defines the output structure
2. ✓ `app/agent/tool_factory.py` builds exactly 5 tools with injected context
3. ✓ `app/agent/adk_agent.py` configures the Google ADK agent
4. ✓ `app/agent/fake.py` provides hermetic testing mode
5. ✓ `app/agent/runtime.py` dispatches between modes
6. ✓ All 27 property-based tests pass
7. ✓ CLI smoke test works
8. ✓ API endpoint returns correct response shape

**To verify now:**
```bash
pytest app/tests/test_agent_runtime.py -v
python -m scripts.run_agent_text "test command"
```

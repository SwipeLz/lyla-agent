# Agent Design

## Overview
- **Agent Name:** `taskbot_agent`
- **Runtime:** Google ADK
- **Model:** Configurable Gemini model (e.g., `gemini-3-flash-preview`)
- **Language:** Indonesian
- **Response Style:** Concise, strict one-sentence responses for device compatibility.

## Tools Planned
1. `create_task`: Registers an academic task with a deadline.
2. `create_expense`: Records a monetary expense with amount and category.
3. `set_reminder`: Schedules a general reminder.
4. `get_today_summary`: Retrieves tasks due and expenses made today.
5. `send_device_command`: Queues a command (e.g., change OLED face, play sound) for the ESP32.

## Phase 3 Implementation Status
- The five tools listed above are implemented as **plain Python wrappers** in `app/tools/` (`task_tools.py`, `expense_tools.py`, `reminder_tools.py`, `summary_tools.py`, `device_tools.py`). Phase 3 menyediakan permukaan stabil yang dibungkus oleh Phase 4 sebagai ADK tools.
- Each wrapper calls into the corresponding `app/services/` module and returns a normalized **Tool Result Dict** of shape `{"success": bool, "type": str, ...}` — on success it includes the created object's `id` and a human-readable `message`; on failure it includes an `error` string.

## Phase 4 Agent Runtime Status

### Tool Surface sebagai Google ADK Tools
- Phase 4 menambahkan satu agent `taskbot_agent` (Google ADK, paket `google.adk`) di `app/agent/adk_agent.py` yang men-register **Tool Surface** berisi tepat lima tool: `create_task`, `create_expense`, `set_reminder`, `get_today_summary`, `send_device_command`.
- Setiap tool adalah adapter tipis di `app/agent/tool_factory.py` yang membungkus tool wrapper Phase 3 di `app/tools/` — tidak ada logika bisnis baru di lapisan agent.
- Tool wrapper Phase 3 dipakai apa adanya; kontrak Tool Result Dict tidak berubah.

### Injected Context via Per-Request Tool Factory
- `db: Session`, `user_id`, dan `device_id` adalah **Injected Context**: nilai-nilai ini di-bind ke setiap tool callable lewat closure di `build_tools(db, user_id, device_id)` per request.
- Argumen tersebut **tidak muncul** di skema fungsi yang dilihat model LLM. Model hanya melihat parameter bisnis (mis. `title`, `amount`, `remind_at`).
- Bila model mencoba mengirim `db`/`user_id`/`device_id` lewat `**kwargs`, runtime mengabaikannya dan tetap memakai nilai Injected Context.
- Saat `device_id is None`, tool `send_device_command` short-circuit ke failure Tool Result Dict tanpa menyentuh service layer.

### Fake Agent untuk Test dan CI
- `app/agent/fake.py` menyediakan **Fake Agent**: implementasi alternatif berbasis keyword-detection sederhana (Bahasa Indonesia, mis. `catat`/`tugas` → `create_task`, `ingatkan`/`reminder` → `set_reminder`) yang memanggil tool wrapper yang sama lewat Per-Request Tool Factory.
- Fake Agent **tidak** mengimpor `google.adk.*` dan tidak melakukan outbound network call, sehingga `pytest` jalan tanpa `GOOGLE_API_KEY` dan tanpa akses Gemini.
- Pemilihan mode dikontrol via `settings.agent_mode`: `"real"` (Google ADK) atau `"fake"` (Fake Agent). Default otomatis: `"real"` saat `GOOGLE_API_KEY` di-set, `"fake"` saat kosong.
- Test suite memakai mode `"fake"` by default; integration test untuk `POST /agent/text` mengeksekusi alur agent end-to-end terhadap SQLite in-memory tanpa menyentuh jaringan.

## Behavior & Validation Rules
- **Do not invent data:** The agent must never fabricate dates, amounts, or facts.
- **Clarification:** If required information (like the amount of an expense or the deadline for a task) is missing, the agent must ask for clarification instead of guessing.
- **Positive Amounts:** Automatically validate that expense amounts are positive.
- **Valid Deadlines:** Ensure deadlines and reminder times are parsed to valid future datetime objects.

## Example Interactions

### Valid Command
**User:** "Besok ada tugas Jaringan jam 10 pagi."
**Agent Action:** Calls `create_task` tool.
**Agent Response:** "Tugas Jaringan untuk besok jam 10 pagi telah dicatat."

### Missing Information
**User:** "Tadi aku beli makan."
**Agent Action:** Identifies missing amount.
**Agent Response:** "Berapa harga makanan yang kamu beli tadi?"

### Invalid Information
**User:** "Aku pengeluaran minus 50 ribu."
**Agent Action:** Fails validation for positive amount.
**Agent Response:** "Maaf, jumlah pengeluaran tidak bisa negatif, mohon periksa kembali."

## Example Structured Response Format
When communicating with the device, the backend might wrap the agent's text response with additional metadata:
```json
{
  "status": "success",
  "text_response": "Tugas Jaringan untuk besok jam 10 pagi telah dicatat.",
  "intent_detected": "create_task",
  "device_action_queued": true
}
```

# Design Document — Agent Runtime and APIs (Phase 4–8)

## Overview

Spec ini menambahkan lima lapisan baru di atas Phase 3 yang sudah ada:

1. **Agent Runtime** (`app/agent/`) yang menggabungkan satu Google ADK agent (`taskbot_agent`) dengan Per-Request Tool Factory yang membungkus tool wrappers Phase 3. Sebuah Fake Agent dipakai untuk test/CI tanpa `GOOGLE_API_KEY`.
2. **`POST /agent/text`** (`app/api/agent.py`) yang memvalidasi request, memanggil Agent Runtime, mencatat `VoiceCommandLog`, lalu mengembalikan `reply` + `actions` + `device_feedback`.
3. **Reminder Scheduler** (`app/scheduler/`) berbasis APScheduler `BackgroundScheduler` yang dimulai pada FastAPI startup (gated oleh `scheduler_enabled`) untuk memproses Due Reminder.
4. **Device Command Queue API** (`app/api/devices.py`) untuk ESP32, dilindungi `X-Device-Token`. Termasuk **Atomic Mark-Sent** pada poll pending.
5. **Minimal Dashboard API** (`app/api/dashboard.py`) untuk task/expense/summary/log/device, gated oleh `dashboard_auth_mode`.

Service Layer Phase 3 dan tool wrappers tidak diubah. Yang berubah hanya:
- `requirements.txt` (tambah `google-adk` + `apscheduler`).
- `app/config.py` (tambah setting baru).
- `app/main.py` (register router baru + lifecycle scheduler).
- File-file baru di `app/agent/`, `app/scheduler/`, `app/api/`, `app/integrations/`, `scripts/`, `app/tests/`.

### Verifikasi Google ADK Python (sumber: adk.dev, docs.cloud.google.com)

| Aspek | Pilihan resmi |
|---|---|
| Install package | `pip install google-adk` |
| Agent class | `from google.adk.agents import Agent` (alias `LlmAgent`) |
| Function tool | Python callable biasa di-pass ke `tools=[...]` (tidak perlu wrapper class) |
| Runner | `from google.adk.runners import Runner` → `runner.run_async(user_id, session_id, new_message)` async generator |
| Session service | `from google.adk.sessions import InMemorySessionService` (`create_session`/`get_session` async) |
| FastAPI integration | Pola resmi: `runner = Runner(app_name, agent, session_service)` di startup; endpoint async yang `async for event in runner.run_async(...)` lalu deteksi `event.is_final_response()` |
| `output_schema` + tools | `output_schema` mematikan tool use kecuali untuk model spesifik (Gemini 3.0). Pada `gemini-3-flash-preview` (dan model 2.x sebelumnya) hasilnya tidak reliable jika digabung dengan tool calling. → **`taskbot_agent` TIDAK pakai `output_schema`**; bentuk output disusun di server dari event tool-call |

### Prinsip Lapisan

| Layer | Tahu tentang | Tidak boleh tahu tentang |
|---|---|---|
| Models | DB schema | Bisnis, HTTP, agent |
| Services | Bisnis, ORM, validasi | HTTP, agent, format LLM-friendly |
| Tool Wrappers (Phase 3) | Tool Result Dict shape | ADK SDK, HTTP |
| ADK Tools (Phase 4) | ADK function tool API + Injected Context | ORM langsung |
| Agent Runtime | ADK SDK + tool factory + fake mode | HTTP body shape |
| API endpoints | HTTP (FastAPI) + Pydantic schemas | ORM langsung untuk write |
| Scheduler | APScheduler + Service Layer | HTTP, ADK |

Tool wrappers Phase 3 **tidak** dimodifikasi. Phase 4 menambahkan layer adapter tipis (`app/agent/tools.py`) yang membuat ADK-friendly callable.

## Architecture

### Diagram Komponen

```mermaid
flowchart TB
  subgraph Client
    ESP[ESP32 Device]
    DashUI[Dashboard UI / curl]
  end

  subgraph FastAPI[app/main.py]
    R0["/health (existing)"]
    R1["POST /agent/text"]
    R2["GET/POST /devices/* (X-Device-Token)"]
    R3["GET/PATCH/DELETE /dashboard/*"]
    LC["Lifespan: startup/shutdown"]
  end

  subgraph AgentRuntime[app/agent/]
    AR["runtime.run_text(...)"]
    SEL["select_runner(agent_mode)"]
    REAL["RealAgentRunner (google-adk)"]
    FAKE["FakeAgentRunner"]
    TF["tool_factory.build_tools(db, user_id, device_id)"]
    AGENT["build_taskbot_agent(model, tools)"]
  end

  subgraph Scheduler[app/scheduler/]
    BG["BackgroundScheduler"]
    TICK["reminder_tick()"]
    WA["WhatsApp Stub"]
  end

  subgraph Services[app/services/ (Phase 3)]
    TS[task_service]
    ES[expense_service]
    RS[reminder_service]
    DS[device_service]
    LS[log_service]
  end

  subgraph Tools[app/tools/ (Phase 3)]
    TT[task_tools]
    ET[expense_tools]
    RT[reminder_tools]
    DT[device_tools]
    ST[summary_tools]
  end

  ESP --> R2
  DashUI --> R3
  Client --> R1

  R1 --> AR
  AR --> SEL
  SEL --> REAL
  SEL --> FAKE
  REAL --> TF
  FAKE --> TF
  TF --> AGENT
  TF --> TT & ET & RT & DT & ST
  TT & ET & RT & DT & ST --> TS & ES & RS & DS

  R1 -.log.-> LS

  LC --> BG
  BG --> TICK
  TICK --> RS
  TICK --> DS
  TICK --> WA

  R2 --> DS
  R3 --> TS & ES & RS & DS & LS
```

### Direktori dan File Baru

```
app/
├── agent/
│   ├── __init__.py
│   ├── runtime.py             # public: run_text(db, user_id, device_id, text, timezone) -> AgentRunResult
│   ├── tool_factory.py        # build_tools(db, user_id, device_id) -> list of ADK-friendly callables
│   ├── adk_agent.py           # build_taskbot_agent(model: str, tools: list) -> google.adk.Agent
│   ├── fake.py                # FakeAgentRunner: keyword-based intent + same tool factory
│   └── result.py              # AgentRunResult dataclass
├── api/
│   ├── agent.py               # POST /agent/text
│   ├── devices.py             # 3 endpoint device-facing
│   └── dashboard.py           # /dashboard/*
├── scheduler/
│   ├── __init__.py
│   ├── lifecycle.py           # start_scheduler(app) / stop_scheduler(app)
│   └── tick.py                # reminder_tick(db_factory, whatsapp_send) — pure function, testable
├── integrations/
│   ├── __init__.py
│   └── whatsapp.py            # whatsapp_send_stub(reminder) → {"sent": True, "stub": True}
├── schemas/
│   ├── __init__.py
│   ├── agent.py               # AgentTextRequest / AgentTextResponse
│   ├── devices.py             # DeviceCommandResponse, DeviceStatusUpdate, AckResponse
│   └── dashboard.py           # TaskOut, TaskPatch, ExpenseIn, ExpenseOut, SummaryOut, LogOut, DeviceOut
└── tests/
    ├── test_agent_runtime.py
    ├── test_agent_text_endpoint.py
    ├── test_scheduler_tick.py
    ├── test_devices_api.py
    └── test_dashboard_api.py

scripts/
└── run_agent_text.py          # python -m scripts.run_agent_text "<text>"
```

`app/agent/__init__.py` tidak melakukan import berat (tidak `from google.adk import ...`) supaya `agent_mode == "fake"` benar-benar tidak meng-import ADK SDK. Import ADK ditunda ke `adk_agent.py` dan `runtime.py` di branch `agent_mode == "real"`.

### Lifespan FastAPI

`app/main.py` akan diubah memakai FastAPI lifespan context:

```python
# pseudocode
@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.scheduler_enabled:
        scheduler = start_scheduler(app)  # APScheduler BackgroundScheduler
        app.state.scheduler = scheduler
    yield
    sched = getattr(app.state, "scheduler", None)
    if sched is not None:
        sched.shutdown(wait=False)

app = FastAPI(lifespan=lifespan, ...)
app.include_router(health.router)
app.include_router(agent.router)
app.include_router(devices.router)
app.include_router(dashboard.router)
```

Test pakai `TestClient(app)` dengan `settings.scheduler_enabled = False` (default) — scheduler tidak start.

## Components and Interfaces

### `app/agent/result.py`

```python
@dataclass
class AgentRunResult:
    reply: str
    actions: list[dict]              # list of Tool Result Dicts
    device_feedback: dict | None     # last successful send_device_command Tool Result Dict
    status: str                      # "success" | "error"
    error: str | None = None
```

`device_feedback` dipilih dari `actions[::-1]` — entry pertama (paling akhir secara waktu) yang punya `success=True` dan `type=="device_command"`.

### `app/agent/tool_factory.py`

Menghasilkan list callable ADK-friendly yang sudah di-bind ke `(db, user_id, device_id)`. Tanda tangan model-visible per tool sesuai Req 2.1.

```python
def build_tools(db, user_id: str, device_id: str | None):
    def create_task(title, course=None, deadline_at=None,
                    reminder_at=None, priority=None) -> dict:
        return task_tools.create_task_tool(
            db=db, user_id=user_id,
            title=title, course=course,
            deadline_at=deadline_at,
            reminder_at=reminder_at, priority=priority,
        )
    create_task.__name__ = "create_task"
    create_task.__doc__ = (
        "Catat tugas akademik baru untuk pengguna. "
        "Argumen: title (str), course (str|None), deadline_at (ISO 8601|None), "
        "reminder_at (ISO 8601|None), priority (str|None)."
    )

    def create_expense(amount, category=None, note=None, spent_at=None) -> dict:
        return expense_tools.create_expense_tool(
            db=db, user_id=user_id,
            amount=amount, category=category,
            note=note, spent_at=spent_at,
        )
    # ... set_reminder, get_today_summary, send_device_command similarly
    return [create_task, create_expense, set_reminder, get_today_summary, send_device_command]
```

Catatan kunci:
- ADK function tool memakai signature & docstring callable untuk membuat skema yang dilihat model. Karena `db`, `user_id`, `device_id` **bukan parameter** dari closure tersebut, model tidak melihatnya (Req 2.2 terpenuhi by construction).
- Saat `device_id is None`, `send_device_command` closure langsung mengembalikan failure dict `{"success": False, "type": "device_command", "error": "Tidak ada device yang terhubung."}` tanpa memanggil service (Req 2.6).
- Datetime parameters yang model-visible (`deadline_at`, `reminder_at`, `spent_at`, `remind_at`) didokumentasikan menerima string ISO 8601. Sebelum diteruskan ke tool wrapper Phase 3 (yang butuh `datetime` aware), closure melakukan parsing dengan `datetime.fromisoformat`. Bila parsing gagal, kembalikan failure Tool Result Dict — tidak melempar.

### `app/agent/adk_agent.py`

```python
from google.adk.agents import Agent

INSTRUCTION = """\
Kamu adalah Taskbot, asisten mahasiswa berbahasa Indonesia.
Aturan:
- Jawab maksimal SATU kalimat singkat (<= 20 kata) untuk perangkat layar kecil.
- Jangan mengarang data: jika informasi penting (jumlah, tanggal) hilang, minta klarifikasi.
- Untuk mencatat tugas/pengeluaran/reminder, panggil tool yang sesuai dan rangkum hasil dalam satu kalimat.
- Jangan menyebut nama tool atau format JSON ke pengguna.
"""

def build_taskbot_agent(*, model: str, tools: list):
    return Agent(
        name="taskbot_agent",
        model=model,
        description="Asisten Taskbot berbahasa Indonesia.",
        instruction=INSTRUCTION,
        tools=tools,
    )
```

Tidak ada `output_schema`. Bentuk output (`AgentRunResult`) dibangun di `runtime.py` dari event stream.

### `app/agent/runtime.py`

```python
def select_mode(settings) -> str:
    """Map settings → 'real' or 'fake'."""
    if settings.agent_mode in ("real", "fake"):
        return settings.agent_mode
    if settings.google_api_key:
        return "real"
    return "fake"

async def run_text(db, *, user_id, device_id, text, timezone) -> AgentRunResult:
    mode = select_mode(settings)
    tools = build_tools(db, user_id, device_id)
    if mode == "real":
        return await _run_real(tools=tools, text=text, timezone=timezone)
    return await _run_fake(tools=tools, text=text, timezone=timezone)
```

`_run_real`:

```python
async def _run_real(*, tools, text, timezone) -> AgentRunResult:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from app.agent.adk_agent import build_taskbot_agent

    agent = build_taskbot_agent(model=settings.google_adk_model, tools=tools)
    session_service = InMemorySessionService()
    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name="taskbot",
        user_id="taskbot_user",  # placeholder; per-call isolation via fresh session_id
        session_id=session_id,
    )
    runner = Runner(app_name="taskbot", agent=agent, session_service=session_service)

    actions: list[dict] = []
    final_text = ""
    async for event in runner.run_async(
        user_id="taskbot_user",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=text)]),
    ):
        # Capture function_response payloads as Tool Result Dicts.
        for part in (event.content.parts if event.content else []) or []:
            if getattr(part, "function_response", None) is not None:
                actions.append(part.function_response.response)
        if event.is_final_response():
            if event.content and event.content.parts:
                final_text = "".join(p.text for p in event.content.parts if p.text)

    return AgentRunResult(
        reply=final_text or "Maaf, aku belum bisa memproses itu.",
        actions=actions,
        device_feedback=_pick_device_feedback(actions),
        status="success",
    )
```

`InMemorySessionService` per-request memastikan tidak ada bocoran state antar pengguna di MVP. Saat tahap berikutnya butuh sesi gabungan, tinggal pindahkan `session_service` ke singleton `app.state`.

`_run_fake`:

Fake Agent meng-deteksi intent berdasarkan keyword sederhana (regex/`in`-substring). Untuk MVP cukup mendukung empat keyword case-insensitive: `"catat"`/`"tugas"` → `create_task`, `"makan"`/`"beli"`/`"bayar"`+angka → `create_expense`, `"ingatkan"`/`"reminder"` → `set_reminder`, `"ringkasan"`/`"hari ini"` → `get_today_summary`. Bila tidak ada keyword cocok, kembalikan `AgentRunResult(reply="Maaf, aku belum mengerti perintah itu.", actions=[], device_feedback=None, status="success")`.

Tujuan utama Fake Agent adalah test hermetic: untuk skenario yang dipakai di test, kita inject keyword yang deterministic sehingga tool wrappers dipanggil dengan argumen yang dapat diukur. Test boleh memonkeypatch `app.agent.runtime._run_fake` untuk mengembalikan hasil yang sangat spesifik. Test default tetap berjalan tanpa monkeypatch.

### `scripts/run_agent_text.py`

```python
# python -m scripts.run_agent_text "<text>" [--user-id U] [--device-id D]
import argparse, asyncio, json, sys, os
from app.db import SessionLocal
from app.agent.runtime import run_text
from app.config import settings

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("text")
    parser.add_argument("--user-id", default=os.environ.get("TASKBOT_USER_ID"))
    parser.add_argument("--device-id", default=os.environ.get("TASKBOT_DEVICE_ID"))
    args = parser.parse_args()
    if not args.text.strip():
        print("usage: python -m scripts.run_agent_text \"<text>\"", file=sys.stderr)
        sys.exit(2)
    db = SessionLocal()
    try:
        result = await run_text(db, user_id=args.user_id, device_id=args.device_id,
                                text=args.text, timezone=settings.timezone)
    finally:
        db.close()
    print(json.dumps({"reply": result.reply, "actions": result.actions,
                      "device_feedback": result.device_feedback, "status": result.status},
                     ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
```

### `app/api/agent.py` — `POST /agent/text`

Pydantic request:

```python
class AgentTextRequest(BaseModel):
    user_id: str
    device_id: str | None = None
    text: str = Field(min_length=1)
    timezone: str | None = None

    @field_validator("text")
    @classmethod
    def _no_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text tidak boleh kosong")
        return v
```

Handler:

```python
@router.post("/agent/text")
async def post_agent_text(payload: AgentTextRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.id == payload.user_id).first() is None:
        raise HTTPException(404, "User tidak ditemukan")
    if payload.device_id is not None and db.query(Device).filter(Device.id == payload.device_id).first() is None:
        raise HTTPException(404, "Device tidak ditemukan")

    tz = payload.timezone or settings.timezone
    try:
        result = await run_text(db, user_id=payload.user_id,
                                device_id=payload.device_id,
                                text=payload.text, timezone=tz)
    except Exception as exc:  # broad on purpose: see Req 6.6
        log_service.create_voice_command_log(
            db, user_id=payload.user_id, device_id=payload.device_id,
            input_text=payload.text, parsed_actions=[],
            response_text=str(exc), status="error",
        )
        raise HTTPException(500, "Agent runtime error")

    log_service.create_voice_command_log(
        db, user_id=payload.user_id, device_id=payload.device_id,
        input_text=payload.text, parsed_actions=result.actions,
        response_text=result.reply, status=result.status,
    )
    return {"reply": result.reply, "actions": result.actions,
            "device_feedback": result.device_feedback}
```

`HTTPException(500)` tidak men-leak stack trace (Req 6.6) karena FastAPI hanya mengirim `detail`.

### `app/api/devices.py` — Device Command Queue API

Dependency token:

```python
def require_device_token(x_device_token: str | None = Header(default=None)):
    if not settings.device_api_token or x_device_token != settings.device_api_token:
        raise HTTPException(401, "Unauthorized")
```

Atomic Mark-Sent:

```python
@router.get("/devices/{device_code}/commands/pending")
def list_pending(device_code: str, db: Session = Depends(get_db),
                 _=Depends(require_device_token)):
    device = device_service.get_device_by_code(db, device_code)  # raises NotFoundError → 404 mapper
    # Single transaction: SELECT ... FOR UPDATE (or UPDATE ... RETURNING for SQLite via 2-step)
    pending = (db.query(DeviceCommand)
                 .filter(DeviceCommand.device_id == device.id,
                         DeviceCommand.status == DeviceCommandStatus.PENDING)
                 .with_for_update()  # no-op on SQLite, but sets intent for Postgres
                 .all())
    if not pending:
        return []
    now = now_utc()
    out = []
    for cmd in pending:
        out.append({
            "command_id": cmd.id,
            "command_type": cmd.command_type,
            "payload": cmd.payload,
            "created_at": cmd.created_at.isoformat(),
        })
        cmd.status = DeviceCommandStatus.SENT
        cmd.sent_at = now
    db.commit()
    return out
```

SQLite tidak benar-benar mendukung row locking. Atomicity diperoleh karena SQLAlchemy session bekerja dalam satu transaksi: read+write+commit dalam satu blok. Dua poll berurutan tidak akan tumpang tindih jika tidak ada request concurrent — yang sesuai dengan model deployment MVP single-process.

Untuk meminimalkan window race kecuali pada scale-up Postgres nanti, query menggunakan `with_for_update()` (no-op untuk SQLite, advisory untuk Postgres). Test akan memverifikasi invarian "dua poll berurutan tidak overlap" via `TestClient`.

Ack & status:

```python
@router.post("/devices/{device_code}/commands/{command_id}/ack", status_code=200)
def ack(device_code, command_id, db=Depends(get_db), _=Depends(require_device_token)):
    device = device_service.get_device_by_code(db, device_code)
    cmd = db.query(DeviceCommand).filter(DeviceCommand.id == command_id,
                                         DeviceCommand.device_id == device.id).first()
    if cmd is None:
        raise HTTPException(404, "Command tidak ditemukan")
    device_service.ack_device_command(db, command_id)
    return {"success": True, "command_id": command_id}

@router.post("/devices/{device_code}/status")
def status_update(device_code, payload: DeviceStatusUpdate,
                  db=Depends(get_db), _=Depends(require_device_token)):
    if payload.status not in (DeviceStatus.ONLINE, DeviceStatus.OFFLINE):
        raise HTTPException(422, "Status tidak valid")
    device = device_service.update_device_status(db, device_code, payload.status)
    return {"status": device.status, "last_seen_at": device.last_seen_at.isoformat()}
```

`require_device_token` dijalankan **sebelum** lookup database — saat 401, tidak ada query yang dieksekusi, memenuhi Req 9.2 ("SHALL NOT mutate any database row").

Token tidak pernah dilog karena tidak ada `logger.info` yang merefer header, dan FastAPI default tidak melog header (Req 9.4).

### `app/api/dashboard.py` — Minimal Dashboard API

Auth dependency:

```python
def require_dashboard_auth(x_dashboard_token: str | None = Header(default=None)):
    mode = settings.dashboard_auth_mode
    if mode == "none":
        return
    if mode == "shared_header":
        expected = settings.dashboard_token  # added in config
        if not expected or x_dashboard_token != expected:
            raise HTTPException(401, "Unauthorized")
        return
    raise HTTPException(500, "Invalid dashboard_auth_mode configuration")
```

Open Decision (Req 14): MVP defaults `dashboard_auth_mode = "none"` karena dashboard berjalan di lokal/VPS internal di Phase 8 dan belum ada UI publik. Rationale: memilih `"none"` mengurangi friksi pengembangan; tetap menyediakan jalur `"shared_header"` agar transisi ke deployment publik tinggal flip config tanpa refactor. Keputusan ini wajib didokumentasikan di `docs/ARCHITECTURE.md` (Req 18.4).

Endpoint shape:

| Route | Service call | Resp |
|---|---|---|
| `GET /dashboard/tasks?user_id&status` | `task_service.list_tasks` | 200 `[TaskOut]` |
| `PATCH /dashboard/tasks/{task_id}` | new helper `task_service.update_task` *(read on)* | 200 `TaskOut` |
| `DELETE /dashboard/tasks/{task_id}` | new helper `task_service.delete_task` *(read on)* | 204 |
| `GET /dashboard/expenses?user_id&start_at&end_at` | `expense_service.list_expenses` | 200 `[ExpenseOut]` |
| `POST /dashboard/expenses` | `expense_service.create_expense` | 201 `ExpenseOut` |
| `GET /dashboard/summary?user_id` | reuse `get_today_summary_tool` | 200 `SummaryOut` |
| `GET /dashboard/logs?user_id` | new query: `VoiceCommandLog` filter+order | 200 `[LogOut]` |
| `GET /dashboard/devices?user_id` | new query: `Device` filter | 200 `[DeviceOut]` |

Catatan tentang **service-layer additions** (Req 8.1 spec ini):
- `task_service.update_task(db, task_id, **patch)` dan `task_service.delete_task(db, task_id)` adalah penambahan kecil yang **menambah** Phase 3 service tanpa memodifikasi yang sudah ada. Validasi datetime/title sama dengan `create_task`. Patch hanya field yang disuplai (tidak nullify). `delete_task` mengembalikan `None` dan melempar `NotFoundError` jika task tidak ada.

Service-layer addition ini membutuhkan pembaruan `requirements.md` Phase 3 — **TIDAK**. Phase 3 lengkap; helper baru ini adalah ekstensi yang dimiliki Phase 8 dan diimplementasikan di file Phase 3 untuk konsistensi tempat. Tidak ada perubahan kontrak Phase 3 yang ada.

Pemetaan exception → HTTP:
- `ValidationError` → 422
- `NotFoundError` → 404
- `PermissionDeniedError` → 403

Sebuah utilitas kecil `app/api/_errors.py` mendaftar exception handler global agar tiap router dashboard tidak menulis try/except per endpoint.

### `app/scheduler/tick.py`

```python
def reminder_tick(*, db_factory, whatsapp_send=None) -> dict:
    """Pure function — returns counts; safe to invoke directly from tests."""
    if whatsapp_send is None:
        from app.integrations.whatsapp import whatsapp_send_stub as whatsapp_send

    sent, failed, skipped = 0, 0, 0
    db = db_factory()
    try:
        due = reminder_service.list_due_reminders(db)
        for reminder in due:
            try:
                if reminder.channel in ("device", "both"):
                    user_devices = db.query(Device).filter(Device.user_id == reminder.user_id).all()
                    if user_devices:
                        device_service.queue_device_command(
                            db, user_devices[0].id,
                            command_type="show_text",
                            payload={"text": reminder.title},
                        )
                    elif reminder.channel == "device":
                        # only-channel device but no device: count as skipped
                        skipped += 1
                        continue
                if reminder.channel in ("whatsapp", "both"):
                    whatsapp_send(reminder)
                reminder_service.mark_reminder_sent(db, reminder.id)
                sent += 1
            except Exception:
                reminder_service.mark_reminder_failed(db, reminder.id)
                failed += 1
        db.commit()
    finally:
        db.close()
    return {"sent": sent, "failed": failed, "skipped": skipped}
```

### `app/scheduler/lifecycle.py`

```python
def start_scheduler(app: FastAPI):
    scheduler = BackgroundScheduler(timezone=ZoneInfo("UTC"))
    scheduler.add_job(
        func=lambda: reminder_tick(db_factory=SessionLocal),
        trigger="interval",
        seconds=settings.scheduler_interval_seconds,
        id="reminder_tick",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
```

`reminder_tick` adalah pure function yang dapat diuji tanpa membuat scheduler (Req 16.5).

### Konfigurasi Baru di `app/config.py`

```python
class Settings(BaseSettings):
    # ... existing fields preserved
    agent_mode: str = ""                       # "" → auto by google_api_key; or "real" / "fake"
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 60
    dashboard_auth_mode: str = "none"          # "none" | "shared_header"
    dashboard_token: str = ""                  # used only when dashboard_auth_mode == "shared_header"
```

`.env.example` ditambah lima baris dengan komentar tetapi tanpa nilai rahasia.

## Data Models

Tidak ada perubahan schema database. Semua tabel Phase 2 dipakai apa adanya. Tidak ada migrasi Alembic baru di Phase 4–8 (sesuai Req 15.8).

Pydantic schemas baru (read/write only di sisi HTTP):

```python
# app/schemas/agent.py
class AgentTextRequest(BaseModel): ...
class AgentTextResponse(BaseModel):
    reply: str
    actions: list[dict]
    device_feedback: dict | None

# app/schemas/devices.py
class PendingCommandOut(BaseModel):
    command_id: str
    command_type: str
    payload: dict
    created_at: str
class AckResponse(BaseModel):
    success: bool
    command_id: str
class DeviceStatusUpdate(BaseModel):
    status: str

# app/schemas/dashboard.py
class TaskOut(BaseModel): ...
class TaskPatch(BaseModel):
    status: str | None = None
    title: str | None = None
    course: str | None = None
    deadline_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: str | None = None
class ExpenseIn(BaseModel): ...
class ExpenseOut(BaseModel): ...
class SummaryOut(BaseModel):
    tasks_due_today: int
    total_expenses_today: int
class LogOut(BaseModel): ...
class DeviceOut(BaseModel): ...
```

`TaskPatch` semua field optional. Endpoint hanya menerapkan field yang non-`None`.

## Correctness Properties

Properti di bawah adalah hasil refleksi setelah analisis 18 requirement: validasi tipe-error yang berbagi semantik digabung dalam satu property dengan generator `one_of`; transisi yang simetris (`mark_sent`/`mark_failed`) jadi satu property; happy-path dan error-path digabung jika semantiknya tidak menambah informasi.

### Agent Runtime

**Property AR1: Tool Surface Identitas**
*For any* invocation of `build_taskbot_agent` produced by the Agent Runtime under `agent_mode == "real"`, the resulting agent SHALL have exactly five tools whose `__name__` attributes equal the set `{"create_task", "create_expense", "set_reminder", "get_today_summary", "send_device_command"}`.
**Validates: Requirements 1.1, 1.3, 1.5**

**Property AR2: Tool Schema Hides Injected Context**
*For any* tool produced by `build_tools(db, user_id, device_id)`, the function's `inspect.signature(tool).parameters` SHALL NOT contain `"db"`, `"user_id"`, or `"device_id"` as a parameter name.
**Validates: Requirements 2.1, 2.2**

**Property AR3: Bound Context Forwarded**
*For any* tool from `build_tools(db, user_id, device_id)` invoked with valid model-visible arguments, the underlying Phase 3 tool wrapper SHALL be called with positional/keyword arguments equal to `(db=db, user_id=user_id, ...)` (and `device_id=device_id` for `send_device_command_tool`); the model-supplied `db`/`user_id`/`device_id` SHALL be ignored if injected via `**kwargs`.
**Validates: Requirements 2.3, 2.4, 2.5**

**Property AR4: send_device_command without device_id short-circuits**
*For any* tool list built with `device_id is None`, calling the `send_device_command` tool with any combination of `face`/`sound`/`text` SHALL return a Tool Result Dict with `success=False`, `type="device_command"`, non-empty `error`, and SHALL NOT call `device_service.queue_device_command`.
**Validates: Requirement 2.6**

**Property AR5: Mode Selection**
*For any* settings combination, `select_mode(settings)` SHALL return:
- `"real"` if `settings.agent_mode == "real"`;
- `"fake"` if `settings.agent_mode == "fake"`;
- `"real"` if `settings.agent_mode == ""` and `settings.google_api_key != ""`;
- `"fake"` otherwise.
**Validates: Requirements 3.3, 3.4**

**Property AR6: Fake Agent Hermeticity**
*For any* execution path of `_run_fake`, no module reachable from the call stack SHALL import `google.adk.runners`, `google.adk.agents`, or `google.adk.sessions`.
**Validates: Requirements 3.2, 3.5, 16.2, 16.3**

**Property AR7: AgentRunResult device_feedback selection**
*For any* `actions` list produced by an agent run, `result.device_feedback` SHALL equal the most recent (last by index) entry of `actions` for which `entry.get("type") == "device_command"` and `entry.get("success") is True`, or `None` if no such entry exists.
**Validates: Requirement 6.5**

### `POST /agent/text` Endpoint

**Property AT1: Request validation table**
*For any* payload, the response SHALL conform to:
| Condition | HTTP | Side effect |
|---|---|---|
| empty/whitespace text | 422 | no agent call, no log |
| unknown user_id | 404 | no agent call, no log |
| unknown device_id (non-null) | 404 | no agent call, no log |
| valid input | 200 | agent called once, exactly one VoiceCommandLog row |
**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3**

**Property AT2: Log mirrors response**
*For any* successful 200 response, the persisted `VoiceCommandLog` row SHALL have `input_text == request.text`, `parsed_actions == response.actions`, `response_text == response.reply`, `status == "success"`.
**Validates: Requirement 6.2, 6.4**

**Property AT3: Error path persists log without leaking trace**
*For any* invocation in which `run_text` raises, the response SHALL be HTTP 500, the response body SHALL NOT contain a stack trace, and a `VoiceCommandLog` row SHALL exist with `status == "error"` and `response_text == str(exc)`.
**Validates: Requirement 6.6**

**Property AT4: device_feedback equals last successful device command action**
*For any* successful 200 response, `response.device_feedback` SHALL equal the last entry of `response.actions` with `type == "device_command"` and `success is True`, or `null` if none.
**Validates: Requirement 6.5**

### Reminder Scheduler

**Property RS1: Lifecycle gating**
*For any* `settings.scheduler_enabled` value, on FastAPI startup, the `BackgroundScheduler` SHALL be running iff `scheduler_enabled is True`. After shutdown, SHALL NOT be running.
**Validates: Requirements 7.5, 7.6, 7.7**

**Property RS2: Tick processes all due reminders**
*For any* DB state with `n` Due Reminders, one call to `reminder_tick` SHALL invoke `reminder_service.list_due_reminders` exactly once and SHALL attempt dispatch for each Due Reminder before returning.
**Validates: Requirements 8.1, 8.5**

**Property RS3: Channel routing**
*For any* Due Reminder with `channel in {"device","both"}` and a user that has at least one Device, the tick SHALL invoke `device_service.queue_device_command` exactly once for that reminder. *For any* with `channel in {"whatsapp","both"}`, the tick SHALL invoke `whatsapp_send` exactly once for that reminder.
**Validates: Requirements 8.2, 8.3**

**Property RS4: Status transition**
*For any* Due Reminder where all dispatch calls succeed, after the tick its status SHALL equal `ReminderStatus.SENT`. *For any* where any dispatch raises, its status SHALL equal `ReminderStatus.FAILED`. Either way, processing of remaining Due Reminders SHALL continue.
**Validates: Requirements 8.4, 8.5**

**Property RS5: No real WhatsApp call**
*For any* tick execution, no module reachable from the call stack SHALL invoke `httpx`, `requests`, `urllib`, or any HTTP client targeting `graph.facebook.com` or `*.whatsapp.com`.
**Validates: Requirements 8.6, 15.2**

**Property RS6: Skip device-only when user has no device**
*For any* Due Reminder with `channel == "device"` whose user has no Device, the tick SHALL NOT call `device_service.queue_device_command` for that reminder, SHALL NOT call WhatsApp, and SHALL leave reminder status equal to `ReminderStatus.SCHEDULED` (no transition).
**Validates: Requirement 8.7**

### Device Command Queue API

**Property DA1: Token check precedes lookup**
*For any* request to a device-facing route with a missing or wrong `X-Device-Token` header, the response SHALL be HTTP 401, no `Device` lookup SHALL be performed, and no row SHALL be mutated.
**Validates: Requirements 9.2, 9.4**

**Property DA2: Unknown device_code → 404**
*For any* request with a valid token and `device_code` not matching any `Device`, the response SHALL be HTTP 404.
**Validates: Requirement 9.3**

**Property DA3: Atomic Mark-Sent invariant**
*For any* sequence `[poll_1, poll_2]` with no `Pending Command` queued in between, `poll_1.body` SHALL be a JSON list and `poll_2.body` SHALL equal `[]`. Every command id present in `poll_1.body` SHALL have status `DeviceCommandStatus.SENT` immediately after `poll_1` returns.
**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

**Property DA4: Ack happy-path and not-found**
*For any* existing `command_id` belonging to `device_code`, `POST /devices/{device_code}/commands/{command_id}/ack` SHALL return 200 with `{"success": true, "command_id": <id>}` and the underlying row SHALL transition to `ACKNOWLEDGED`. *For any* `command_id` that does not exist or belongs to a different device, the response SHALL be 404 and no row SHALL be mutated.
**Validates: Requirements 11.1, 11.2**

**Property DA5: Status update validation**
*For any* status update request, the response SHALL be 200 if `payload.status in {"online","offline"}` and the device row SHALL reflect both `status` and `last_seen_at`. Any other status value SHALL produce HTTP 422 and SHALL NOT mutate the device row.
**Validates: Requirements 11.3, 11.4**

### Dashboard API

**Property DB1: User existence gate**
*For any* Dashboard endpoint requiring `user_id`, an unknown `user_id` SHALL produce HTTP 404 and SHALL NOT call any service mutation.
**Validates: Requirement 13.6**

**Property DB2: List endpoints reflect service results**
*For any* `GET /dashboard/tasks?user_id` (optional `status`), the response SHALL equal a serialization of `task_service.list_tasks(db, user_id, status)`. Same for `GET /dashboard/expenses` ↔ `expense_service.list_expenses` and `GET /dashboard/summary` ↔ `get_today_summary_tool`.
**Validates: Requirements 12.1, 12.2, 13.1, 13.3**

**Property DB3: Patch applies only supplied fields**
*For any* existing `task_id` and any subset `S` of patchable fields, `PATCH /dashboard/tasks/{task_id}` with body `S` SHALL produce a task whose updated fields equal `S` and whose other fields equal the pre-patch values.
**Validates: Requirement 12.4**

**Property DB4: Delete behavior**
*For any* existing `task_id`, `DELETE /dashboard/tasks/{task_id}` SHALL respond 204 and the row SHALL no longer exist. *For any* missing `task_id`, the response SHALL be 404 and no row SHALL be mutated.
**Validates: Requirements 12.6, 12.7**

**Property DB5: Validation propagation**
*For any* request whose body/query violates Service-Layer validation (e.g., `amount <= 0`, naive datetime), the response SHALL be HTTP 422 and no row SHALL be mutated.
**Validates: Requirement 13.7**

**Property DB6: Auth mode behavior**
*For any* configured `dashboard_auth_mode`:
- `"none"`: requests succeed without `X-Dashboard-Token` header.
- `"shared_header"`: requests without/with-wrong `X-Dashboard-Token` produce HTTP 401; with-correct token produce normal response.
**Validates: Requirements 14.2, 14.3**

### Cross-Cutting

**Property X1: No real Gemini call in default tests**
*For any* default `pytest` run with `GOOGLE_API_KEY` unset, no test SHALL cause an HTTP request to `*.googleapis.com`, `generativelanguage.googleapis.com`, or `*.aiplatform.googleapis.com`.
**Validates: Requirements 3.5, 16.2, 16.3**

**Property X2: Schema unchanged**
The set of tables and columns reported by `Base.metadata` after Phase 4–8 SHALL equal the set after Phase 3.
**Validates: Requirement 15.8**

## Error Handling

| Sumber | Mekanisme | Layer pemanggil |
|---|---|---|
| Pydantic validation | 422 oleh FastAPI | API |
| `ValidationError` service | 422 via global exception handler | API |
| `NotFoundError` service | 404 via global exception handler | API |
| `PermissionDeniedError` service | 403 via global exception handler | API |
| `IntegrityError`/`OperationalError` | 500 generic | API |
| Token mismatch (device/dashboard) | 401 | API |
| Agent runtime exception | log + 500 (no stack trace) | `POST /agent/text` |
| Tool wrapper service exception | sudah jadi failure dict di Phase 3 | tool wrapper |
| Scheduler tick item exception | catch + `mark_reminder_failed`, lanjut item berikut | scheduler |
| WhatsApp Stub | tidak pernah memanggil API real; hanya log line | integrations |

Global exception handler dipasang di `app/main.py` via `app.add_exception_handler` untuk tiga tipe service exception. Endpoint biasa tidak perlu try/except.

## Testing Strategy

### Library

- `pytest` + `hypothesis` (sudah ada).
- `apscheduler>=3.10` ditambahkan ke `requirements.txt`.
- `google-adk>=1.0` ditambahkan ke `requirements.txt`. **Catatan:** versi pasti diverifikasi pada `pip install` saat `tasks` task 1.x; jika rilis stable resmi belum ada, disesuaikan ke `>=2.0a` dengan persetujuan eksplisit di task tersebut.
- Untuk test, kita pakai `httpx.AsyncClient` melalui `TestClient` FastAPI biasa (sinkron) bila handler sinkron, atau `httpx.ASGITransport`/`anyio` jika perlu untuk handler async.

### Test Strategy per Komponen

| Komponen | File test | Strategi |
|---|---|---|
| Agent Runtime tool factory | `test_agent_runtime.py` | PBT untuk AR1–AR4, AR6, AR7 (signature inspection, monkeypatch `task_tools.create_task_tool` untuk merekam args) |
| Mode selection | `test_agent_runtime.py` | Property AR5: matrix settings → expected mode |
| `POST /agent/text` | `test_agent_text_endpoint.py` | `TestClient`. Monkeypatch `app.agent.runtime.run_text` untuk mengembalikan `AgentRunResult` deterministik. Jangan monkeypatch tool wrappers — biarkan service layer asli. |
| Scheduler tick | `test_scheduler_tick.py` | Panggil `reminder_tick` langsung (tidak start `BackgroundScheduler`). Inject `db_factory` ke session in-memory. Inject `whatsapp_send` mock yang bisa raise. |
| Lifecycle scheduler | `test_scheduler_tick.py` | Test memakai `with TestClient(app)` dan memeriksa `app.state.scheduler` exists/None berdasarkan `settings.scheduler_enabled`. Sebelum test, `monkeypatch.setattr(settings, "scheduler_enabled", ...)`. |
| Devices API | `test_devices_api.py` | `TestClient`. Properti DA3 diuji dengan dua poll berurutan. |
| Dashboard API | `test_dashboard_api.py` | `TestClient`. Memakai `dashboard_auth_mode = "none"` untuk happy path; satu test menyetel `"shared_header"` untuk DB6. |

### Konvensi PBT

- Setiap PBT diberi komentar tepat di atas dekorator: `# Feature: agent-runtime-and-apis, Property X: ...`.
- `settings(max_examples=100, deadline=None)` default. Endpoint test boleh menurunkan ke 30 jika setup berat.
- Generator tetap memakai pola Phase 3 (`aware_future_dt`, `non_blank_str`, dll.) — diimpor ulang dari `conftest.py` jika sudah ada, atau didefinisikan lokal.
- Network kill-switch: file `app/tests/conftest.py` ditambah autouse fixture yang memonkeypatch `socket.socket` agar test default tidak bisa membuat outbound connection. Fixture ini memastikan AR6, RS5, X1.

### Smoke Manual

```bash
GOOGLE_API_KEY=... python -m scripts.run_agent_text "catat makan siang 20000"
```

Tidak dijalankan di CI default; dipakai developer setelah `.env` setempat dikonfigurasi.

## Open Decisions

1. **Dashboard auth mode default (Req 14.4)** — Pilihan: `"none"` untuk MVP. Rationale: dashboard berjalan di lokal/VPS internal di Phase 8; `"shared_header"` tetap tersedia tanpa refactor saat dashboard publik. **Status: chosen.**
2. **`google-adk` version pinning** — Pilihan: `>=1.0` jika ada major stable; jatuh ke `>=2.0a2` jika tidak. **Status: deferred to first task in implementation plan; verifikasi `pip index versions google-adk` saat eksekusi.**
3. **APScheduler timezone** — Pilihan: `BackgroundScheduler(timezone=ZoneInfo("UTC"))` agar interval pasti dan konsisten dengan `now_utc()`. **Status: chosen.**
4. **Per-request vs singleton `InMemorySessionService`** — Pilihan: per-request untuk MVP (no cross-user state). **Status: chosen.** Akan ditinjau ulang saat fitur conversation history dibutuhkan.

# Taskbot

Taskbot is an AIoT pocket assistant for students, inspired by BMO, designed for academic task management and daily expense tracking.

## MVP Goal
The Minimum Viable Product (MVP) focuses on a text-command-based backend system to handle tasks, expenses, and summaries using Google ADK as the agent runtime. Hardware integration is planned for later phases.

## High-Level Architecture
- **ESP32-S3 (Future Phase)**: Acts as a local interaction controller (OLED face, microphone, speaker, device commands).
- **VPS/Backend (MVP Phase)**: Main backend and AI runtime built with FastAPI.
- **Agent Runtime**: Powered by Google ADK.
- **Database**: SQLite for MVP, migrating to PostgreSQL in later phases.

## Development Phases Summary
The project is divided into 14 phases, starting from backend skeleton and database design, progressing to the Google ADK agent integration, and eventually adding the dashboard, hardware prototype, audio processing, and WhatsApp notifications.

**Current Phase:** Phase 13 shipped (frontend BMO redesign on top of Phase 12 backend). Backend regression: 310/310 tests passing. **ESP32-S3 firmware integration is the next milestone** — the normative contract lives at [`docs/ESP32_INTEGRATION_CONTRACT.md`](docs/ESP32_INTEGRATION_CONTRACT.md) with rationale at [`docs/ESP32_INTEGRATION_ADR.md`](docs/ESP32_INTEGRATION_ADR.md). For phase-level history see [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Backend Development

The service layer (`app/services/`) and the tool wrapper layer (`app/tools/`) are implemented and covered by unit and property-based tests. Tool wrappers are plain Python functions that return a normalized `{"success": bool, "type": str, ...}` dict; Google ADK integration is deferred to Phase 4.

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Database Migration
```bash
alembic upgrade head
```

### Seed Development Data
```bash
python -m scripts.seed_dev
```

### Run Backend Locally
```bash
uvicorn app.main:app --reload
```

### Run Tests
```bash
python -m pytest app/tests/ -v
```

## Agent Runtime & API (Phase 4–6)

Bagian ini merangkum cara memakai Agent Runtime, scheduler, dan endpoint `POST /agent/text` setelah Phase 4–8 di-merge. Default-nya hermetic: tanpa `GOOGLE_API_KEY` agent berjalan dalam mode **fake** dan tidak melakukan panggilan jaringan ke Gemini.

### Menjalankan agent dari CLI

Untuk smoke-test agent end-to-end tanpa lewat HTTP, gunakan script `scripts/run_agent_text.py`:

```bash
python -m scripts.run_agent_text "<text>" --user-id <id> [--device-id <id>]
```

Contoh:

```bash
python -m scripts.run_agent_text "catat tugas algoritma deadline besok jam 10" --user-id 1
```

Argumen `--user-id` dan `--device-id` opsional di CLI dan akan jatuh ke environment variable berikut bila tidak diisi:

- `TASKBOT_USER_ID` — fallback untuk `--user-id`.
- `TASKBOT_DEVICE_ID` — fallback untuk `--device-id` (boleh kosong; saat tidak ada device, tool `send_device_command` short-circuit ke failure tanpa menyentuh service layer).

Untuk run yang benar-benar offline/hermetic (cocok untuk demo lokal atau CI tanpa kunci Gemini), set `AGENT_MODE=fake` di `.env` atau export sementara:

```bash
# Linux/macOS
AGENT_MODE=fake python -m scripts.run_agent_text "ringkasan hari ini" --user-id 1

# Windows PowerShell
$env:AGENT_MODE="fake"; python -m scripts.run_agent_text "ringkasan hari ini" --user-id 1
```

Saat `AGENT_MODE` kosong, runtime auto-select: `real` bila `GOOGLE_API_KEY` terisi, `fake` bila kosong. Output script berupa JSON `{reply, actions, device_feedback, status}` ke stdout. Text kosong/whitespace exit dengan status non-zero dan menulis usage ke stderr.

### Mengaktifkan scheduler

Reminder Scheduler dimatikan secara default agar test dan development run tidak memicu background job. Untuk menjalankannya, set di `.env`:

```dotenv
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_SECONDS=60
```

- `SCHEDULER_ENABLED=true` — saat aplikasi start (`uvicorn app.main:app`), APScheduler `BackgroundScheduler` ikut dinyalakan dan dimatikan otomatis pada shutdown lewat FastAPI lifespan.
- `SCHEDULER_INTERVAL_SECONDS=60` — periode antar Scheduler Tick dalam detik (default `60`). Setiap tick mengambil Due Reminder via `reminder_service.list_due_reminders`, mendispatch ke device command queue dan/atau WhatsApp Stub sesuai `channel`, lalu menandai reminder `SENT` atau `FAILED`.

WhatsApp Stub tidak memanggil API eksternal mana pun (lihat `app/integrations/whatsapp.py`); integrasi WhatsApp Cloud API tidak termasuk di Phase 4–8.

### Memanggil `POST /agent/text`

Endpoint utama untuk client (frontend, ESP32, dashboard debug). Body JSON minimal: `user_id` dan `text`; `device_id` dan `timezone` opsional.

Contoh dengan `curl`:

```bash
curl -X POST http://localhost:8000/agent/text \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "device_id": 1,
    "text": "catat tugas algoritma deadline besok jam 10",
    "timezone": "Asia/Jakarta"
  }'
```

Response sukses (HTTP 200):

```json
{
  "reply": "Tugas algoritma sudah dicatat.",
  "actions": [
    {
      "success": true,
      "type": "task",
      "task_id": 12,
      "title": "algoritma"
    }
  ],
  "device_feedback": null
}
```

Catatan respons:

- `reply` — teks satu kalimat dari agent (Bahasa Indonesia).
- `actions` — list Tool Result Dict dari Phase 3 tool wrappers, urut sesuai eksekusi.
- `device_feedback` — Tool Result Dict `send_device_command` terakhir yang sukses, atau `null` bila tidak ada.

Kode error yang relevan:

- `422` — `text` kosong/whitespace atau body tidak valid.
- `404` — `user_id` atau `device_id` tidak ditemukan; agent tidak dipanggil.
- `500` — Agent Runtime raise; endpoint tetap mencatat `VoiceCommandLog` dengan `status="error"` dan tidak membocorkan stack trace ke client.

## Frontend Dashboard (Phase 9)

The dashboard SPA at `frontend/` consumes the backend above. It uses
**Vite + React + TypeScript + Tailwind**, *not* Next.js. No SSR, no
server actions, no backend-for-frontend layer — the browser talks to
FastAPI directly.

### Run the frontend

```bash
cd frontend
cp .env.example .env
# Fill in VITE_DEMO_USER_ID and VITE_DEMO_DEVICE_ID from `python -m scripts.seed_dev`
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/agent`,
`/dashboard`, `/devices`, and `/healthz` to `http://127.0.0.1:8000` so
no CORS configuration is required during development.

### Frontend `.env` keys

| Key | Required | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | optional | Origin of FastAPI. Default `http://127.0.0.1:8000`. |
| `VITE_DEMO_USER_ID` | **yes** | UUID printed by `python -m scripts.seed_dev`. |
| `VITE_DEMO_DEVICE_ID` | optional | UUID for demo device. Without it, AgentCommandBox warns and skips device feedback. |
| `VITE_DASHBOARD_TOKEN` | optional | Set only when backend uses `DASHBOARD_AUTH_MODE=shared_header`. |

### Test the Agent Command Box

On the **Ringkasan** page, type `catat makan siang 20000` and click
**Jalankan**. The dashboard should display the agent reply, device
feedback (if `VITE_DEMO_DEVICE_ID` is set), and refresh the summary
stat cards automatically.

### Building for production

```bash
cd frontend
npm run build
```

Output goes to `frontend/dist/`. Serve with any static file server.
For production deployment configure FastAPI `CORSMiddleware` or put
both behind a reverse proxy on the same origin (out of scope for
Phase 9).

Full runbook: [`docs/FRONTEND_DASHBOARD.md`](docs/FRONTEND_DASHBOARD.md).
Phase summary: [`docs/PHASE_9_SUMMARY.md`](docs/PHASE_9_SUMMARY.md).

### What's intentionally NOT in Phase 9

- Phase 8.5 backend smoke test (deferred).
- Audio capture / STT / TTS.
- Real WhatsApp integration.
- ESP32 firmware.
- JWT/OAuth/session auth (dashboard auth stays at MVP `none`).
- Next.js, Remix, Angular, Vue, SvelteKit.

## Audio Backend (Phase 10)

`POST /agent/audio` accepts a multipart audio upload, runs a **fake**
STT to produce a deterministic transcript, dispatches the transcript
through the existing agent flow, and returns the standard
`reply`/`actions`/`device_feedback` plus transcription, audio, and TTS
metadata. **Phase 10 is hermetic-only** — no real STT/TTS provider is
integrated; provider selection is deferred to Phase 10.5.

### Quick example

```bash
curl -X POST http://127.0.0.1:8765/agent/audio \
  -F "user_id=<demo-user-uuid>" \
  -F "device_id=<demo-device-uuid>" \
  -F "timezone=Asia/Jakarta" \
  -F "file=@sample.wav"
```

Or via the in-process CLI (mirrors `scripts/run_agent_text.py`):

```powershell
$env:TASKBOT_USER_ID = "<demo-user-uuid>"
$env:TASKBOT_DEVICE_ID = "<demo-device-uuid>"
python -m scripts.run_agent_audio path\to\sample.wav
```

### Settings (`.env`)

```
AUDIO_STT_MODE=fake
AUDIO_TTS_MODE=fake
FAKE_STT_TRANSCRIPT=catat makan siang 20000
MAX_AUDIO_UPLOAD_MB=10
FAKE_TTS_FORMAT=wav
FAKE_TTS_SAMPLE_RATE=16000
```

`MAX_AUDIO_UPLOAD_MB` is decimal MB (10 MB = 10_000_000 bytes).

Full runbook: [`docs/AUDIO_BACKEND.md`](docs/AUDIO_BACKEND.md).
Phase summary: [`docs/PHASE_10_SUMMARY.md`](docs/PHASE_10_SUMMARY.md).

### What's intentionally NOT in Phase 10

- Real STT/TTS provider (Google Cloud Speech, OpenAI Whisper,
  ElevenLabs, ADK Live Audio API, etc.).
- Provider SDKs in `requirements.txt`.
- Streaming, WebSocket audio, wake-word.
- ESP32 firmware (INMP441/I2S, MAX98357A).
- Frontend microphone UI.
- Binary TTS audio fetch endpoint (planned for Phase 11+).

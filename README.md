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

**Current Phase:** Phase 3 (Service Layer & Tool Wrappers) — implemented and tested.

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

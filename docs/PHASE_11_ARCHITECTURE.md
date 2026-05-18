# Phase 11 — End-to-End Architecture (ESP32 Voice Integration)

This document is the **canonical end-to-end blueprint** for the ESP32 ↔ FastAPI ↔ Gemini integration. It freezes contracts so the backend team and the firmware team can work in parallel without breaking each other.

For implementation specifics see:
- [`PHASE_11_BACKEND.md`](PHASE_11_BACKEND.md) — what the FastAPI side must build
- [`PHASE_11_FIRMWARE.md`](PHASE_11_FIRMWARE.md) — what the ESP32-S3 side must build

## Goals

1. **Realtime-feel UX** — user does not stare at silence for >3 seconds.
2. **Hybrid TTS** — pre-recorded audio for common cases (zero latency), Gemini TTS only for dynamic answers.
3. **No regex on `reply`** — ESP firmware switches on a server-classified `audio_code` enum.
4. **One vendor for AI** — Gemini multimodal handles STT (audio → text) and the agent runtime; Cloud TTS or Gemini TTS for synthesis.
5. **SD card audio cache** — ESP32-S3 reads pre-recorded WAV from microSD; firmware never decodes audio formats it cannot stream natively.

## Tech inventory

| Layer | Component |
|---|---|
| Mic | INMP441 over I2S |
| Speaker | MAX98357A over I2S |
| Storage | microSD (SPI), FAT32, ≥4 GB |
| Display | OLED SSD1306 128×64 over I2C (or matching) |
| Network | WiFi (HTTPS to backend) |
| Backend | FastAPI (existing), Phase 10 plumbing |
| AI | Gemini multimodal (audio in → text + tools) |
| TTS | Gemini TTS (`gemini-3.1-flash-tts-preview`) for dynamic; pre-recorded WAV on SD card for static |

## Roles in one sentence

- **ESP32** captures audio, plays filler immediately, posts audio, then plays the response (either from SD or fetched from backend).
- **FastAPI** validates audio, routes to Gemini multimodal for transcription + agent, classifies the response into a `directive`, optionally synthesizes TTS, returns JSON.
- **Gemini** transcribes Indonesian audio and decides which tool (`create_task` / `create_expense` / etc.) to invoke. Tool execution updates the SQLite DB. Gemini also generates dynamic TTS audio when needed.

## End-to-end timeline

```
T+0.0s  User releases push-to-talk button
        ESP captures last ~3s of audio buffer (stops on silence or button release)

T+0.0s  ESP starts playing /sd/sounds/ack_thinking.wav
        ESP shows face_thinking on OLED
        ESP starts HTTP POST /agent/audio (multipart, audio bytes in body)

T+1.5s  ack_thinking.wav done → ESP idles (face still thinking)
        Backend: validation done, Gemini multimodal call in flight

T+3.0s  ESP plays /sd/sounds/ack_still_thinking.wav (filler #2, optional)

T+3.5s  Backend response arrives:
        - directive.audio_code = "ok_expense"
        - directive.face = "happy"
        - directive.screen_text = "Rp 10.000\nMakan siang"
        - directive.fetch_url = null
        ESP fades out filler audio
        ESP renders face_happy + screen_text on OLED
        ESP plays /sd/sounds/ok_expense.wav (~2s)

T+5.5s  Done. ESP idles, ready for next command.
```

For dynamic answers (e.g. "apa itu algoritma?"):

```
T+0.0s  Same start: filler audio + POST /agent/audio
T+3.5s  Response: directive.audio_code = "fallback_tts", fetch_url = "/agent/audio/{log_id}/tts"
T+3.5s  ESP keeps playing filler (or starts ack_still_thinking)
T+3.5s  ESP issues GET <fetch_url> in parallel
T+~6s   First audio bytes arrive (server is streaming Gemini TTS chunks as they come)
T+~6s   ESP fades out filler, starts streaming TTS audio to MAX98357A
T+~12s  TTS playback ends. Done.
```

## Request contract

`POST /agent/audio` — multipart/form-data

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | binary | yes | WAV/MP3/WebM/M4A; ESP sends WAV 16kHz mono 16-bit PCM |
| `user_id` | string (UUID) | yes | provisioned during ESP pairing |
| `device_id` | string (UUID) | yes | provisioned during ESP pairing |
| `timezone` | string | no | default `Asia/Jakarta` |

Headers:
- `Content-Type: multipart/form-data; boundary=...`
- (Optional, future) `X-Device-Token: <token>` for hardware authentication

## Response contract (Phase 10 + Phase 11 extension)

```json
{
  "reply": "Pengeluaran Rp10.000 sudah dicatat.",
  "actions": [
    { "success": true, "type": "expense", "id": "...", "message": "..." }
  ],
  "device_feedback": null,
  "transcription": {
    "text": "catat makan siang sepuluh ribu",
    "mode": "gemini",
    "duration_ms": 2400,
    "confidence": null
  },
  "audio": {
    "filename": "voice.wav",
    "content_type": "audio/wav",
    "size_bytes": 96044
  },
  "tts": {
    "mode": "fake",
    "available": true,
    "content_type": "audio/wav"
  },
  "directive": {
    "audio_code": "ok_expense",
    "face": "happy",
    "screen_text": "Rp 10.000\nMakan siang",
    "fetch_url": null
  }
}
```

`directive` is the **only field ESP firmware needs to act on** for playback decisions. Everything else is for logs, debugging, or future use.

## `audio_code` enum (frozen)

| `audio_code` | When | ESP plays |
|---|---|---|
| `ok_expense` | `create_expense` succeeded | `/sd/sounds/ok_expense.wav` |
| `ok_task` | `create_task` succeeded | `/sd/sounds/ok_task.wav` |
| `ok_reminder` | `set_reminder` succeeded | `/sd/sounds/ok_reminder.wav` |
| `ok_summary` | `get_today_summary` succeeded | `/sd/sounds/ok_summary.wav` |
| `ok_generic` | other action succeeded | `/sd/sounds/ok_generic.wav` |
| `err_generic` | any action failed | `/sd/sounds/err_generic.wav` |
| `fallback_tts` | no actions; agent answered free-form | fetch `directive.fetch_url`, stream-play |

Adding a new code requires server change, ESP firmware change, and a new WAV file on SD card. Treat the enum as a versioned contract.

## `face` enum (frozen)

| `face` | When | OLED renders |
|---|---|---|
| `happy` | success | smile pixmap |
| `sad` | error | frown pixmap |
| `thinking` | filler / fallback | dots animation |
| `neutral` | summary / informational | flat line pixmap |

Other server values: ESP firmware falls back to `neutral`.

## `screen_text`

- Server always provides a string ≤60 characters (truncated with `…` if needed).
- ESP firmware renders as-is on OLED. Newlines (`\n`) are honored.
- ESP firmware MUST NOT parse content. It is opaque.

## `fetch_url`

- Phase 10: always `null`.
- Phase 11: relative path `/agent/audio/{voice_command_log_id}/tts` when `audio_code == "fallback_tts"`.
- ESP firmware appends to `VITE_API_BASE_URL` (or its hardcoded base) and issues `GET`.
- Returns `audio/wav` (16-bit PCM 24 kHz mono); chunked transfer encoding allowed.

## Audio retention

- ESP records, sends, then can discard local copy.
- Backend: bytes processed in memory, never persisted.
- Only `transcription.text` is logged in `VoiceCommandLog`.
- TTS audio is generated on demand and cached in process memory keyed by `voice_command_log_id` for ~5 minutes (then evicted) to support `fetch_url` retrieval.

## Failure modes (frozen)

| Failure | Server status | `directive` (if response sent) | ESP behavior |
|---|---|---|---|
| Validation rejects (oversize/empty/bad type) | 400/413 | not sent | Play `err_generic.wav`, face_sad, "Rekaman bermasalah" on OLED |
| Unknown user/device | 404 | not sent | Play `err_generic.wav`, face_sad, "Akun belum siap" |
| Agent runtime crash | 500 | not sent | Play `err_generic.wav`, face_sad, "Coba lagi sebentar" |
| TTS fetch fails | 200 (main) + GET 5xx | code=fallback_tts, fetch failed at GET | Play `err_generic.wav` after 5s timeout |
| Network timeout | n/a | n/a | Play `ack_slow_network.wav`, then `err_generic.wav` after 30s |

ESP firmware MUST NOT crash on any of these. It always returns to idle.

## Versioning

- This document defines protocol version 1.
- Server implementations MUST set response header `X-Lyla-Protocol: 1`.
- ESP firmware MUST refuse to act on responses with mismatched version (play `err_generic.wav`).
- Schema-additive changes (new optional field) keep version 1.
- Removing or renaming a field bumps to version 2 and is breaking.

## Out of scope for Phase 11

- Wake-word ("Hey Lyla") — Phase 12.
- Continuous conversation (multi-turn) — Phase 13.
- Voice biometrics — never.
- On-device STT — never (latency budget too tight).
- WebRTC / streaming upload — Phase 14+.

## Decision log

| Decision | Choice | Rationale |
|---|---|---|
| STT vendor | Gemini multimodal | One API key shared with agent; quality acceptable for Indonesian |
| TTS vendor | Gemini TTS preview | Same API key; latency 6s (mitigated by filler) |
| Audio format ESP→server | WAV 16kHz mono 16-bit | Smallest reasonable; Gemini accepts directly |
| Audio format server→ESP | WAV 24kHz mono 16-bit | Gemini TTS native output rate |
| Pre-recorded audio storage | SD card on ESP32-S3 | Cheap, allows updates without firmware reflash |
| Audio code dispatch | Enum string in `directive.audio_code` | Deterministic, no NLP brittleness |
| Filler timing | ESP-driven | Server cannot trigger before response is sent |

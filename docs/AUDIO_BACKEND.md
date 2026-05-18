# Audio Backend (Phase 10)

This document is the runbook for the Phase 10 audio backend.

## Overview

Phase 10 adds the audio path foundation for Taskbot: a `POST /agent/audio`
endpoint that accepts a multipart file upload, transcribes it via a
**fake** STT, runs the existing agent flow on the transcript, and
returns the standard agent response plus transcription and TTS metadata.

**Phase 10 is fake/hermetic only.** No real STT or TTS provider is
integrated yet. Provider selection (Google Cloud Speech, OpenAI Whisper,
ElevenLabs, ADK Live Audio API, etc.) is deliberately deferred to a
future phase so the backend audio plumbing can be tested end-to-end
offline first.

This is parallel to the existing fake/real split for the agent runtime
(`app/agent/fake.py` vs `app/agent/runtime.py::_run_real`).

## Endpoint

`POST /agent/audio`

Request: `multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | UploadFile | yes | `.wav`/`.mp3`/`.webm`/`.m4a` |
| `user_id` | string | yes | UUID of seeded user |
| `device_id` | string | no | UUID of paired device |
| `timezone` | string | no | IANA tz; defaults to `Asia/Jakarta` |

Response (200): JSON.

```json
{
  "reply": "Tugas algoritma sudah dicatat.",
  "actions": [
    { "success": true, "type": "task", "task_id": "..." }
  ],
  "device_feedback": null,
  "transcription": {
    "text": "catat makan siang 20000",
    "mode": "fake",
    "duration_ms": null,
    "confidence": null
  },
  "audio": {
    "filename": "voice.wav",
    "content_type": "audio/wav",
    "size_bytes": 12345
  },
  "tts": {
    "mode": "fake",
    "available": true,
    "content_type": "audio/wav"
  }
}
```

`AgentAudioResponse` inherits from `AgentTextResponse` so the
`reply`/`actions`/`device_feedback` contract has one source of truth and
cannot drift between text and audio paths.

### Status codes

| Code | Cause | Side effect |
|---|---|---|
| 200 | Happy path | one `VoiceCommandLog` row written |
| 400 | Validation: empty file, missing filename, unsupported extension or content type | no log row |
| 404 | Unknown `user_id` or `device_id` | no log row |
| 413 | File exceeds `MAX_AUDIO_UPLOAD_MB` | no log row |
| 500 | Agent runtime crash after STT succeeded | log row with `status="error"`, transcript as `input_text` |
| 502 | STT raised (Phase 10: should not happen with fake mode; reserved for real provider failures) | no log row |

`VoiceCommandLog` is written **only when there is a transcript**. STT
failures never pollute the log table.

## Settings

All settings are loaded from project-root `.env` via `app/config.py`.
Phase 10 keys are model/provider agnostic.

| Env var | Default | Purpose |
|---|---|---|
| `AUDIO_STT_MODE` | `fake` | Phase 10 only supports `fake`; any other value raises `ConfigurationError` |
| `AUDIO_TTS_MODE` | `fake` | Phase 10 only supports `fake`; any other value raises `ConfigurationError` |
| `FAKE_STT_TRANSCRIPT` | `catat makan siang 20000` | Canned transcript returned by fake STT |
| `MAX_AUDIO_UPLOAD_MB` | `10` | Decimal MB; **10 MB = 10_000_000 bytes** |
| `FAKE_TTS_FORMAT` | `wav` | Reserved for future use; fake TTS always emits WAV |
| `FAKE_TTS_SAMPLE_RATE` | `16000` | Sample rate of generated silent WAV |

`MAX_AUDIO_UPLOAD_MB` is interpreted as **decimal** megabytes
(`1 MB = 1_000_000 bytes`) to match the user-facing mental model and HTTP
`Content-Length` semantics. This is documented next to the setting in
`app/config.py` so a future contributor doesn't accidentally switch to
binary MiB.

## Fake STT

`app/audio/stt.py::transcribe_audio(file_bytes, filename, content_type)`

- Returns `TranscriptionResult(text=settings.fake_stt_transcript, mode="fake", ...)`.
- Does NOT inspect `file_bytes` content beyond `len()`.
- Raises `ConfigurationError` when `AUDIO_STT_MODE != "fake"`.
- Deterministic: same inputs always produce equal `TranscriptionResult`.

To override the transcript for demos or test scenarios, set
`FAKE_STT_TRANSCRIPT` in `.env` before starting uvicorn.

## Fake TTS

`app/audio/tts.py::synthesize_text(text)`

- Generates a minimal valid silent WAV using the stdlib `wave` module
  (no new Python dependency).
- Returns `SynthesisResult(mode="fake", content_type="audio/wav", audio_bytes=<RIFF/WAVE>, ...)`.
- Bytes start with `b"RIFF"` and contain `b"WAVE"` at offset 8.
- Raises `ConfigurationError` when `AUDIO_TTS_MODE != "fake"`.

The fake TTS audio bytes are **not** returned in the JSON response —
only metadata (`mode`, `available`, `content_type`). This keeps the
response size bounded and avoids base64 bloat. A binary fetch endpoint
(e.g. `GET /agent/audio/{voice_command_log_id}/tts`) will be added in a
future phase when ESP32 needs to play TTS audio.

## Audio retention

Uploaded audio bytes are processed entirely in memory and discarded
when the handler returns. They are **never** persisted to disk or any
storage layer. Only the transcript text is logged in `VoiceCommandLog`.

This is enforced by the implementation (no `open(...)`, no `boto3`, no
disk writes anywhere in `app/audio/` or `app/api/audio.py`) but not by a
formal property test in Phase 10.

## Hermeticity (Property AR7)

`AGENTS.md` Hard Rule 8 requires:

> `app/audio/stt.py`, `app/audio/tts.py`, and `app/audio/_seam.py` MUST
> NOT import any provider SDK (`google.cloud.speech`,
> `google.cloud.texttospeech`, `openai`, `whisper`, `elevenlabs`,
> `deepgram`, `assemblyai`) and MUST NOT import `google.adk.*`.

This is enforced by `app/tests/test_audio_fake_hermeticity.py` using
the same `sys.modules` diff strategy as Property AR6
(`test_agent_fake_hermeticity.py`).

## Running audio tests

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q app/tests/test_audio_validation.py app/tests/test_fake_stt.py app/tests/test_fake_tts.py app/tests/test_audio_fake_hermeticity.py app/tests/test_agent_audio_endpoint.py -v
```

Or the full suite (recommended before commits):

```powershell
python -m pytest -q
# Expected: 230 passed
```

## Manual testing

CLI (in-process, mirrors `scripts/run_agent_text.py`):

```powershell
.\.venv\Scripts\Activate.ps1
$env:TASKBOT_USER_ID = "<demo-user-uuid>"
$env:TASKBOT_DEVICE_ID = "<demo-device-uuid>"
python -m scripts.run_agent_audio path\to\sample.wav
```

HTTP (uvicorn must be running; replace port to match yours):

```powershell
curl -X POST http://127.0.0.1:8765/agent/audio `
  -F "user_id=<demo-user-uuid>" `
  -F "device_id=<demo-device-uuid>" `
  -F "timezone=Asia/Jakarta" `
  -F "file=@sample.wav"
```

## Adding a real provider (future-phase guide)

When a real STT or TTS provider is added, the integration shape is:

1. Implement `SttProvider` or `TtsProvider` (Protocols in
   `app/audio/_seam.py`) in a new module under `app/audio/` (for example
   `app/audio/stt_google.py`).
2. Add a new mode value (e.g. `"google"`) to the `AUDIO_STT_MODE` /
   `AUDIO_TTS_MODE` allowed set.
3. Update `transcribe_audio` / `synthesize_text` dispatch in
   `app/audio/stt.py` / `app/audio/tts.py` to route to the new provider
   when the mode matches; keep the `"fake"` branch unchanged.
4. Add provider-specific settings (API key, region, voice name, etc.)
   to `app/config.py` and `.env.example`.
5. Property AR7 still applies: provider modules must not be reachable
   from `_seam.py`, `stt.py` (fake branch), or `tts.py` (fake branch).
   Real provider code can import its SDK only inside the `"real"`
   branch — mirror the `_run_real` deferred-import pattern in
   `app/agent/runtime.py`.

## Alternative architecture (informational)

The Phase 10 pipeline is **STT → text agent → TTS**. Google ADK Live
Audio API supports a single bidirectional audio agent (audio in, audio
out) that bypasses `POST /agent/text` entirely. This trades the clean
`VoiceCommandLog` audit trail (which depends on a discrete transcript
step) for lower latency and tone-aware reasoning.

Out of scope for Phase 10. Mentioned here so a future architect knows
the choice exists when picking a real provider.

## Limitations

Phase 10 explicitly does NOT include:

- Real STT or TTS provider.
- Streaming audio.
- WebSocket audio.
- Wake-word detection.
- ESP32 firmware (no INMP441/I2S code, no MAX98357A playback).
- Frontend microphone UI.
- Audio retention or replay.
- Multi-language detection.
- Speaker diarization.
- Voice biometrics.

These belong to later phases (Phase 11+ for ESP integration; a
provider-research phase for real STT/TTS).

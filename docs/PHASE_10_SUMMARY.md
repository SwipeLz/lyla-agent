# Phase 10 Summary — Audio Backend (Hermetic Foundation)

## Status

**Shipped and verified.** `python -m pytest -q` reports **230 passed**
(189 baseline + 41 new). No real STT or TTS provider integrated; this
is intentional. Provider selection is deferred to a later phase.

## What shipped

### New endpoint
- `POST /agent/audio` — multipart upload → fake STT → existing agent
  flow (via shared helper) → fake TTS metadata. Audio bytes processed
  in memory and discarded.

### New audio module (`app/audio/`)
- `_seam.py` — `TranscriptionResult`, `SynthesisResult`,
  `ConfigurationError`, `SttProvider`/`TtsProvider` Protocols.
- `stt.py` — `transcribe_audio()` returns `settings.fake_stt_transcript`.
- `tts.py` — `synthesize_text()` generates a minimal silent WAV using
  the stdlib `wave` module (zero new Python dependencies).

### Validation
- `app/utils/audio_validation.py` — `validate_audio()` accepts
  `.wav`/`.mp3`/`.webm`/`.m4a` and the corresponding content types
  (including `audio/x-m4a`, `audio/aac`, and `application/octet-stream`
  fallback). Rejects empty bytes, oversized payloads (decimal MB),
  unsupported extensions, missing filenames.

### Schemas
- `app/schemas/audio.py` — `AudioMetadataOut`, `TranscriptionInfoOut`,
  `FakeTTSInfoOut`, and `AgentAudioResponse` which **inherits from
  `AgentTextResponse`** so reply/actions/device_feedback have one
  source of truth across endpoints.

### Shared agent helper
- `app/api/_agent_helpers.py::process_agent_text_command()` —
  encapsulates user/device 404 checks, timezone fallback, runtime
  invocation, and `VoiceCommandLog` semantics. Used by `/agent/audio`.
  `/agent/text` was NOT refactored to use this helper because existing
  tests monkeypatch `app.api.agent.run_text` directly; routing through
  the helper broke 17 tests, so the original handler stays inline (per
  Task 9 revert gate in the execution plan).

### Hermeticity property AR7
- New AGENTS.md hard rule: `app/audio/*` MUST NOT import
  `google.cloud.speech`, `google.cloud.texttospeech`, `openai`,
  `whisper`, `elevenlabs`, `deepgram`, `assemblyai`, or `google.adk.*`.
- Enforced by `app/tests/test_audio_fake_hermeticity.py` using the
  same `sys.modules` diff strategy as Property AR6
  (`test_agent_fake_hermeticity.py`).

### Manual CLI
- `scripts/run_agent_audio.py` — in-process audio pipeline mirroring
  `scripts/run_agent_text.py`. Reads file → validates → fake STT →
  shared helper → fake TTS metadata → prints `AgentAudioResponse` JSON.

### Tests added (41 new)
- `test_audio_validation.py` — 16 cases (parametrized accept + reject)
- `test_fake_stt.py` — 5 cases
- `test_fake_tts.py` — 5 cases
- `test_audio_fake_hermeticity.py` — 3 cases (1 module-import + 2 Hypothesis property tests with 20 examples each)
- `test_agent_audio_endpoint.py` — 10 endpoint integration tests
- 2 additional cases come from Hypothesis @example pinning

### Documentation
- `docs/AUDIO_BACKEND.md` — runbook (English).
- `docs/PHASE_10_SUMMARY.md` — this file.
- `AGENTS.md` — Property AR7 added to Hard Rules; runbook added to
  canonical decisions list.
- `.env.example` — Phase 10 audio settings block.

## Files added

```
app/audio/__init__.py
app/audio/_seam.py
app/audio/stt.py
app/audio/tts.py
app/utils/audio_validation.py
app/schemas/audio.py
app/api/_agent_helpers.py
app/api/audio.py
scripts/run_agent_audio.py
app/tests/test_audio_validation.py
app/tests/test_fake_stt.py
app/tests/test_fake_tts.py
app/tests/test_audio_fake_hermeticity.py
app/tests/test_agent_audio_endpoint.py
docs/AUDIO_BACKEND.md
docs/PHASE_10_SUMMARY.md
```

## Files modified

```
app/config.py        # 6 new audio settings (audio_stt_mode, audio_tts_mode,
                     # fake_stt_transcript, max_audio_upload_mb, fake_tts_format,
                     # fake_tts_sample_rate)
app/main.py          # mount audio.router
.env.example         # Phase 10 audio settings block
AGENTS.md            # Property AR7 added; AUDIO_BACKEND.md referenced
README.md            # Phase 10 section
docs/ROADMAP.md      # Phase 10 marked current
```

## Files explicitly NOT changed

- `app/api/agent.py` — `/agent/text` handler kept bit-for-bit identical
  (revert documented in execution plan; rationale in module docstring).
- `app/agent/**` — agent runtime untouched.
- `app/services/**`, `app/models/**`, `app/tools/**`, `app/schemas/**`
  (except new `audio.py`) — business logic untouched.
- `agents/taskbot_agent/**` — dev shell untouched.
- `alembic/**` — no schema migrations.
- `requirements.txt` — no new Python dependencies.
- `frontend/**` — frontend untouched.

## How to run end-to-end

```powershell
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head      # if not already migrated
python -m scripts.seed_dev          # if no demo user yet
uvicorn app.main:app --reload --port 8765
```

In a second terminal:

```powershell
.\.venv\Scripts\Activate.ps1
$env:TASKBOT_USER_ID = "<demo-user-uuid>"
$env:TASKBOT_DEVICE_ID = "<demo-device-uuid>"
python -m scripts.run_agent_audio path\to\sample.wav
```

Or via HTTP:

```powershell
curl -X POST http://127.0.0.1:8765/agent/audio `
  -F "user_id=<demo-user-uuid>" `
  -F "device_id=<demo-device-uuid>" `
  -F "timezone=Asia/Jakarta" `
  -F "file=@sample.wav"
```

## Verification gates

| Gate | Command | Result |
|---|---|---|
| Backend regression | `python -m pytest -q` | **230 passed** |
| AR7 enforcement | `python -m pytest -q app/tests/test_audio_fake_hermeticity.py` | 3 passed |
| Forbidden-deps audit | `findstr /R /S "google.cloud.speech google.cloud.texttospeech openai whisper elevenlabs deepgram assemblyai" app` | no matches |
| `requirements.txt` diff | `git diff --stat -- requirements.txt` | empty |

## Known issues encountered (and resolved)

1. **`/agent/text` refactor broke 17 tests.** Existing tests
   monkeypatch `app.api.agent.run_text` directly, but the helper
   imports `run_text` into its own namespace. Reverted per Task 9 gate;
   `/agent/audio` uses the helper inline, `/agent/text` keeps original
   inline form. Documented in `app/api/agent.py` module docstring so
   future contributors don't undo the revert.
2. **`DeviceStatus.ACTIVE` referenced in test fixture** — actually
   doesn't exist (constants are `ONLINE`/`OFFLINE`). Fixed during
   Wave 4.
3. **`Device.api_token` referenced in test fixture** — model doesn't
   have that column. Fixed during Wave 4.

## Intentionally NOT in Phase 10

- Real STT or TTS provider (Google Cloud Speech, OpenAI Whisper, ADK
  Live Audio API, ElevenLabs, etc.).
- Provider-specific SDKs in `requirements.txt`.
- Streaming audio, WebSocket audio.
- Wake-word detection.
- ESP32 firmware (INMP441/I2S, MAX98357A).
- Frontend microphone UI.
- Binary TTS audio fetch endpoint (deferred to Phase 11+).
- Audio retention / replay.
- Multi-language detection or speaker diarization.

## Caveats

- The audio script script depends on `TASKBOT_USER_ID` (or `--user-id`).
  If unset, the script exits with code 2 and stderr message — by
  design, since the agent flow needs a real user UUID.
- `MAX_AUDIO_UPLOAD_MB` is **decimal** (10 MB = 10_000_000 bytes), not
  binary MiB. Documented in `app/config.py` and the runbook.
- Fake TTS emits a ~100ms silent WAV. Real product use will need a
  longer/structured audio response that depends on the chosen provider.
- AR7 covers import-time and call-time hermeticity, but does NOT cover
  runtime network egress; the existing autouse network kill-switch in
  `app/tests/conftest.py` already enforces that.

## Recommended next phase

Three viable directions, in suggested priority:

1. **Phase 10.5 — Real STT (Google Cloud Speech)** — wire the first
   real provider behind `AUDIO_STT_MODE=google`. Highest user-visible
   value: dashboard demo with live audio input. Requires Google Cloud
   project + service account; reuse existing `GOOGLE_API_KEY`
   infrastructure where possible.
2. **Phase 11 — ESP32 audio integration** — firmware to capture I2S
   audio from INMP441, POST to `/agent/audio`, play back TTS via
   MAX98357A. Depends on Phase 10.5 only if real-time real STT is
   wanted; otherwise Phase 10 is sufficient for end-to-end demo with
   pre-recorded clips.
3. **Phase 10-alt — Evaluate ADK Live Audio API** — replaces the
   STT→text agent→TTS pipeline with a single bidirectional audio
   agent. Trade audit-trail simplicity for latency. Good candidate if
   user feedback demands sub-second response time.

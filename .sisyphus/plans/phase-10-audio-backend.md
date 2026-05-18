# Phase 10 — Audio Backend (Hermetic Foundation)

## TL;DR

> **Quick Summary**: Add `POST /agent/audio` to FastAPI backend. Multipart upload → audio validation → fake STT → reuse existing agent flow → response with transcription + TTS metadata. Zero real provider integration; zero new SDK; zero network calls. Hermetic-by-design.
>
> **Deliverables**:
> - `app/audio/` package (stt + tts adapters, fake-only)
> - `app/utils/audio_validation.py`
> - `app/schemas/audio.py`
> - `POST /agent/audio` endpoint reusing the shared agent helper
> - `scripts/run_agent_audio.py` (in-process CLI)
> - 5 new test files (validation, stt, tts, endpoint, AR7 hermeticity)
> - `docs/AUDIO_BACKEND.md`, `docs/PHASE_10_SUMMARY.md`
> - Updates: `README.md`, `docs/ROADMAP.md`, `.env.example`, `AGENTS.md` (Property AR7)
>
> **Estimated Effort**: Medium (one focused session)
> **Parallel Execution**: YES — 5 waves
> **Critical Path**: settings → audio adapters → shared helper → endpoint → tests → docs

---

## Context

### Original Request

Phase 10 — backend audio path foundation. Provider research and real STT/TTS deferred. Goal: ESP32-compatible vertical slice that future providers can plug into without touching call sites.

### Backend Inspection Findings (already read)

| File | Key facts |
|---|---|
| `app/config.py` | `Settings(BaseSettings)` with `pydantic_settings`. Loads project-root `.env` by absolute path. Add new fields here. |
| `app/api/agent.py` | Existing `POST /agent/text` handler. Order: user 404 → device 404 → tz → `run_text` → success log OR error log + 500. Tested by `test_agent_text_endpoint.py`. |
| `app/agent/runtime.py` | `async run_text(...)` builds tools per request, dispatches to `_run_real`/`_run_fake`. Returns `AgentRunResult`. |
| `app/services/log_service.py` | `create_voice_command_log(db, user_id, device_id, input_text, parsed_actions, response_text, status)`. Sync, raises `ValidationError`/`NotFoundError`. |
| `app/agent/fake.py` | Pattern reference: keyword detection, no SDK imports. Hermeticity enforced by AR6 test (`test_agent_fake_hermeticity.py`). |
| `app/tests/test_agent_fake_hermeticity.py` | Style template for AR7 test: `sys.modules` purge before + assert no forbidden modules after. |
| `app/services/AGENTS.md` | Services raise typed exceptions. Audio adapters do NOT belong here. |

### Adaptation Notes

- **Settings field naming**: pydantic-settings auto-lowercases. `AUDIO_STT_MODE` env var → `settings.audio_stt_mode` Python attribute. Document both.
- **Async/sync boundary**: API handler is async; `run_text` is async; `log_service.create_voice_command_log` is sync. Shared helper must be `async def` and call sync log service directly (matches `app/api/agent.py` exactly).
- **AR6 test as template**: copy structure verbatim for AR7 — `_purge_*_from_sys_modules()` + `_FORBIDDEN_MODULES` tuple + `assert not in sys.modules`.
- **`UploadFile.size`** in starlette can be `None` for streaming uploads. Validate by reading body bytes once and measuring `len(bytes)` — also avoids second-read concerns.
- **Audio retention**: read `await file.read()` once into local variable, pass bytes to STT, never touch disk. Drop after handler returns.

### Pre-Existing Risks

1. **`/agent/text` refactor risk**: existing 189 tests assert specific sequencing in `test_agent_text_endpoint.py`. Helper extraction must preserve every observable behavior. Plan includes a "revert if any test fails" gate.
2. **Pydantic v2 inheritance**: `AgentTextResponse` is a `BaseModel`. Composing into `AgentAudioResponse` via inheritance is cleanest — extra fields added, parent fields unchanged.
3. **Network kill-switch**: existing autouse fixture patches `socket.socket`. Audio tests don't open sockets, so compatible by default. Verify in regression wave.

---

## Work Objectives

### Core Objective

Ship a working `POST /agent/audio` that reuses existing agent flow, returns the documented response shape, and stays hermetic. Real STT/TTS providers are out of scope.

### Concrete Deliverables

- `app/audio/__init__.py`, `app/audio/stt.py`, `app/audio/tts.py`
- `app/utils/audio_validation.py`
- `app/schemas/audio.py`
- `app/api/agent.py` — extend with shared helper + new audio handler (or new file `app/api/audio.py` mounted alongside)
- `scripts/run_agent_audio.py`
- `app/tests/test_audio_validation.py`, `test_fake_stt.py`, `test_fake_tts.py`, `test_agent_audio_endpoint.py`, `test_audio_fake_hermeticity.py`
- `docs/AUDIO_BACKEND.md`, `docs/PHASE_10_SUMMARY.md`
- Updates: `app/config.py`, `.env.example`, `README.md`, `docs/ROADMAP.md`, `AGENTS.md`

### Definition of Done

- [ ] `python -m pytest -q` reports `(189 + new) passed` with zero failures
- [ ] `POST /agent/audio` accepts multipart upload and returns `AgentAudioResponse`
- [ ] `POST /agent/text` behavior bit-for-bit unchanged (existing tests untouched)
- [ ] Property AR7 test added and passing
- [ ] No new entry in `requirements.txt`
- [ ] No `google.cloud.speech`, `google.cloud.texttospeech`, `openai`, `whisper`, `elevenlabs`, `deepgram`, `assemblyai` import anywhere in `app/`
- [ ] `AGENTS.md` Hard Rules section contains AR7
- [ ] `python -m scripts.run_agent_audio sample.wav` prints valid `AgentAudioResponse` JSON

### Must Have

- Multipart endpoint, in-memory processing, deterministic fake STT/TTS
- Provider-agnostic settings names
- AR7 hermeticity test paralleling AR6
- AgentAudioResponse composes AgentTextResponse (no field duplication)
- `requirements.txt` unchanged

### Must NOT Have (Guardrails — verbatim from prompt)

- OpenAI / Gemini Speech / Whisper API / Google Cloud Speech / ElevenLabs / AssemblyAI / Deepgram integration
- Provider SDKs in `requirements.txt`
- Any network call from any audio module
- API key requirement
- Frontend microphone UI
- ESP32 firmware, INMP441/I2S, MAX98357A code
- Wake word, streaming, WebSocket audio
- LangChain / OpenClaw / ESP-Claw / Dify / Flowise
- Schema migrations (no DB changes)
- Persisting audio bytes anywhere
- Stack traces in error responses
- Duplicate `VoiceCommandLog` rows for one audio request

---

## Verification Strategy

### Test Decision

- **Infrastructure exists**: YES (pytest + Hypothesis already in use)
- **Automated tests**: YES — TDD-aligned. Each task includes targeted tests.
- **Framework**: pytest (existing)
- **Build verification**: `python -m pytest -q` is the gate. New test count expected: ~25–35.

### QA Policy

- Audio validation: unit-tested via constructed `UploadFile` mocks (starlette has test utilities) + raw bytes
- Fake STT/TTS: unit-tested with deterministic inputs; assert mode/content_type/RIFF header
- Endpoint: full FastAPI `TestClient` integration with multipart payload; assert status, JSON shape, `VoiceCommandLog` row inserted
- Hermeticity (AR7): mirror AR6 — `sys.modules` diff before/after import
- Regression: existing 189 tests must continue passing unchanged

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — pure additions, all parallel):
├── Task 1: Settings + .env.example fields
├── Task 2: app/audio/ package skeleton + protocols
├── Task 3: app/utils/audio_validation.py
└── Task 4: app/schemas/audio.py

Wave 2 (Audio adapters — depend on Wave 1):
├── Task 5: app/audio/stt.py (fake STT + ConfigurationError)
├── Task 6: app/audio/tts.py (fake TTS, silent WAV via stdlib)
└── Task 7: test_audio_fake_hermeticity.py (Property AR7)

Wave 3 (Shared helper + endpoint refactor):
├── Task 8: Extract process_agent_text_command helper (NEW; do NOT yet refactor /agent/text)
├── Task 9: Try refactoring /agent/text to use helper; revert if any existing test fails
└── Task 10: POST /agent/audio endpoint + AgentAudioResponse wiring

Wave 4 (Tests for new surface area):
├── Task 11: test_audio_validation.py
├── Task 12: test_fake_stt.py
├── Task 13: test_fake_tts.py
└── Task 14: test_agent_audio_endpoint.py + full regression

Wave 5 (Manual script + docs):
├── Task 15: scripts/run_agent_audio.py
├── Task 16: docs/AUDIO_BACKEND.md
├── Task 17: docs/PHASE_10_SUMMARY.md
└── Task 18: README.md + docs/ROADMAP.md + AGENTS.md (AR7) updates

Critical Path: 1 → 2 → 5 → 8 → 10 → 14 → 18
```

### Agent Dispatch Summary

- Wave 1: Tasks 1–4 → `quick`
- Wave 2: Tasks 5–7 → `quick` (Task 7 needs special care — mirror AR6 exactly)
- Wave 3: Tasks 8–10 → `unspecified-high` (refactor risk)
- Wave 4: Tasks 11–14 → `unspecified-high` (Task 14 includes full regression)
- Wave 5: Tasks 15–18 → `writing`

---

## TODOs

- [ ] 1. Settings + `.env.example` fields

  **What to do**:
  - Add to `app/config.py` `Settings`:
    - `audio_stt_mode: str = "fake"`
    - `audio_tts_mode: str = "fake"`
    - `fake_stt_transcript: str = "catat makan siang 20000"`
    - `max_audio_upload_mb: int = 10`
    - `fake_tts_format: str = "wav"`
    - `fake_tts_sample_rate: int = 16000`
  - Append to `.env.example` with the same uppercase keys (env layer is uppercase; pydantic-settings lowercases attrs).
  - Add a brief comment block above the new settings: "Phase 10 audio settings. MAX_AUDIO_UPLOAD_MB is decimal (10 MB = 10_000_000 bytes)."

  **Must NOT do**: no provider-specific keys (`STT_API_KEY`, `OPENAI_API_KEY`, etc.).

  **Acceptance**:
  - `from app.config import settings; settings.audio_stt_mode == "fake"` works
  - `.env.example` parseable

- [ ] 2. `app/audio/` package skeleton + provider seam

  **What to do**:
  - Create `app/audio/__init__.py` (empty or `__all__ = []`)
  - Create `app/audio/_seam.py` with:
    - `class ConfigurationError(Exception)` — raised when an unsupported mode is configured
    - `class SttProvider(typing.Protocol)`: `def transcribe(self, file_bytes: bytes, filename: str, content_type: str | None) -> TranscriptionResult: ...`
    - `class TtsProvider(typing.Protocol)`: `def synthesize(self, text: str) -> SynthesisResult: ...`
    - `@dataclass class TranscriptionResult` — see prompt
    - `@dataclass class SynthesisResult` — see prompt
  - Place `TranscriptionResult` / `SynthesisResult` here so `stt.py` and `tts.py` both import from `_seam.py`.

  **Must NOT do**: no provider SDK imports anywhere in `app/audio/`.

  **References**: `app/agent/fake.py` for the hermeticity pattern.

  **Acceptance**: `python -c "from app.audio._seam import TranscriptionResult, SynthesisResult, ConfigurationError, SttProvider, TtsProvider"` works.

- [ ] 3. `app/utils/audio_validation.py`

  **What to do**:
  - Create constants `ALLOWED_EXTENSIONS = {".wav", ".mp3", ".webm", ".m4a"}` and `ALLOWED_CONTENT_TYPES = {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/webm", "audio/mp4", "audio/x-m4a", "audio/aac", "application/octet-stream"}`.
  - Create `@dataclass class AudioMetadata: filename: str; content_type: str; size_bytes: int; detected_extension: str`.
  - Create `class AudioValidationError(Exception)` with `status_code: int` attribute (400 default; 413 for size).
  - `def validate_audio(file_bytes: bytes, filename: str | None, content_type: str | None, max_mb: int) -> AudioMetadata`:
    1. `filename` non-empty and `len(filename.strip()) > 0` else `AudioValidationError("missing filename", status_code=400)`
    2. extract extension `os.path.splitext(filename)[1].lower()`; reject if not in `ALLOWED_EXTENSIONS`
    3. content_type optional; if provided, must be in `ALLOWED_CONTENT_TYPES`. If `application/octet-stream`, only accept when extension is in allowed list (already enforced by step 2).
    4. `len(file_bytes) > 0` else `AudioValidationError("empty file", 400)`
    5. `len(file_bytes) > max_mb * 1_000_000` else `AudioValidationError("oversized file", 413)` — note: decimal MB
  - Return `AudioMetadata`.

  **Must NOT do**: no audio frame decoding.

  **Acceptance**: pure function, no FastAPI imports needed; testable with raw bytes.

- [ ] 4. `app/schemas/audio.py`

  **What to do**:
  - Pydantic v2 BaseModels (mirror `app/schemas/agent.py` style):
    - `AudioMetadataOut(BaseModel)`: `filename: str`, `content_type: str`, `size_bytes: int`
    - `TranscriptionInfoOut(BaseModel)`: `text: str`, `mode: str`, `duration_ms: int | None = None`, `confidence: float | None = None`
    - `FakeTTSInfoOut(BaseModel)`: `mode: str`, `available: bool`, `content_type: str`
    - `AgentAudioResponse(AgentTextResponse)` — **inherits from `AgentTextResponse`** (composition via inheritance), adds `transcription: TranscriptionInfoOut`, `audio: AudioMetadataOut`, `tts: FakeTTSInfoOut`.
  - Import `AgentTextResponse` from `app.schemas.agent`.

  **Must NOT do**:
  - Do not redeclare `reply`, `actions`, `device_feedback` — inherited.
  - Do not name fields with provider names.

  **Acceptance**: `AgentAudioResponse(reply="x", actions=[], device_feedback=None, transcription=..., audio=..., tts=...).model_dump()` returns a dict containing all 6 fields.

- [ ] 5. `app/audio/stt.py` — fake STT

  **What to do**:
  - Import only stdlib + `app.audio._seam` + `app.config.settings`. NO provider imports.
  - `def transcribe_audio(file_bytes: bytes, filename: str, content_type: str | None = None) -> TranscriptionResult`:
    1. `if settings.audio_stt_mode != "fake": raise ConfigurationError(f"Unsupported AUDIO_STT_MODE={settings.audio_stt_mode!r}; only 'fake' supported in Phase 10")`
    2. Return `TranscriptionResult(text=settings.fake_stt_transcript, mode="fake", duration_ms=None, confidence=None, metadata={"filename": filename, "content_type": content_type, "size_bytes": len(file_bytes)})`
  - Do NOT inspect `file_bytes` content beyond `len()`.

  **Must NOT do**:
  - No `import google.cloud.speech`, `import openai`, `import whisper`, etc.
  - No network calls.
  - No `import google.adk.*`.

  **Acceptance**: deterministic — calling twice with same `(file_bytes, filename)` returns same `TranscriptionResult`.

- [ ] 6. `app/audio/tts.py` — fake TTS with silent WAV

  **What to do**:
  - Import only stdlib (`io`, `wave`, `struct`) + `app.audio._seam` + `app.config.settings`. NO provider imports.
  - Module-level helper `_silent_wav(sample_rate: int, duration_ms: int = 100) -> bytes`:
    1. Build a minimal mono 16-bit PCM silent WAV using `wave` stdlib module:
       ```python
       buf = io.BytesIO()
       with wave.open(buf, "wb") as wf:
           wf.setnchannels(1)
           wf.setsampwidth(2)
           wf.setframerate(sample_rate)
           num_frames = int(sample_rate * duration_ms / 1000)
           wf.writeframes(b"\x00\x00" * num_frames)
       return buf.getvalue()
       ```
    2. The returned bytes start with `RIFF` and contain `WAVE` at offset 8 — verifiable in tests.
  - `def synthesize_text(text: str) -> SynthesisResult`:
    1. `if settings.audio_tts_mode != "fake": raise ConfigurationError(f"Unsupported AUDIO_TTS_MODE={settings.audio_tts_mode!r}; only 'fake' supported in Phase 10")`
    2. Generate `audio_bytes = _silent_wav(settings.fake_tts_sample_rate)`
    3. Return `SynthesisResult(mode="fake", content_type="audio/wav", audio_bytes=audio_bytes, text=text, metadata={"sample_rate": settings.fake_tts_sample_rate, "format": settings.fake_tts_format})`

  **Must NOT do**:
  - No new dependency in `requirements.txt`. `wave` is stdlib.
  - No network call.
  - Do not return `audio_bytes` in API JSON response (handler strips before serializing).

  **Acceptance**:
  - `synthesize_text("hello").audio_bytes[:4] == b"RIFF"`
  - `synthesize_text("hello").audio_bytes[8:12] == b"WAVE"`

- [ ] 7. `app/tests/test_audio_fake_hermeticity.py` — Property AR7

  **What to do**:
  - **Mirror `test_agent_fake_hermeticity.py` structure exactly.**
  - `_FORBIDDEN_MODULES` tuple should include:
    - `google.cloud.speech`
    - `google.cloud.texttospeech`
    - `google.adk.runners`
    - `google.adk.agents`
    - `google.adk.sessions`
    - `openai`
    - `whisper`
    - `elevenlabs`
    - `deepgram`
    - `assemblyai`
  - `_purge_forbidden_from_sys_modules()` — drops any matching modules pre-test
  - Test 1 — module-import hermeticity:
    ```python
    def test_audio_modules_do_not_import_forbidden_sdks():
        _purge_forbidden_from_sys_modules()
        # Trigger fresh import
        import importlib
        for mod in ["app.audio.stt", "app.audio.tts", "app.audio._seam"]:
            sys.modules.pop(mod, None)
            importlib.import_module(mod)
        leaked = [m for m in _FORBIDDEN_MODULES if m in sys.modules]
        assert leaked == [], f"app.audio.* leaked forbidden modules: {leaked}"
    ```
  - Test 2 — call-time hermeticity for fake STT:
    ```python
    @given(text=st.text(min_size=1, max_size=80))
    def test_property_ar7_fake_stt_hermeticity(text):
        _purge_forbidden_from_sys_modules()
        from app.audio.stt import transcribe_audio
        transcribe_audio(file_bytes=b"\x00" * 16, filename="x.wav", content_type="audio/wav")
        leaked = [m for m in _FORBIDDEN_MODULES if m in sys.modules]
        assert leaked == []
    ```
  - Test 3 — call-time hermeticity for fake TTS, mirroring Test 2 with `synthesize_text(text)`.

  **Must NOT do**:
  - Do not use `pytest.importorskip` here — we want imports to fail loudly if a forbidden SDK is added.

  **References**: `app/tests/test_agent_fake_hermeticity.py` (verbatim style template).

  **Acceptance**: passes in current state (no forbidden modules imported by `app.audio.*`).

- [ ] 8. Extract `process_agent_text_command` shared helper (additive, NO refactor of /agent/text yet)

  **What to do**:
  - Create `app/api/_agent_helpers.py` (or add to top of `app/api/agent.py`):
    ```python
    async def process_agent_text_command(
        db: Session,
        *,
        user_id: str,
        text: str,
        device_id: str | None = None,
        timezone: str | None = None,
    ) -> AgentRunResult:
        """Shared agent invocation flow used by /agent/text and /agent/audio.

        Encapsulates: user 404, device 404 (if provided), timezone fallback,
        run_text invocation, success VoiceCommandLog write, failure
        VoiceCommandLog write + HTTPException(500). Behavior MUST mirror
        the existing /agent/text handler exactly.
        """
    ```
  - Body: copy the logic from `app/api/agent.py::post_agent_text` lines 67–141, replacing `payload.X` with the keyword args. Keep identical: 404 details, error log fallback, generic 500 detail.
  - Return the `AgentRunResult` (not the response object) so callers can build their own response shape.

  **Must NOT do**:
  - Do not modify `app/api/agent.py::post_agent_text` yet (Task 9 covers that).
  - Do not change order of operations.

  **Acceptance**: helper importable; behaves identically to inline logic when called with the same args. No tests yet — Task 9 confirms parity via existing `/agent/text` test suite.

- [ ] 9. Refactor `/agent/text` handler to use shared helper (REVERTABLE)

  **What to do**:
  - Replace the body of `post_agent_text` in `app/api/agent.py` to:
    ```python
    result = await process_agent_text_command(
        db,
        user_id=payload.user_id,
        text=payload.text,
        device_id=payload.device_id,
        timezone=payload.timezone,
    )
    return AgentTextResponse(
        reply=result.reply,
        actions=result.actions,
        device_feedback=result.device_feedback,
    )
    ```
  - Run full pytest: `python -m pytest -q app/tests/`
  - **GATE**: if ANY existing test fails OR test count drops below 189, REVERT this task. Keep helper from Task 8 but leave `post_agent_text` body unchanged. Document the revert in the plan.
  - If tests pass, commit and proceed.

  **Must NOT do**:
  - Do not weaken any test to make this pass.
  - Do not change the response model, status codes, or detail strings.

  **Acceptance**: 189 tests still pass. `git diff app/api/agent.py` shows only the body simplified — no signature, route, or import order change.

- [ ] 10. `POST /agent/audio` endpoint

  **What to do**:
  - Add `app/api/audio.py` (new router file, mirrors `app/api/agent.py` structure):
    ```python
    from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
    router = APIRouter(tags=["Agent"])

    @router.post("/agent/audio", response_model=AgentAudioResponse)
    async def post_agent_audio(
        user_id: str = Form(...),
        text: str | None = Form(None),  # not used; only present to mirror text endpoint flexibility
        device_id: str | None = Form(None),
        timezone: str | None = Form(None),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
    ) -> AgentAudioResponse:
        ...
    ```
  - Handler steps (in order):
    1. Read `file_bytes = await file.read()` once
    2. Call `validate_audio(file_bytes, file.filename, file.content_type, settings.max_audio_upload_mb)` — catch `AudioValidationError` → `HTTPException(status_code=err.status_code, detail=str(err))`
    3. Call `transcribe_audio(file_bytes, file.filename, file.content_type)` — catch generic `Exception` (NOT `ConfigurationError`) → `HTTPException(502, "Audio transcription failed")`. Let `ConfigurationError` propagate to global handler (mis-config = 500).
    4. **Important**: STT failure does NOT write `VoiceCommandLog` (per STT failure semantics)
    5. Call `process_agent_text_command(db, user_id=user_id, text=transcription.text, device_id=device_id, timezone=timezone)` — handles user 404, device 404, agent runtime errors, and VoiceCommandLog
    6. Call `synthesize_text(transcription.text)` — wrap in try/except; on failure use `tts_info = FakeTTSInfoOut(mode="fake", available=False, content_type="audio/wav")` instead of crashing
    7. Build `AgentAudioResponse`:
       - inherited fields: `reply`, `actions`, `device_feedback` from `result`
       - `transcription = TranscriptionInfoOut(...)` from `transcription`
       - `audio = AudioMetadataOut(filename=..., content_type=..., size_bytes=len(file_bytes))`
       - `tts = FakeTTSInfoOut(mode=tts_result.mode, available=True, content_type=tts_result.content_type)` — note: `audio_bytes` field is dropped, only metadata in response
  - Mount in `app/main.py`: `app.include_router(audio.router)` after the existing `agent.router`.

  **Must NOT do**:
  - Do not include `audio_bytes` in the JSON response.
  - Do not write `VoiceCommandLog` from this handler (helper does it).
  - Do not catch `HTTPException` from `process_agent_text_command` — let it bubble.
  - Do not persist `file_bytes` to disk anywhere.

  **References**:
  - `app/api/agent.py` for shape and HTTPException pattern
  - `app/main.py` for router include pattern

  **Acceptance**:
  - `curl -F file=@sample.wav -F user_id=<uuid> http://127.0.0.1:8765/agent/audio` returns 200 with documented JSON shape
  - Empty file → 400; oversized → 413; bad extension → 400
  - Unknown user → 404; unknown device (when provided) → 404

- [ ] 11. `app/tests/test_audio_validation.py`

  **What to do**:
  - Pure-function tests on `validate_audio`. No FastAPI client needed.
  - Cases:
    - accept `.wav`, `.mp3`, `.webm`, `.m4a` (parametrize)
    - accept content types: `audio/wav`, `audio/x-wav`, `audio/mpeg`, `audio/mp3`, `audio/webm`, `audio/mp4`, `audio/x-m4a`, `audio/aac`, `application/octet-stream` (with allowed ext)
    - reject extension `.txt`, `.exe`, `.flac` → `AudioValidationError`, `status_code == 400`
    - reject content type `text/plain` → 400
    - reject empty bytes (`b""`) → 400
    - reject oversized (`b"x" * (10_000_001)` with `max_mb=10`) → 413
    - reject missing filename (`None`, `""`, `"   "`) → 400
    - returned `AudioMetadata.size_bytes == len(file_bytes)`
  - Use `pytest.mark.parametrize` for the accept cases.

  **Acceptance**: ≥10 test cases pass.

- [ ] 12. `app/tests/test_fake_stt.py`

  **What to do**:
  - Cases:
    - `transcribe_audio(b"\x00", "x.wav")` returns `TranscriptionResult` with `mode == "fake"`, `text == settings.fake_stt_transcript`
    - Override via monkeypatch: `monkeypatch.setattr(settings, "fake_stt_transcript", "halo dunia")`; assert returned `text == "halo dunia"`
    - Determinism: two calls with same args return equal `TranscriptionResult`
    - `monkeypatch.setattr(settings, "audio_stt_mode", "real")` → `pytest.raises(ConfigurationError)`
    - `monkeypatch.setattr(settings, "audio_stt_mode", "openai")` → `pytest.raises(ConfigurationError)` with message containing the bad mode value
  - The autouse network kill-switch from `conftest.py` already enforces "no network" — no extra mock needed.

  **Acceptance**: 5+ tests pass.

- [ ] 13. `app/tests/test_fake_tts.py`

  **What to do**:
  - Cases:
    - `synthesize_text("halo")` returns `SynthesisResult` with `mode == "fake"`, `content_type == "audio/wav"`
    - `result.audio_bytes` starts with `b"RIFF"` and contains `b"WAVE"` at offset 8
    - `result.audio_bytes` parseable by stdlib `wave.open(io.BytesIO(...), "rb")` — assert `getframerate() == settings.fake_tts_sample_rate`
    - Determinism: two calls return equal bytes
    - `monkeypatch.setattr(settings, "audio_tts_mode", "elevenlabs")` → `pytest.raises(ConfigurationError)`

  **Acceptance**: 5+ tests pass.

- [ ] 14. `app/tests/test_agent_audio_endpoint.py` + full regression

  **What to do**:
  - Use FastAPI `TestClient` (same as `test_agent_text_endpoint.py`).
  - Setup: seed a user + device in the in-memory DB via existing fixtures.
  - Cases:
    - **Happy path**: `client.post("/agent/audio", data={"user_id": user.id, "device_id": device.id}, files={"file": ("x.wav", b"RIFFxxxxWAVExxxx", "audio/wav")})` → 200; assert response includes `transcription.text == FAKE_STT_TRANSCRIPT`, `transcription.mode == "fake"`, `reply` non-empty, `device_feedback` present (or null), `audio.filename == "x.wav"`, `tts.mode == "fake"`, `tts.available is True`.
    - `VoiceCommandLog` row created with `input_text == FAKE_STT_TRANSCRIPT`, `status == "success"`. Query DB to verify.
    - Only ONE log row created per request.
    - Unknown `user_id` → 404, no log row, no agent invocation.
    - Unknown `device_id` (when supplied) → 404, no log row.
    - Empty file → 400.
    - Unsupported extension `.txt` → 400.
    - Oversized file (use `max_audio_upload_mb=1` via monkeypatch + 1.5MB body) → 413.
    - Missing filename → 400.
    - Inherited fields type-match: response has `reply: str`, `actions: list`, `device_feedback: dict | None`.
  - **Final regression**: run `python -m pytest -q` and assert exit 0 with `(189 + N_new) passed`.

  **Acceptance**: 10+ endpoint tests pass; full regression green.

- [ ] 15. `scripts/run_agent_audio.py`

  **What to do**:
  - Mirror structure of `scripts/run_agent_text.py` exactly:
    - argparse: positional `audio_path`, optional `--user-id`, `--device-id`
    - env fallbacks: `TASKBOT_USER_ID`, `TASKBOT_DEVICE_ID`
    - imports: `from app.db import SessionLocal`, `from app.utils.audio_validation import validate_audio`, `from app.audio.stt import transcribe_audio`, `from app.audio.tts import synthesize_text`, `from app.api._agent_helpers import process_agent_text_command`, `from app.config import settings`, `from app.schemas.audio import AgentAudioResponse, AudioMetadataOut, TranscriptionInfoOut, FakeTTSInfoOut`
    - flow:
      1. Parse args; resolve user_id/device_id (CLI > env > error to stderr exit 2)
      2. `pathlib.Path(audio_path).read_bytes()` → exit 2 with stderr if not found
      3. Detect content_type via `mimetypes.guess_type(audio_path)`
      4. `validate_audio(...)` → on `AudioValidationError` print to stderr, exit 1
      5. `transcribe_audio(file_bytes, filename, content_type)`
      6. Open DB session, call `await process_agent_text_command(...)` — wrap in `asyncio.run`
      7. `synthesize_text(transcription.text)` for tts metadata (drop bytes)
      8. Build `AgentAudioResponse`, print `response.model_dump_json(indent=2)` to stdout
    - exit 0 on success, non-zero on any failure
  - In-process call only; do NOT use `httpx`/`requests`/uvicorn.

  **Must NOT do**:
  - No HTTP client.
  - No network call.
  - No saving file_bytes anywhere.

  **References**: `scripts/run_agent_text.py` is the canonical template.

  **Acceptance**: `python -m scripts.run_agent_audio sample.wav` (after seeding) prints valid JSON, exits 0.

- [ ] 16. `docs/AUDIO_BACKEND.md`

  **What to do**:
  - Sections (English):
    1. **Overview** — Phase 10 is fake/hermetic only. Provider selection deferred. Why: ESP32 firmware not yet ready; product wants the backend audio path testable end-to-end without provider lock-in.
    2. **Endpoint** — `POST /agent/audio` request shape (multipart fields), response shape (full JSON example), status codes table.
    3. **Settings** — table of env vars with defaults and meaning. Note: `MAX_AUDIO_UPLOAD_MB` is decimal (10 MB = 10_000_000 bytes).
    4. **Fake STT** — what it returns; how to override `FAKE_STT_TRANSCRIPT`; why we don't inspect audio content.
    5. **Fake TTS** — silent WAV via stdlib `wave`; only metadata in JSON response; binary fetch endpoint deferred to Phase 11.
    6. **Audio retention** — explicit: bytes never persisted; only transcript text in `VoiceCommandLog`.
    7. **Manual testing** — CLI script + curl example.
    8. **Running tests** — `python -m pytest -q app/tests/test_audio_*.py -v`.
    9. **Alternative architecture (informational)** — Google ADK Live Audio API replaces STT→text→TTS pipeline with bidirectional audio agent. Out of scope for Phase 10. Mention so future architects know the choice exists.
    10. **Limitations** — bullet list verbatim from prompt.
    11. **Adding a real provider (future-phase guide)** — implement `SttProvider`/`TtsProvider` from `app.audio._seam`; add new mode value (e.g. `"google"`); flip dispatch in `transcribe_audio`/`synthesize_text`; add provider settings; AR7 hermeticity stays for fake mode.

  **Acceptance**: file exists, is valid markdown, covers all 11 sections.

- [ ] 17. `docs/PHASE_10_SUMMARY.md`

  **What to do**:
  - Mirror structure of `docs/PHASE_9_SUMMARY.md`:
    - Status (shipped, test count, hermetic-by-design)
    - What shipped (frontend not touched; backend audio package; new endpoint; tests)
    - Files added (list)
    - Files modified (list with one-line "why")
    - Files explicitly NOT changed (frontend/, requirements.txt, schema)
    - How to run end-to-end
    - Verification gates (commands + expected output)
    - Known issues encountered & resolved (whatever surfaces during implementation)
    - Intentionally NOT in Phase 10 (verbatim from prompt's non-goals)
    - Caveats (provider deferred, ADK Live Audio alternative, retention policy)
    - Recommended next phase: Phase 10.5 (real STT/TTS provider) OR Phase 11 (ESP audio integration). Mention ADK Live Audio API as a re-architect option.

  **Acceptance**: file exists, accurate to actual implementation (not pre-planned aspirations).

- [ ] 18. Update `README.md`, `docs/ROADMAP.md`, `AGENTS.md` (Property AR7), `.env.example`

  **What to do**:
  - **`README.md`** — surgical edit: bump current phase line to "Phase 10 (Audio Backend Foundation)"; add a short "Audio Backend (Phase 10)" section with `POST /agent/audio` curl example and pointer to `docs/AUDIO_BACKEND.md`.
  - **`docs/ROADMAP.md`** — surgical edit: mark Phase 10 as `(Current)` (or shipped, depending on commit timing); update Phase 11 description from "ESP Prototype" to clarify audio integration depends on Phase 10.5 (real provider) first.
  - **`AGENTS.md`** — Hard Rules section: add Property AR7 verbatim:
    ```
    8. **Audio module hermeticity (AR7).** `app/audio/stt.py` and `app/audio/tts.py` MUST NOT import any provider SDK (google.cloud.speech, google.cloud.texttospeech, openai, whisper, elevenlabs, deepgram, assemblyai) and MUST NOT import google.adk.*. Property is enforced by `test_audio_fake_hermeticity.py`.
    ```
    Also append to "Where the canonical decisions live" list:
    - `docs/AUDIO_BACKEND.md` — audio backend runbook (Phase 10).
  - **`.env.example`** — add Phase 10 audio settings block (already covered in Task 1; verify here).

  **Acceptance**: all four files updated; `findstr /R "AR7" AGENTS.md` returns at least one match.

---

## Final Verification Wave

- [ ] F1. **Plan compliance audit** — every Must Have present, every Must NOT Have absent. Grep `app/audio/` and `app/tests/` for forbidden imports (`google.cloud.speech`, `google.cloud.texttospeech`, `openai`, `whisper`, `elevenlabs`, `deepgram`, `assemblyai`).
- [ ] F2. **Backend regression** — `python -m pytest -q` reports `(189 + N_new) passed`, where `N_new` is the count from Wave 4. Zero failures, zero errors, zero skipped.
- [ ] F3. **Hermeticity proof** — `test_audio_fake_hermeticity.py` passes; `requirements.txt` diff is empty for Phase 10.
- [ ] F4. **Manual smoke** — `python -m scripts.run_agent_audio <any-wav>` prints valid `AgentAudioResponse` JSON; `curl -F file=@sample.wav ...` returns 200 with documented shape.

## Commit Strategy

One commit per wave for reviewability:

- `phase-10: settings + audio package skeleton + audio_validation + audio schemas`
- `phase-10: fake STT + fake TTS + AR7 hermeticity test`
- `phase-10: shared agent helper + POST /agent/audio endpoint`
- `phase-10: tests for validation/stt/tts/endpoint + full regression`
- `phase-10: manual script + audio docs + README/ROADMAP/AGENTS updates`

## Success Criteria

### Verification Commands

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
# Expected: (189 + new) passed

findstr /R /S "google.cloud.speech google.cloud.texttospeech openai whisper elevenlabs deepgram assemblyai" app
# Expected: no matches

git diff --stat -- requirements.txt
# Expected: empty (no Python deps added)
```

### Final Checklist

- [ ] All 18 tasks complete
- [ ] All tests pass
- [ ] No new Python dependency added
- [ ] No real provider code committed
- [ ] AR7 enforced by automated test
- [ ] /agent/text behavior unchanged
- [ ] Docs explain hermetic-by-design rationale

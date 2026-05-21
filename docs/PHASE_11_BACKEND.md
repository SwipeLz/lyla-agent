# Phase 11 — Backend Architecture (FastAPI)

> **HISTORICAL — work described below is SHIPPED.** Phase 11a (real Gemini
> STT/TTS) and Phase 11b (TTS cache, directive classifier, `X-Lyla-Protocol`
> header, `AgentInvocation`) are complete. See `docs/ROADMAP.md` for the
> shipped status and `docs/PHASE_12_SUMMARY.md` for what landed on top.
> The current source of truth for ESP integration is
> [`ESP32_INTEGRATION_CONTRACT.md`](ESP32_INTEGRATION_CONTRACT.md).
> This document is preserved for the design rationale, layer-placement
> rules, and failure-semantics tables that remain valid.

This document specifies what the **FastAPI backend** must build for ESP32 voice integration. Read [`PHASE_11_ARCHITECTURE.md`](PHASE_11_ARCHITECTURE.md) first for the contract; this file is the implementation guide.

## What's already built (Phase 10)

The Phase 10 audio plumbing is **production-ready** for the ESP path:

- `app/audio/_seam.py` — `TranscriptionResult`, `SynthesisResult`, `ConfigurationError`, `SttProvider`/`TtsProvider` Protocols
- `app/audio/stt.py` — fake STT, returns canned transcript
- `app/audio/tts.py` — fake TTS, silent WAV
- `app/utils/audio_validation.py` — multipart validator (size, ext, mime, filename)
- `app/api/audio.py` — `POST /agent/audio` endpoint, calls validator → STT → agent helper → TTS → directive classifier
- `app/api/_audio_directive.py` — server-side classifier, maps `actions` → `audio_code` + `face` + `screen_text`
- `app/schemas/audio.py` — `AgentAudioResponse` extends `AgentTextResponse` with transcription/audio/tts/**directive**
- `AGENTS.md` Property AR7 — hermeticity rule for `app/audio/*`
- 41 audio tests + 11 directive tests, all passing

What's left for Phase 11 = swap fake providers for real ones + add the binary TTS fetch endpoint.

## Tasks for Phase 11

### Task B1 — Real STT via Gemini multimodal

**File:** new `app/audio/stt_gemini.py`

Implement `SttProvider` Protocol from `_seam.py`. Pattern: deferred import (mirror `app/agent/runtime.py::_run_real`) so AR7 stays intact in fake mode.

```python
# Sketch (do not commit yet)
from app.audio._seam import TranscriptionResult, SttProvider

class GeminiSttProvider:
    def __init__(self, model: str, api_key: str):
        self._model = model
        self._api_key = api_key

    def transcribe(self, file_bytes, filename, content_type):
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self._model,
            contents=[
                "Transcribe the audio in Indonesian. Output ONLY the transcript text, no commentary.",
                types.Part.from_bytes(data=file_bytes, mime_type=content_type or "audio/wav"),
            ],
        )
        return TranscriptionResult(
            text=(response.text or "").strip(),
            mode="gemini",
            duration_ms=None,
            confidence=None,
            metadata={"model": self._model},
        )
```

Wire into `app/audio/stt.py`:

```python
def transcribe_audio(file_bytes, filename, content_type=None):
    mode = settings.audio_stt_mode
    if mode == "fake":
        return _fake_transcribe(...)
    if mode == "gemini":
        return _gemini_provider().transcribe(file_bytes, filename, content_type)
    raise ConfigurationError(f"Unsupported AUDIO_STT_MODE={mode!r}")
```

`_gemini_provider()` is a module-level lazy singleton that builds a `GeminiSttProvider(settings.google_adk_model_audio, settings.google_api_key)` on first call.

### Task B2 — Real TTS via Gemini

**File:** new `app/audio/tts_gemini.py`

Same pattern. Output PCM 24kHz mono → wrap in WAV header before returning.

```python
def synthesize(self, text):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=self._api_key)
    response = client.models.generate_content(
        model=self._model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._voice),
                ),
            ),
        ),
    )
    pcm = response.candidates[0].content.parts[0].inline_data.data
    wav_bytes = _wrap_pcm_to_wav(pcm, rate=24000)
    return SynthesisResult(
        mode="gemini",
        content_type="audio/wav",
        audio_bytes=wav_bytes,
        text=text,
        metadata={"voice": self._voice, "model": self._model},
    )
```

### Task B3 — New settings

Add to `app/config.py`:

```python
audio_stt_provider_model: str = "gemini-3-flash-preview"
audio_tts_provider_model: str = "gemini-3.1-flash-tts-preview"
audio_tts_voice: str = "Leda"
tts_cache_ttl_seconds: int = 300
```

Add to `.env.example` with sensible defaults; comment that switching `AUDIO_STT_MODE=gemini` and `AUDIO_TTS_MODE=gemini` activates real providers.

### Task B4 — TTS cache + binary fetch endpoint

**Why:** `directive.audio_code = "fallback_tts"` must give ESP a `fetch_url`. Sending audio bytes inline in JSON is bad (base64 bloat 33%, blocks until TTS done).

**Where:** new `app/audio/tts_cache.py` — in-process LRU keyed by `voice_command_log_id`, TTL from settings.

```python
from cachetools import TTLCache

class TtsCache:
    def __init__(self, maxsize: int, ttl: int):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)

    def put(self, log_id: str, audio_bytes: bytes, content_type: str): ...
    def get(self, log_id: str) -> tuple[bytes, str] | None: ...
```

**Endpoint:** new file `app/api/audio_tts.py`

```python
@router.get("/agent/audio/{log_id}/tts")
async def get_tts_audio(log_id: str, db: Session = Depends(get_db)):
    entry = tts_cache.get(log_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="TTS not available or expired")
    audio_bytes, content_type = entry
    return Response(content=audio_bytes, media_type=content_type)
```

Mount in `app/main.py` after `audio.router`.

### Task B5 — Hook TTS cache + fetch_url into the audio handler

In `app/api/audio.py`:

1. After `process_agent_text_command` returns, check the directive's `audio_code`.
2. If `fallback_tts` and `settings.audio_tts_mode != "fake"`: synthesize TTS, get the persisted `VoiceCommandLog.id` from the helper, store TTS bytes in cache keyed by that id, set `directive.fetch_url = f"/agent/audio/{log_id}/tts"`.
3. If success path: skip TTS synthesis entirely (ESP plays from SD).

This requires `process_agent_text_command` to return the log row id along with the `AgentRunResult`. Either:

- (a) extend the helper return type to a dataclass `(result, log_id)`, OR
- (b) re-query the latest log row by `(user_id, created_at)` after the helper returns.

Option (a) is cleaner; the existing helper writes the log via `log_service.create_voice_command_log` which already returns the row. Plumb the id back.

### Task B6 — Stream Gemini TTS chunks (optional but valuable)

Gemini TTS supports `generate_content_stream`. Saving the entire WAV before streaming to ESP costs 6 seconds idle; streaming lets ESP start playback after the first chunk (~1-2 seconds).

Two ways:

- (a) `StreamingResponse` from `/agent/audio/{log_id}/tts` that writes PCM chunks as they arrive from Gemini, prepends WAV header with content-length=0xFFFFFFFF (some players choke on this).
- (b) Synthesize fully, then stream from cache (no latency benefit, simpler).

Pick (b) for v1. Leave a comment in `tts_cache.py` flagging (a) as future work.

### Task B7 — Protocol version header

Add to every `/agent/audio` response:

```python
response.headers["X-Lyla-Protocol"] = "1"
```

Use FastAPI middleware or `Response(headers=...)` — middleware is cleaner.

### Task B8 — Tests

| File | What |
|---|---|
| `app/tests/test_gemini_stt_smoke.py` | mark as `@pytest.mark.requires_api_key`; skip when `GOOGLE_API_KEY` empty; verify mode==`"gemini"` and non-empty transcript |
| `app/tests/test_gemini_tts_smoke.py` | same skip; verify WAV header + `audio_bytes` non-empty |
| `app/tests/test_tts_cache.py` | unit tests for LRU + TTL |
| `app/tests/test_audio_tts_endpoint.py` | unit test for `GET /agent/audio/{log_id}/tts`: hit, miss, expired |
| `app/tests/test_audio_endpoint_protocol_header.py` | assert `X-Lyla-Protocol: 1` on all `/agent/audio` responses |

Existing AR7 hermeticity test stays. Real-provider modules (`stt_gemini.py`, `tts_gemini.py`) are NOT covered by AR7 because they legitimately import provider SDK; AR7 covers only `_seam.py`/`stt.py`/`tts.py` (the dispatcher facades). The deferred-import pattern keeps the SDK out of `sys.modules` until the real path executes.

### Task B9 — Documentation updates

- `docs/AUDIO_BACKEND.md` — switch the "Adding a real provider" section from speculative to actual instructions matching the new files.
- `docs/PHASE_11_SUMMARY.md` — add when this phase ships.
- `AGENTS.md` — extend AR7 wording: "Real provider modules (`stt_gemini.py`, `tts_gemini.py`) MAY import provider SDK but only via deferred imports inside method bodies; module-level imports of `google.cloud.*` / `google.genai.*` / etc. remain forbidden in `_seam.py`, `stt.py`, `tts.py`."
- `docs/ROADMAP.md` — Phase 11 marked current.

## Layer placement (mandatory)

```
app/audio/
├── _seam.py             # types + Protocols (no SDK)
├── stt.py               # dispatcher: fake | gemini (no top-level SDK import)
├── stt_gemini.py        # real Gemini STT (deferred SDK import inside methods)
├── tts.py               # dispatcher: fake | gemini (no top-level SDK import)
├── tts_gemini.py        # real Gemini TTS (deferred SDK import inside methods)
└── tts_cache.py         # in-process TTS bytes cache (stdlib + cachetools only)

app/api/
├── audio.py             # POST /agent/audio (existing, extend with TTS cache write)
├── audio_tts.py         # NEW: GET /agent/audio/{log_id}/tts (binary fetch)
├── _agent_helpers.py    # existing helper; extend return type to include log_id
└── _audio_directive.py  # existing classifier (no change)
```

`app/services/` is **not** touched in this phase. Audio is an infrastructure adapter, not domain logic.

## Failure semantics (must implement)

| Failure | HTTP status | Server side effect | Response body |
|---|---|---|---|
| Audio validation rejects | 400 / 413 | none | `{"detail": "..."}` |
| STT raises (provider down) | 502 | none | `{"detail": "Audio transcription failed"}` |
| Gemini API key missing while `AUDIO_STT_MODE=gemini` | 500 (`ConfigurationError`) | none | generic |
| Agent runtime raises | 500 | log row written with `status="error"`, `input_text=transcript` | `{"detail": "Agent runtime error"}` |
| TTS raises after agent succeeds | 200 (main response) | `tts.available=false`, `directive.fetch_url=null`, `directive.audio_code` overridden to `err_generic` | per schema |
| `GET /agent/audio/{log_id}/tts` cache miss / expired | 404 | none | `{"detail": "TTS not available or expired"}` |

## Network hermeticity in tests

Existing autouse fixture `_no_outbound_network` in `app/tests/conftest.py` patches sockets. New real-provider tests MUST opt out via explicit `monkeypatch` allowing only `generativelanguage.googleapis.com` and require `GOOGLE_API_KEY` env. Otherwise skip.

```python
@pytest.fixture
def _allow_gemini_egress(monkeypatch):
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set; skipping real-Gemini smoke test")
    # restore original socket module attributes locally
    ...
```

## Migration guide for B5 helper change

Current helper signature:

```python
async def process_agent_text_command(db, *, user_id, text, device_id, timezone) -> AgentRunResult:
```

Target:

```python
@dataclass
class AgentInvocation:
    result: AgentRunResult
    log_id: str

async def process_agent_text_command(db, *, ...) -> AgentInvocation:
```

This is a **breaking** change for callers. There is exactly one caller (`app/api/audio.py`); update in the same commit. `/agent/text` is NOT a caller (it duplicates the logic inline by design — see `app/api/agent.py` module docstring).

## Performance targets

| Metric | Target | Phase 10 baseline |
|---|---|---|
| STT (Gemini multimodal) | <3s | n/a (fake) |
| Agent (Gemini text) | <2s | <2s real Gemini |
| TTS (Gemini, 1 sentence) | <6s | n/a (fake) |
| Total when audio_code != fallback_tts | <5s | <2s real Gemini |
| Total when audio_code == fallback_tts | <11s | n/a |
| `/agent/audio/{log_id}/tts` cache hit | <50ms | n/a |

## Out of scope for backend Phase 11

- Streaming TTS — Task B6 picks the simple path.
- TTS audio persistence — in-memory cache only.
- Per-user TTS rate limiting.
- Audio transcoding (we accept whatever ESP sends).
- Wake-word.
- WebSocket audio.

## Configuration table

```
# Existing (Phase 10)
AUDIO_STT_MODE=gemini          # was "fake"
AUDIO_TTS_MODE=gemini          # was "fake"
FAKE_STT_TRANSCRIPT=...        # ignored when mode != fake
MAX_AUDIO_UPLOAD_MB=10
FAKE_TTS_FORMAT=wav
FAKE_TTS_SAMPLE_RATE=16000

# New (Phase 11)
AUDIO_STT_PROVIDER_MODEL=gemini-3-flash-preview
AUDIO_TTS_PROVIDER_MODEL=gemini-3.1-flash-tts-preview
AUDIO_TTS_VOICE=Leda
TTS_CACHE_TTL_SECONDS=300
```

`GOOGLE_API_KEY` reuses the same key from Phase 4–10. No new credential.

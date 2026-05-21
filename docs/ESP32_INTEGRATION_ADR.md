# ESP32-S3 Integration — Architecture Decision Records

**Status:** companion to `docs/ESP32_INTEGRATION_CONTRACT.md`.
**Purpose:** record every ambiguity that existed across Phase 11 / Phase
12 documentation and explain how each was resolved in the Contract.
Read this when a Contract decision surprises you.

**Format:** each ADR has Context, Decision, Consequences, Alternatives.

**Verified against backend:** commit `afbdb7b`. If a future code change
invalidates an ADR, append a "Superseded by ADR-N" note rather than
rewriting history.

---

## ADR-1 — `base_url` is opaque; firmware honors HTTP and HTTPS

### Context

Pre-existing docs disagreed:
- `PHASE_11_FIRMWARE.md` §Provisioning shows
  `"base_url": "http://192.168.1.10:8765"` (LAN HTTP).
- `phase-12/ESP_BRIEF.md` prose says "URL pakai `https://`" (public
  HTTPS) but its sample JSON keeps the LAN HTTP example.
- `phase-12/BACKEND_BRIEF.md` says TLS termination is **external**
  (tunnel / reverse proxy) and the FastAPI app stays HTTP.

User goal is AWS deployment, so production will be HTTPS. But local
dev and integration testing benefit from plain HTTP.

### Decision

The firmware MUST treat `base_url` as opaque. It selects the transport
client purely from the URL scheme:
- `http://...` → `WiFiClient`
- `https://...` → `WiFiClientSecure` with `setInsecure()` (MVP)

There is no compile-time URL. Every network target is read from
`/sd/config.json`.

### Consequences

- One firmware binary works against `localhost:8765`, LAN dev, AWS
  staging, AWS production unchanged.
- Operators switch environments by re-pairing and rewriting the SD
  card. No firmware reflash needed.
- The `base_url` field MUST start with a scheme; bare hostnames are
  rejected at boot validation (§2.3 of Contract).

### Alternatives considered

- **Compile-time `BASE_URL` macro.** Rejected: forces reflash for every
  environment change; brittle for AWS where URLs differ between staging
  and production.
- **Always HTTPS.** Rejected: blocks LAN integration testing without a
  TLS-terminating proxy in dev.

---

## ADR-2 — Multipart upload uses Option A (PSRAM blob), not streaming

### Context

`PHASE_11_FIRMWARE.md` §HTTP upload pattern offered two options:
- **Option A**: build entire multipart body in PSRAM, then `http.POST(body)`.
- **Option B**: streaming Stream class that emits boundaries on demand.

Phase 12 added TLS, which adds ~32 KB of handshake buffers. Concern:
does Option A still fit in 8 MB PSRAM with TLS overhead?

### Decision

Use **Option A** for v1. Build the multipart body in PSRAM and POST in
one shot.

Memory peak (worst case, 30 s recording):
- Audio capture buffer: 960 KB
- Multipart body (preamble + WAV header + audio + trailer): ~ 962 KB
- TLS handshake: ~ 32 KB
- Application + libraries: ~ 100 KB
- Total: ~ 2.0 MB

Fits comfortably in 8 MB PSRAM. Headroom for FreeRTOS stacks and
ArduinoJson is ~ 6 MB.

The audio capture buffer is reused as the multipart body backing store
when possible (no double-allocation).

### Consequences

- Simple firmware code: one `ps_malloc`, one `http.POST(body, len)`.
- Latency penalty: must finish recording before send starts. Acceptable
  because filler audio (`ack_thinking.wav`) masks the gap.
- The 30 s record cap is a hard cap (firmware enforces, server tolerates
  larger but rejects > 10 MB).

### Alternatives considered

- **Option B (custom Stream).** Rejected for v1: more code, harder to
  debug, marginal memory savings on a board that has 8 MB PSRAM.
- **chunked transfer encoding.** Rejected: Arduino-ESP32 `HTTPClient`
  doesn't expose chunked POST cleanly.

---

## ADR-3 — WiFi drop mid-request: abort, don't resume

### Context

Phase 11 docs mention WiFi reconnect with backoff but don't specify
behavior when WiFi drops during `[SENDING]` or `[PLAYING_RESPONSE]`.
Resuming a partial multipart upload is non-trivial; resuming an
interrupted TTS stream is worse.

### Decision

Voice commands are **atomic**. If WiFi drops mid-request:
1. Abort the in-flight HTTP call within 5 s (firmware-level timeout
   shorter than the 30 s socket timeout).
2. Stop I2S DMA cleanly.
3. Show `Tidak bisa hubungi server` (OLED) and `err_generic.wav`.
4. Return to `[IDLE]`.

The user re-records on next button press. No state is preserved across
WiFi drops.

### Consequences

- Simpler firmware: no resumption logic, no offline queue.
- Worst case the user repeats a command. Acceptable for MVP.
- The backend may see a `VoiceCommandLog` row with partial metadata if
  the abort happens after multipart parsing started; current Phase 12
  behavior writes the row only after STT succeeds, so partial uploads
  don't pollute logs in practice.

### Alternatives considered

- **Offline queue on SD card.** Rejected: significant complexity,
  privacy concerns (recordings persist), no operator UX win.
- **Auto-retry once.** Rejected: duplicates side effects (e.g.
  `create_task` running twice if the first request did succeed but the
  response was lost on the wire).

---


## ADR-4 — Heartbeat is a FreeRTOS task; pauses during active states

### Context

Phase 12 brief said "pause heartbeat during recording/playback" but did
not specify the concurrency model. Options:
- Timer in main loop: simple but couples heartbeat to loop frequency.
- FreeRTOS timer: clean separation, but requires careful state-flag
  sharing.
- Dedicated FreeRTOS task: most flexible, easiest to reason about.

### Decision

The heartbeat runs as a **FreeRTOS software timer** firing every 60 s.
The timer callback checks a shared atomic state variable
(`current_state`) and skips the heartbeat when state is anything other
than `[IDLE]`.

When the firmware re-enters `[IDLE]` after a request, the next
heartbeat fires on the regular 60 s tick — no immediate "catch-up"
heartbeat.

After WiFi reconnect, the firmware MUST trigger one immediate heartbeat
(out-of-band) so the dashboard sees the device come back online without
waiting up to 60 s.

### Consequences

- No heartbeat ever preempts an active request.
- The dashboard sees a heartbeat gap during long playback (up to ~12 s
  for `fallback_tts`). Acceptable: device is still considered online
  by the 60 s online threshold.
- Three FreeRTOS tasks total: main, I2S input, I2S output (heartbeat
  uses a software timer, no dedicated task stack).

### Alternatives considered

- **Heartbeat task with priority lower than I2S.** Equivalent
  correctness, more memory overhead (extra task stack).
- **Inline in main loop.** Rejected: hard to guarantee 60 s cadence
  when main loop is busy with HTTP I/O.

---

## ADR-5 — OLED face pixmaps are pre-baked XBM in firmware; not on SD

### Context

Phase 11 docs said "pre-bake face pixmaps as XBM arrays in firmware"
but did not specify tooling, source format, or rationale.

### Decision

Face pixmaps are stored as `const uint8_t [] PROGMEM` XBM arrays in
firmware source. The 4 frozen faces are:

- `face_happy_xbm`
- `face_sad_xbm`
- `face_thinking_xbm` (or animation frames)
- `face_neutral_xbm`

Each pixmap is 128 × 64 monochrome (1024 bytes). Total: 4 KB in flash.

The "thinking" face is animated as a sequence of 3-4 frames cycled at
~ 200 ms (dots animation). This is rendered by the I2C OLED driver
(U8g2 recommended); animation logic lives in the firmware, not on SD.

### Consequences

- Faces are fixed at compile time. Updating requires firmware reflash.
- No I/O cost to render (PROGMEM read is fast).
- Operator workflow: design in any vector tool, export as 128×64 PNG,
  convert with convert image.png image.xbm (ImageMagick) or any
  PNG-to-XBM tool, paste the byte array into firmware source.

### Alternatives considered

- **Faces on SD card as PBM/BMP.** Rejected: extra I/O cost on every
  state transition; SD card swap risk (operator could install a card
  without faces).
- **Procedural drawing (lines/circles).** Rejected: harder to design,
  less expressive.

---

## ADR-6 — TTS playback is buffer-then-play, not streaming

### Context

allback_tts audio is fetched from the backend after the JSON
response. Two playback strategies:

- **Buffer-then-play**: download whole WAV, then start I2S. Latency =
  full TTS time + transfer time (~ 6-12 s for typical replies).
- **Stream-while-playing**: start I2S after first ~ 8 KB, fill as bytes
  arrive. Latency = first-byte time (~ 1-2 s) but vulnerable to WiFi
  jitter (audio underrun = clicky/glitchy playback).

### Decision

Use **buffer-then-play** for v1. Filler audio (ck_still_thinking.wav)
masks the latency.

### Consequences

- Memory: 12 s WAV at 24 kHz mono 16-bit = 576 KB in PSRAM, allocated
  after the audio capture buffer is freed.
- Worst-case end-to-end latency on dynamic answers: ~ 12 s. The user
  hears continuous filler so it does not feel like silence.
- WiFi jitter has no effect on playback quality.

### Alternatives considered

- **Stream-while-playing.** Deferred to a later phase. The Contract
  documents this as future work; `app/api/audio_tts.py` already
  returns the full body so the server side is compatible.

---

## ADR-7 — Library version pins; lib_deps spec deferred

### Context

User explicitly asked to skip PlatformIO setup. But concrete library
versions matter for reproducibility — without pins, two firmware
authors building the same source code can get different runtime
behavior.

### Decision

The Contract names libraries by canonical identity but does NOT pin
versions today. When PlatformIO setup begins, pins go into a future
`firmware/platformio.ini` and a follow-up ADR-7-supersession.

Identified libraries (informational, no version yet):

- `WiFi` and `WiFiClientSecure` — Arduino-ESP32 v3.x built-in
- `HTTPClient` — Arduino-ESP32 v3.x built-in
- `ArduinoJson` v7 (binary-incompatible with v6; the Contract code
  shape requires v7 `JsonDocument`)
- `U8g2` for OLED rendering (preferred over Adafruit_SSD1306 because
  better fonts and lower memory footprint)
- `SD` — Arduino-ESP32 built-in
- I2S audio: use ESP-IDF I2S driver via Arduino-ESP32 wrappers; avoid
  external libraries that add layers (e.g. older `ESP32-audioI2S`
  which has had Arduino-ESP32 v3 compat issues).

### Consequences

- Firmware author still has flexibility on minor versions.
- Reproducibility risk until ADR-7 is superseded by a pin list.
- The Contract works against any reasonable version of the listed
  libraries. The firmware author records the actual versions used in
  the future `firmware/PIN_LIST.md`.

### Alternatives considered

- **Pin everything now.** Rejected by user: PlatformIO setup is
  out of scope for this round.

---


## ADR-8 — Memory budget published; firmware MUST NOT hold dual buffers

### Context

Phase 11 docs included individual memory numbers but no consolidated
table that combined audio buffer + TLS handshake + multipart preamble +
JsonDocument + OLED frame buffer + WAV header builder. This made it
hard to verify the firmware would fit on an 8 MB PSRAM board.

### Decision

The Contract publishes a memory budget table (§14.1) that sums every
known allocation and reserves a 100 KB free heap floor. The hard rule:
firmware MUST NOT hold the audio capture buffer and the TTS playback
buffer simultaneously.

The capture buffer is freed before issuing the TTS GET request. This
keeps PSRAM peak below 1.6 MB.

### Consequences

- Firmware author has a clear budget to verify against during
  development.
- Future allocations (e.g. wake-word ring buffer, OTA staging) MUST
  amend §14.1.
- The "free before allocate" rule is testable by instrumenting
  `ESP.getFreePsram()` at state transitions.

### Alternatives considered

- **Static allocation of both buffers.** Rejected: pushes peak past
  1.5 MB unnecessarily on a board where dynamic allocation works fine.

---

## ADR-9 — Firmware unit-test framework deferred; logical contracts only

### Context

Phase 11 docs suggested "unit-test the audio_code dispatcher" without
specifying framework (Unity vs GoogleTest vs PlatformIO native env).
User has not started PlatformIO setup.

### Decision

Defer firmware unit-test framework choice to the PlatformIO setup
phase. The Contract specifies **logical** test points the firmware
author MUST cover (regardless of framework):

1. Config parser: valid JSON, missing field, bad scheme, oversize file.
2. Audio code dispatcher: every value in the §7.1 enum maps to the
   right action.
3. Multipart body builder: byte-count match between assembled body and
   declared `Content-Length`.
4. JSON response parser: well-formed response, missing `directive`,
   missing `audio_code`, unknown `audio_code` (forward-compat).
5. Protocol-version verifier: missing header, wrong value.

When PlatformIO ships, the framework choice + test files location go
into a future ADR-9-supersession.

### Consequences

- Firmware author is free to mock SD and HTTP however the chosen
  framework prefers.
- Logical coverage is locked even before tooling is.

### Alternatives considered

- **Pick Unity now.** Mild preference, but premature: PlatformIO
  setup may bring its own conventions.

---

## ADR-10 — `fetch_url` is concatenated as `base_url + fetch_url`, verbatim

### Context

PHASE_11_ARCHITECTURE.md says:

> ESP firmware appends to VITE_API_BASE_URL (or its hardcoded base)
> and issues GET.

This was implicit and ambiguous: `VITE_API_BASE_URL` is a frontend
env, not relevant on ESP. The firmware needs explicit guidance.

Backend behavior (verified in `app/api/audio.py:137`):

`python
fetch_url=f"/agent/audio/{log_id}/tts"
`

The value is always a relative path starting with `/`.

### Decision

The firmware constructs the TTS GET URL as:

`
request_url = base_url + directive.fetch_url
`

with exactly one `/` between them (firmware HTTP helper deduplicates
slashes).

The firmware MUST NOT parse `directive.fetch_url` into segments and
re-emit. It treats the value verbatim. This insulates firmware from
future server-side path changes (e.g. if the backend later adds a
prefix like `/v2/agent/audio/...`).

### Consequences

- Server can change the URL shape without firmware reflash, as long as
  the response stays bytes-compatible.
- Firmware HTTP helper has one job: `join(base_url, path)`.

### Alternatives considered

- **Hardcode the path template in firmware.** Rejected: tightly
  couples firmware to a specific backend path.

---

## ADR-11 — Two X-Device-Token mechanisms collapse via 1-device convention

### Context

Verified during code review: the backend has **two distinct
authentication mechanisms** that both use the header name
`X-Device-Token`:

1. **Per-device** (pp/api/_auth_dependencies.require_device_token):
   - Used by `POST /agent/audio` and `GET /agent/audio/{log_id}/tts`.
   - Looks up a row in `Device` where `api_token` matches the
     header value.
   - Gated by `REQUIRE_DEVICE_TOKEN` setting (default `true`).

2. **Global** (pp/api/devices.require_device_token, defined inline
   in pp/api/devices.py:62-78):
   - Used by `/devices/{device_code}/commands/pending`,
     `/devices/{device_code}/commands/{command_id}/ack`,
     `/devices/{device_code}/status`.
   - Compares the header to a single `settings.device_api_token`
     env value, identical for every device.

The Phase 11/12 docs did not surface this divergence. The firmware
needs to send a token to both endpoint groups. Sending a different
value per group is brittle and confusing for a 1-device MVP.

### Decision

For the 1-device MVP, the operator MUST configure the backend so the
global token equals the paired device's token:

`ash
# .env (backend)
REQUIRE_DEVICE_TOKEN=true
DEVICE_API_TOKEN=<api_token from POST /devices/pair response>
`

This collapses both mechanisms into a single working token. The
firmware sends `X-Device-Token: <device_token from config.json>` for
every authenticated request.

When the project moves beyond 1-device, the global `device_api_token`
mechanism MUST be removed in favor of unified per-device lookup. That
work is a future backend phase, not a firmware change.

### Consequences

- Operator setup gains one explicit step (paste the device token into
  `.env` after pairing). This step is now part of the Contract §3.3.
- The firmware sends one token everywhere — no branching.
- The 1-device MVP convention is enforced operationally, not
  programmatically. A future ADR will record the unification on the
  backend side.

### Alternatives considered

- **Send two different headers (e.g. `X-Global-Device-Token` and
  `X-Device-Token`).** Rejected: firmware complexity, divergence from
  Phase 12 docs.
- **Always use the per-device check for `/devices/{code}/...`.**
  Correct long-term fix, but requires backend code change. Out of
  scope for this round.
- **Always use the global check for `/agent/audio*`.** Rejected:
  loses the per-device audit trail in `VoiceCommandLog`.

### Backend follow-up [INFORMATIVE]

Future backend phase (not part of firmware contract): replace
`app/api/devices.require_device_token` with a per-device lookup
(matching `app/api/_auth_dependencies.require_device_token` behavior).
This removes the `DEVICE_API_TOKEN` env entirely. When that ships,
this ADR is superseded.

---

## Summary table

| ADR | Topic | Resolution |
|---|---|---|
| 1 | Base URL HTTP vs HTTPS | Opaque; firmware honors scheme |
| 2 | Multipart upload strategy | Option A (PSRAM blob) for v1 |
| 3 | WiFi drop mid-request | Atomic abort, no resume |
| 4 | Heartbeat concurrency | FreeRTOS software timer, paused outside IDLE |
| 5 | OLED face pixmaps | XBM in firmware, not on SD |
| 6 | TTS playback strategy | Buffer-then-play for v1 |
| 7 | Library version pins | Deferred until PlatformIO setup |
| 8 | Memory budget | Published table; no dual buffers |
| 9 | Firmware unit tests | Logical contracts only; framework deferred |
| 10 | fetch_url construction | base_url + fetch_url verbatim |
| 11 | Two X-Device-Token mechanisms | Collapse via 1-device convention |

Each Contract section is annotated with the ADR(s) that drive it.

---

## Living document policy

- New gaps discovered during firmware implementation get a new ADR.
- Existing ADRs are never edited destructively. If a decision changes,
  add an ADR-N-supersession that references the old one and explains
  what changed.
- The Contract document is updated to match the latest accepted ADR.
- This file is co-located with the Contract and supersedes individual
  Phase 11/12 doc paragraphs that conflict with it.


## ADR-12 - Display is TFT ILI9341 320x240, not OLED SSD1306

### Context

Contract §14 originally referenced an OLED SSD1306 128×64 I2C panel
(SDA=8, SCL=9) inherited from Phase 11 docs. Reality (per
`taskbot_online_pinmap.md` and the existing offline firmware "Smooth
Offline v5"): the device uses an Adafruit ILI9341 320×240 RGB565 TFT
on a shared SPI bus with the microSD card.

Two structural consequences:

1. GPIO 8/9 (formerly OLED I2C) are now MAX98357A I2S output
   (LRC/BCLK). The I2S audio output works because OLED is gone.
2. Display memory is now ~150 KB framebuffer (320 * 240 * 2 bytes),
   not 1 KB. Rendering is RGB565 procedural drawing on a
   `GFXcanvas16`, not XBM bitmap blit.

The existing offline firmware already handles all TFT rendering for
five emotion states (HAPPY, SATISFIED, DIZZY, ANGRY, ANGRY_IDLE) using
`Adafruit_ILI9341` + `GFXcanvas16` + procedural draw helpers. Online
firmware must reuse this rendering pipeline rather than introduce a
parallel one.

### Decision

The TFT ILI9341 is the canonical display. Online firmware reuses the
offline rendering pipeline:

- `Adafruit_ILI9341` for hardware-level SPI driving.
- `GFXcanvas16` (heap-backed) as offscreen framebuffer.
- `Adafruit_GFX` for text + primitive shapes.
- ROI streaming (`pushFaceROI`) for fast face updates.
- Indonesian-language `screen_text` rendered via `Adafruit_GFX`
  text functions, NOT u8g2.

Contract §14 hardware reference is updated to reflect TFT pinout.
Contract §11 OLED catalog becomes "TFT screen text catalog"; same
copy, different rendering target.

ADR-5 (OLED XBM pixmaps in firmware) is **superseded by ADR-12**.
Server-driven faces (`happy`, `sad`, `thinking`, `neutral`)
are rendered procedurally on the GFXcanvas, not as static XBM blits.
This costs ~3 KB extra flash for face drawing helpers but unifies
rendering with the offline emotion state machine, avoiding a parallel
graphics path.

### Consequences

- Memory budget §14.1 amended: ~150 KB heap framebuffer reserved.
  Audio buffer (PSRAM) is unaffected. Total RAM ceiling under 1.7 MB
  peak.
- Online face rendering shares helpers with offline (eyes, mouth,
  brow primitives in `tft_face.cpp`).
- The 7-frame "thinking" face animation is implemented as procedural
  bouncing dots on the GFXcanvas, not multi-XBM cycling.
- The screen never goes dark during PLAYING_RESPONSE — server text is
  layered into the existing TFT face region.

### Alternatives considered

- **Bring back OLED on a different I2C pair (e.g. GPIO 38/39).**
  Rejected: GPIO 38-40 are reserved (internal SD/SDIO). Adding I2C
  fights the pinmap.
- **Keep OLED + TFT both.** Rejected: doubles BOM cost, doubles
  rendering paths, doesn't help users.
- **Render online faces as XBM and blit on TFT.** Rejected: TFT is
  RGB565, XBM is monochrome — looks visibly out of place next to
  procedural offline faces.

---

## ADR-13 - Offline + online coexistence: single firmware, layered state

### Context

The user already shipped "Smooth Offline v5", an Arduino-IDE firmware
with a complete emotion state machine driven by touch sensor (GPIO4)
and MPU6050 shake detection. That firmware is the baseline and works.

User requirement (verbatim): "kedua mode itu berdampingan. Offline
bekerja sebagai fallback dari online jadi offline features always-on.
Fitur online auto-aktif kalau wifi tersedia, nantinya ada juga
perilaku bmo yang memberitahu gabisa akses fitur online karena tidak
ada internet."

Roles per pinmap:
- Touch sensor (GPIO4) = wake-from-idle (offline)
- PTT button (GPIO18) = record audio (online only)
- MPU6050 = shake-to-dizzy (offline)
- INMP441 / MAX98357A / SD = online features

Constraint: A breaking change to offline behavior is unacceptable.
Online integration MUST NOT regress shake-to-dizzy, touch-to-satisfied,
or any Smooth-v5 timing.

### Decision

Single firmware with a **two-tier state machine**:

1. **Offline tier** (always running): the Smooth-v5 emotion state
   machine. Touch + shake input continue to drive emotion transitions
   exactly as today.

2. **Online tier** (overlay): a new state machine for the audio
   request lifecycle: `[ONLINE_IDLE] -> [RECORDING] -> [SENDING] ->
   [PLAYING_RESPONSE] -> [SHOWING_ERROR] -> [ONLINE_IDLE]`. While
   online tier is in any non-idle state, offline emotion transitions
   are **suppressed** (input ignored, current emotion held).

3. **WiFi tier** (background): WiFi connection state is tracked
   continuously. If WiFi is unavailable when the user presses PTT
   button, the firmware enters a transient `[OFFLINE_NOTICE]` online
   state: BMO shows `EMO_SAD` for ~2 seconds with TFT text "Tidak
   ada internet". Then both tiers resume normal operation.

Server-driven directives (`directive.face` from
`POST /agent/audio` response) become **temporary face overrides**
during `[PLAYING_RESPONSE]`. They do NOT modify the persistent
offline emotion. After playback ends, the offline emotion that was
active resumes its render.

Mapping from Contract `face` enum to firmware emotion overrides:

| Contract `face` | Override emotion |
|---|---|
| `happy` | `EMO_SERVER_HAPPY` (uses HAPPY visuals, no autonomous blink/look) |
| `sad` | `EMO_SERVER_SAD` (new: droopy eyes + downturned mouth) |
| `thinking` | `EMO_SERVER_THINKING` (new: bouncing dots beneath eyes) |
| `neutral` | `EMO_SERVER_NEUTRAL` (HAPPY visuals, no breath bob) |

Indonesian `directive.screen_text` is rendered above or beside the
face as monospace text (per Contract §11.2), then cleared on
`[ONLINE_IDLE]` re-entry.

### Consequences

- Existing offline .ino becomes the visual core. Online firmware
  imports the same draw helpers.
- New code is purely additive: WiFi manager, audio capture / playback,
  network client, directive dispatcher, heartbeat timer, online state
  machine. Total ~1500 lines of new C++ across 12 files.
- Failure modes are graceful: WiFi down = offline still works.
  Audio hardware down = offline still works (firmware logs +
  shows error face but does not halt).
- Touch debounce, MPU6050 calibration, blink/look animations are
  **unchanged** from Smooth-v5.

### Alternatives considered

- **Two separate firmwares with NVS-stored mode toggle.** Rejected by
  user explicitly: doesn't want hard separation.
- **Online firmware replaces offline (deprecate offline).** Rejected:
  loses the existing investment in BMO emotion polish; loses the
  "BMO is alive" UX when WiFi is down.
- **Online runs as a FreeRTOS task entirely separate from offline
  loop().** Considered. Rejected for v1 because shared TFT framebuffer
  needs a single render task. Multi-task is a possible v2 refactor.

### Followup ADR (when shipped)

ADR-13b: when stream-while-playing TTS lands (ADR-6 superseded), the
`[PLAYING_RESPONSE]` state needs reentrancy guards on the I2S output
because chunked TLS stalls could flush a partial frame.

---

# ESP32-S3 ↔ Backend Integration Contract

**Status:** NORMATIVE GROUND TRUTH for Lyla / Taskbot ESP32-S3 firmware.
**Audience:** firmware author, backend operator, dashboard team.
**Supersedes (in case of disagreement):** `docs/PHASE_11_FIRMWARE.md`,
`docs/PHASE_11_ARCHITECTURE.md`, `docs/PHASE_11_BACKEND.md`,
`docs/phase-12/ESP_BRIEF.md`, `docs/phase-12/BACKEND_BRIEF.md`.
Those documents remain valid for historical context but where this
document differs, this document wins.

**Companion:** `docs/ESP32_INTEGRATION_ADR.md` — decision log explaining
why each ambiguity was resolved the way it is. Read that file when you
disagree with a choice here.

**Backend baseline:** Phase 12 shipped (`310 passed`). Verified against
`app/api/audio.py`, `app/api/devices.py`, `app/api/_audio_directive.py`,
`app/api/_auth_dependencies.py`, `app/api/audio_tts.py`,
`app/main.py`, `app/schemas/audio.py`, `app/schemas/devices.py`,
`app/utils/audio_validation.py`, `app/config.py` at commit `afbdb7b`.

Protocol version: **`X-Lyla-Protocol: 1`**.

---

## How to read this document

Sections marked **[NORMATIVE]** are contract. The firmware MUST conform.
Sections marked **[INFORMATIVE]** are background, rationale, or
non-binding examples.

Words in capitals (MUST, MUST NOT, SHOULD, MAY) follow RFC 2119 usage.

Every endpoint section answers four questions in this order:
1. **Path & method** (exact)
2. **Headers in / out** (which are required, optional, frozen)
3. **Body in / out** (schema, with field-level constraints)
4. **Status codes** (which the firmware must distinguish)

If a fact is not in this document, it is **not** part of the contract
and MUST NOT be relied on by firmware.

---

## 1. Identity & deployment posture [NORMATIVE]

| Concept | Value |
|---|---|
| Backend public URL (production) | `https://<your-domain>` (e.g. AWS-fronted) |
| Backend dev URL (LAN) | `http://<lan-ip>:8765` (LAN only, not internet-exposed) |
| TLS termination | external to FastAPI (AWS ALB / CloudFront / reverse proxy / Cloudflare Tunnel). FastAPI itself stays HTTP. |
| Device authentication | `X-Device-Token` header (per-device). See §3. |
| Provisioning | manual SD-card transfer; no BLE, no captive portal. |
| Token rotation | re-pair via dashboard, re-write SD card. No on-device rotate. |
| Concurrency | 1 ESP per `Device` row. No multi-tenant on a single device. |

**The firmware MUST NOT** assume a specific origin shape (LAN vs HTTPS).
It MUST read `base_url` from `/sd/config.json` and treat it as opaque
prefix for every request.

**The firmware MUST** support both HTTP and HTTPS schemes. HTTPS is
production default. HTTP is permitted for LAN development only.

### Why this matters for AWS deployment [INFORMATIVE]

When you deploy to AWS, the typical setup is:
- ALB / CloudFront terminates TLS with an ACM certificate
- FastAPI runs behind on plain HTTP inside the VPC
- Public URL is `https://lyla.<your-domain>` (or `https://<alb-dns>`)
- Operator pairs the device after deployment; the pair response embeds
  `base_url` from `BASE_URL` env on the backend, so ESP picks it up
  automatically without firmware reflash.

The implication for firmware: there is **no compile-time URL**. All
network targets come from `/sd/config.json`. This is intentional so the
same firmware binary runs against `localhost`, LAN, staging, and AWS
production unchanged.

---

## 2. Provisioning & `/sd/config.json` [NORMATIVE]

### 2.1 Operator flow (one-time per device)

1. Operator logs in to the dashboard at the public URL.
2. Navigates to `/devices` → "Pair New Device" → enters a label.
3. Backend issues `POST /devices/pair` (session-cookie gated).
4. Response includes a `config_json` blob (see §2.3).
5. Operator copies the blob, fills `wifi.ssid` and `wifi.password`
   locally, saves the file as **`/sd/config.json`** on a microSD card
   (FAT32, ≥4 GB).
6. Operator inserts SD card, powers ESP on.

The firmware never modifies this file. Token rotation is the operator's
job (re-pair, re-write SD).

### 2.2 File location & encoding

- Path on SD card: `/config.json` (root of the FAT32 volume).
- Encoding: UTF-8, no BOM.
- Line endings: any (`\n` or `\r\n`).
- File size: ≤ 4 KiB (a full-fat config including comments fits well
  within 1 KiB; the firmware MAY reject > 4 KiB as malformed).

### 2.3 Schema [NORMATIVE]

```json
{
  "user_id": "9f58e349-63b2-4f30-8fce-277d8cc670d7",
  "device_id": "34074323-28c8-459c-a005-f9d9b8d26ddb",
  "device_code": "TASKBOT-DEMO-001",
  "device_token": "tk_live_abc123...",
  "base_url": "https://lyla.example.com",
  "wifi": {
    "ssid": "MyHomeWifi",
    "password": "secretpassword"
  },
  "firmware_version": "0.1.0"
}
```

Field-level rules:

| Field | Type | Required | Validation |
|---|---|---|---|
| `user_id` | UUID v4 string | **yes** | regex `[0-9a-f]{8}-[0-9a-f]{4}-...` (36 chars) |
| `device_id` | UUID v4 string | **yes** | same |
| `device_code` | string | **yes** | non-empty, ≤ 64 chars |
| `device_token` | string | **yes** | non-empty; treat as opaque |
| `base_url` | string | **yes** | starts with `http://` or `https://`; no trailing slash |
| `wifi.ssid` | string | **yes** | non-empty, ≤ 32 chars (802.11 limit) |
| `wifi.password` | string | **yes** | may be empty for open networks |
| `firmware_version` | semver string | **yes** | reported back to backend in telemetry |

**Validation on boot [NORMATIVE]:**

If any required field is missing, empty, or fails the validation rule,
the firmware MUST:
1. Render `Config error: <field>` on TFT (Indonesian: see §11).
2. Halt the main loop. Do NOT attempt WiFi or any network call.
3. Optionally blink the status LED red.

Halt is the correct outcome because every recovery path requires SD
card replacement.

### 2.4 `base_url` policy [NORMATIVE]

This is the **most important** field for AWS deployment. Policy:

- The firmware MUST treat `base_url` as the unmodified prefix for
  every request URL. Concretely: `request_url = base_url + path`,
  with a single `/` between them ensured by the firmware.
- The firmware MUST NOT strip, normalize, lowercase, or re-encode
  `base_url`.
- The firmware MUST select TLS based on the scheme:
  - `http://...` → plain `WiFiClient`
  - `https://...` → `WiFiClientSecure` with `setInsecure()` (MVP) — see §13.
- If `base_url` contains a port, the firmware MUST honor it (e.g.
  `http://192.168.1.10:8765` connects to port 8765, not 80).

### 2.5 Pair endpoint contract [NORMATIVE]

`POST /devices/pair`

Auth: dashboard session cookie (`lyla_session`). NOT a device endpoint.
The firmware MUST NOT call this endpoint. It is operator-facing.

Request body:
```json
{ "name": "Lyla Demo Unit" }
```

Response (HTTP 201):
```json
{
  "device_id": "...",
  "device_code": "TASKBOT-XXXX",
  "api_token": "tk_live_...",
  "config_json": {
    "user_id": "...",
    "device_id": "...",
    "device_code": "TASKBOT-XXXX",
    "device_token": "tk_live_...",
    "base_url": "<from BASE_URL env>",
    "wifi": { "ssid": "", "password": "" },
    "firmware_version": "0.1.0"
  }
}
```

The dashboard SHOULD display `config_json` in a copyable textarea so the
operator can paste, fill `wifi`, and save to SD.

---

## 3. Authentication [NORMATIVE]

The backend has **two distinct token mechanisms** that share the
`X-Device-Token` header name. The firmware MUST send the right token to
the right endpoint group.

### 3.1 Per-device token (audio endpoints)

Used by:
- `POST /agent/audio`
- `GET /agent/audio/{log_id}/tts`

Backend behavior (see `app/api/_auth_dependencies.require_device_token`):
- If `REQUIRE_DEVICE_TOKEN=false` (dev only): no header required.
- If `REQUIRE_DEVICE_TOKEN=true` (production default):
  - Header `X-Device-Token` is required.
  - Value MUST equal `Device.api_token` for some row in the DB.
  - Lookup is by token, not by `device_code` or `device_id`.

The firmware MUST send the value of `device_token` from
`/sd/config.json` as `X-Device-Token`.

### 3.2 Global token (device-management endpoints)

Used by:
- `GET /devices/{device_code}/commands/pending`
- `POST /devices/{device_code}/commands/{command_id}/ack`
- `POST /devices/{device_code}/status`

Backend behavior (see `app/api/devices.require_device_token`):
- Header `X-Device-Token` is required.
- Value MUST equal `settings.device_api_token` (env `DEVICE_API_TOKEN`).
- This is a **single global token** shared across all devices.

### 3.3 1-device MVP convention [NORMATIVE]

For the MVP, the operator MUST configure the backend so that:

```
DEVICE_API_TOKEN == <api_token of the single paired device>
```

This makes the two mechanisms collapse into one usable token. The
firmware sends `X-Device-Token: <device_token from config.json>` for
**every** authenticated request, and both endpoint groups accept it.

This convention is documented and enforced by ADR-11. When the project
moves beyond 1-device MVP, the global `device_api_token` mechanism MUST
be removed in favor of unified per-device lookup. Until then, the
operator-side `.env` setup is:

```bash
# .env (backend)
REQUIRE_DEVICE_TOKEN=true
DEVICE_API_TOKEN=<paste device.api_token from POST /devices/pair response>
```

### 3.4 Header sent by firmware [NORMATIVE]

For every request to:
- `POST /agent/audio`
- `GET /agent/audio/{log_id}/tts`
- `GET /devices/{device_code}/commands/pending`
- `POST /devices/{device_code}/commands/{command_id}/ack`
- `POST /devices/{device_code}/status`

the firmware MUST set:

```
X-Device-Token: <device_token from /sd/config.json>
```

The token value MUST NOT appear in TFT text, serial logs at INFO level
or higher, or any error message. DEBUG logs MAY include the first 6
characters followed by `...` (e.g. `tk_liv...`).

### 3.5 Failure semantics

- HTTP 401 from any of the above endpoints → firmware enters the
  "Device tidak terdaftar" error path (§11), halts main loop, requires
  SD-card re-provisioning.
- HTTP 403 is not used by the backend for these endpoints. If observed,
  treat identically to 401.

---

## 4. Network plumbing [NORMATIVE]

### 4.1 WiFi

- Standard: 802.11 b/g/n on 2.4 GHz only (ESP32-S3 limitation).
- SSID/password from `wifi.ssid` / `wifi.password` in config.
- Connection retry: exponential backoff starting at 1s, doubling, capped
  at 30s. Retry forever; do not give up.
- During retry, TFT shows `WiFi terputus` and the firmware MUST NOT
  enter audio capture or playback states.
- If WiFi was up and drops mid-request, the in-flight HTTP call MUST
  be aborted within 5 seconds and treated as timeout (see §6.4).

### 4.2 TLS

- Production (`base_url` starts with `https://`): use
  `WiFiClientSecure` with `setInsecure()` for MVP. See §13 for the
  trade-off and the post-MVP upgrade path (root-CA bundle).
- Dev (`base_url` starts with `http://`): use plain `WiFiClient`. Do
  NOT instantiate `WiFiClientSecure` for HTTP URLs (wastes RAM).
- Per-request socket timeout: 30 seconds (§6.4 audio, 15 seconds for
  TTS fetch and heartbeat).

### 4.3 HTTP client

- Library: `HTTPClient` (Arduino-ESP32 built-in).
- Connection: keep-alive is OPTIONAL. The backend tolerates new
  connection per request.
- User-Agent: the firmware SHOULD send
  `User-Agent: Lyla-ESP32S3/<firmware_version>`. Backend does not
  inspect this; it is for log triage.
- The firmware MUST NOT send `Cookie` headers. Sessions are
  dashboard-only.

### 4.4 DNS

- Resolved by the underlying WiFi stack. The firmware does not need to
  manage DNS itself.
- If DNS resolution fails (`http.begin` returns false or `http.GET()` /
  `POST()` returns negative), treat as the "Tidak bisa hubungi server"
  error path (§11).

### 4.5 Time-of-day

- The firmware does not need a real clock for the audio request path
  (the backend stamps `request_received_at` server-side).
- For UUID v4 generation in `client_request_id` the firmware uses
  `esp_fill_random` only — no time required.
- If a future feature needs wall-clock time, NTP via `pool.ntp.org`
  SHOULD be added; currently it is out of scope.

---

## 5. Endpoint reference [NORMATIVE]

All paths are appended to `base_url` from `/sd/config.json`.

| # | Method | Path | Used for | Auth header |
|---|---|---|---|---|
| 5.1 | POST | `/agent/audio` | submit recorded voice | `X-Device-Token` |
| 5.2 | GET | `/agent/audio/{log_id}/tts` | fetch dynamic TTS audio | `X-Device-Token` |
| 5.3 | POST | `/devices/{device_code}/status` | heartbeat | `X-Device-Token` |
| 5.4 | GET | `/devices/{device_code}/commands/pending` | poll commands (optional, future) | `X-Device-Token` |
| 5.5 | POST | `/devices/{device_code}/commands/{command_id}/ack` | ack command (optional, future) | `X-Device-Token` |
| 5.6 | GET | `/healthz` | liveness probe (optional) | none |

Endpoints 5.4 and 5.5 are not used by the audio path. They exist for
the legacy device command queue (Phase 7). Firmware MAY skip them in
v1; if used, they share the same header convention.

The `/agent/text` endpoint is **not** part of the firmware contract.
It is used by the dashboard and by `scripts/run_agent_text.py` only.
ESP MUST NOT call it.

---

## 6. `POST /agent/audio` [NORMATIVE]

### 6.1 Path and method

```
POST <base_url>/agent/audio
```

### 6.2 Headers

Request:

| Header | Required | Value |
|---|---|---|
| `Content-Type` | yes | `multipart/form-data; boundary=<boundary>` |
| `X-Device-Token` | yes (when `REQUIRE_DEVICE_TOKEN=true`) | `<device_token from config>` |
| `User-Agent` | optional | `Lyla-ESP32S3/<firmware_version>` |
| `Accept` | optional | `application/json` |

Response:

| Header | Always present | Value |
|---|---|---|
| `Content-Type` | yes | `application/json` |
| `X-Lyla-Protocol` | yes | `1` (firmware MUST verify) |

The `X-Lyla-Protocol` header is added by middleware in `app/main.py`
on every response whose path starts with `/agent/audio`. Firmware
behavior on mismatch: §6.6.

### 6.3 Multipart body

Fields, in any order:

| Name | Type | Required | Notes |
|---|---|---|---|
| `file` | file | **yes** | WAV PCM 16 kHz mono 16-bit; filename ends `.wav`; `Content-Type: audio/wav` |
| `user_id` | text | **yes** | UUID from config |
| `device_id` | text | optional but firmware MUST send | UUID from config |
| `timezone` | text | optional but firmware MUST send | hardcode `Asia/Jakarta` |
| `client_request_id` | text | optional but firmware MUST send | UUID v4, fresh per request |
| `firmware_version` | text | optional but firmware MUST send | from config |
| `wifi_rssi_dbm` | text | optional but firmware MUST send | integer, e.g. `-55` |
| `battery_pct` | text | optional but firmware MUST send | `0..100`, or `-1` if unknown |
| `recording_duration_ms` | text | optional but firmware MUST send | integer ms from button-down to button-up |

Backend behavior with optional fields: missing fields are stored as
`null` in `VoiceCommandLog.metadata_json`. They never affect the agent
output. Firmware sending them all is required to make
`/observability/*` useful.

Audio constraints:

- Format: WAV PCM 16-bit signed little-endian.
- Sample rate: 16000 Hz.
- Channels: 1 (mono).
- Max upload size: `MAX_AUDIO_UPLOAD_MB * 1_000_000` bytes (decimal MB,
  default 10 MB → 10,000,000 bytes).
- Allowed extensions on backend (`app/utils/audio_validation.py`):
  `.wav`, `.mp3`, `.webm`, `.m4a`. Firmware uses `.wav`.
- Allowed content types: `audio/wav`, `audio/x-wav`,
  `application/octet-stream` (and others; firmware uses `audio/wav`).

### 6.4 Timeouts and retry

- Socket timeout: 30 seconds. Set on `HTTPClient` via
  `http.setTimeout(30000)` and on the underlying client.
- Firmware-level total timeout: 30 seconds. After that, abort the
  request and enter the "Server tidak responsif" error path (§11).
- The firmware MUST NOT retry `POST /agent/audio` automatically. The
  request creates a `VoiceCommandLog` row server-side (Phase 12 captures
  metadata even on error paths in some scenarios), and silent retries
  produce duplicate logs and possibly duplicate side effects (e.g.
  `create_task` running twice). Recovery is user-driven: user presses
  the button again.

### 6.5 Response body shape

HTTP 200, `Content-Type: application/json`. Schema is
`AgentAudioResponse` in `app/schemas/audio.py`:

```json
{
  "reply": "string",
  "actions": [ /* tool result dicts; firmware ignores */ ],
  "device_feedback": null,
  "transcription": {
    "text": "string",
    "mode": "fake" | "gemini",
    "duration_ms": null,
    "confidence": null
  },
  "audio": {
    "filename": "string",
    "content_type": "string",
    "size_bytes": 0
  },
  "tts": {
    "mode": "fake" | "gemini",
    "available": true,
    "content_type": "audio/wav"
  },
  "directive": {
    "audio_code": "ok_expense" | "ok_task" | "ok_reminder" | "ok_summary" | "ok_generic" | "err_generic" | "fallback_tts",
    "face": "happy" | "sad" | "thinking" | "neutral",
    "screen_text": "string or null (≤60 chars)",
    "fetch_url": "string or null"
  }
}
```

**The firmware MUST only act on `directive`.** All other fields are
informational. The firmware MUST NOT pattern-match on `reply`,
`actions`, or `transcription.text`.

### 6.6 Status codes

| Code | Meaning | Firmware action |
|---|---|---|
| 200 | success | proceed to §7 (directive dispatch) |
| 400 | validation rejected (audio empty, bad ext, bad MIME) | err_generic, TFT `Rekaman bermasalah`, → IDLE |
| 401 | missing or invalid `X-Device-Token` | err_generic, TFT `Device tidak terdaftar`, halt |
| 404 | unknown `user_id` or `device_id` | err_generic, TFT `Akun belum siap`, halt |
| 413 | audio file too large | err_generic, TFT `Rekaman terlalu panjang`, → IDLE |
| 422 | malformed multipart | err_generic, TFT `Permintaan ditolak`, → IDLE |
| 500 | agent runtime crashed | err_generic, TFT `Coba lagi sebentar`, → IDLE |
| 502 | STT provider failure | err_generic, TFT `Coba lagi sebentar`, → IDLE |
| (any other 5xx) | server error | err_generic, TFT `Server bermasalah`, → IDLE |
| (any other 4xx) | reject | err_generic, TFT `Permintaan ditolak`, → IDLE |
| (network timeout / no response) | server unreachable | err_generic, TFT `Server tidak responsif`, → IDLE |

In all cases the firmware also verifies `X-Lyla-Protocol: 1` on the
response. Mismatch (header missing or value not `"1"`): treat as the
error path "Versi server beda".

---



## 7. Directive dispatch [NORMATIVE]

The `directive` object is the only contract the firmware acts on. All
fields are server-classified. ESP firmware is a dumb dispatcher.

### 7.1 `audio_code` enum (frozen)

| Value | Triggered by | ESP playback |
|---|---|---|
| `ok_expense` | `create_expense` succeeded | `/sd/sounds/ok_expense.wav` |
| `ok_task` | `create_task` succeeded | `/sd/sounds/ok_task.wav` |
| `ok_reminder` | `set_reminder` succeeded | `/sd/sounds/ok_reminder.wav` |
| `ok_summary` | `get_today_summary` succeeded | `/sd/sounds/ok_summary.wav` |
| `ok_generic` | other tool succeeded | `/sd/sounds/ok_generic.wav` |
| `err_generic` | at least one action failed | `/sd/sounds/err_generic.wav` |
| `fallback_tts` | no actions; agent gave free-form reply | fetch `directive.fetch_url` and stream |

If `directive.audio_code` matches none of these (forward-compat with a
future server version), the firmware MUST treat it as `ok_generic` and
continue. It MUST NOT crash.

### 7.2 `face` enum (frozen)

| Value | TFT rendering |
|---|---|
| `happy` | smile pixmap |
| `sad` | frown pixmap |
| `thinking` | dots animation |
| `neutral` | flat-line pixmap |

Unknown `face` values: render `neutral`.

### 7.3 `screen_text`

- Type: string or null.
- Length: ≤ 60 characters (server already truncates with `…`).
- May contain `\n` for line breaks. Other control characters: render
  as space.
- Firmware MUST treat the string as opaque. No parsing, no regex.
- If `null`: clear the text region of the TFT.

### 7.4 `fetch_url`

- Type: string or null.
- When non-null, format is a **relative path** like `/agent/audio/<log_id>/tts`.
- The firmware MUST construct the request URL as `base_url + fetch_url`
  with exactly one `/` between them (handled by the firmware HTTP
  helper).
- The firmware MUST NOT use `fetch_url` for any audio_code other than
  `fallback_tts`. For all other codes it is `null` and MUST be
  ignored.

### 7.5 SD-card filename mapping

For audio_codes other than `fallback_tts`, the playback file is
`/sd/sounds/<audio_code>.wav`. The 7 files (6 mapped codes + greeting)
that MUST be present on every SD card:

`
/sd/sounds/ok_expense.wav
/sd/sounds/ok_task.wav
/sd/sounds/ok_reminder.wav
/sd/sounds/ok_summary.wav
/sd/sounds/ok_generic.wav
/sd/sounds/err_generic.wav
/sd/sounds/greet_hello.wav
`

Optional filler files (firmware SHOULD play to mask network latency):

`
/sd/sounds/ack_thinking.wav
/sd/sounds/ack_still_thinking.wav
/sd/sounds/ack_slow_network.wav
`

WAV format for every file: PCM 16-bit signed mono. Sample rate is read from the WAV header at runtime, so files MAY be 16 kHz or 24 kHz. The bundled SD pack generated by `scripts/generate_firmware_sounds.py` is **24 kHz** (Gemini TTS native).

If a required file is missing on SD, firmware MUST fall back to
`err_generic.wav`. If `err_generic.wav` itself is missing, firmware
MUST emit a 200 ms tone or skip playback silently and continue without
crashing.

---

## 8. `GET /agent/audio/{log_id}/tts` [NORMATIVE]

Used only when `directive.audio_code == "fallback_tts"` and
`directive.fetch_url` is non-null.

### 8.1 Path

`
GET <base_url><directive.fetch_url>
`

The firmware MUST NOT construct the path manually from the
`log_id`. It MUST use `directive.fetch_url` verbatim. This keeps
firmware insulated from future server-side path changes.

### 8.2 Headers

Request:

| Header | Required | Value |
|---|---|---|
| `X-Device-Token` | yes (when `REQUIRE_DEVICE_TOKEN=true`) | `<device_token from config>` |
| `Accept` | optional | `audio/wav` |

Response:

| Header | Always present | Value |
|---|---|---|
| `Content-Type` | yes | `audio/wav` |
| `X-Lyla-Protocol` | yes | `1` |

### 8.3 Body

WAV PCM 16-bit signed mono. Sample rate is the provider's native rate:

- Fake mode: 16000 Hz (matches `FAKE_TTS_SAMPLE_RATE`).
- Gemini mode: 24000 Hz (Gemini TTS native).

The firmware MUST inspect the WAV header (sample rate field at byte
offset 24) and configure the I2S output accordingly. Hard-coding 16 kHz
or 24 kHz on the firmware side is forbidden.

### 8.4 Timeouts

- Socket timeout: 15 seconds.
- The firmware SHOULD start playing filler audio
  (`ack_still_thinking.wav`) when this fetch begins, to mask Gemini
  TTS latency (~1-6 s).
- If the fetch fails or times out, fall back to `err_generic.wav` and
  return to IDLE.

### 8.5 Status codes

| Code | Meaning | Firmware action |
|---|---|---|
| 200 | audio bytes follow | parse WAV header, stream to I2S |
| 401 | bad token | TFT `Device tidak terdaftar`, halt |
| 404 | cache miss or expired (TTL 300 s) | err_generic, → IDLE |
| (any 5xx) | provider/server error | err_generic, → IDLE |
| (timeout) | network slow | err_generic, → IDLE |

### 8.6 Cache TTL

The backend caches TTS bytes in-process for `TTS_CACHE_TTL_SECONDS`
(default 300 s). The firmware MUST fetch immediately after receiving
`fetch_url` and MUST NOT defer the GET. Stale `log_id`s return 404.

### 8.7 Buffer-then-play (v1)

The firmware MUST download the full response body before starting I2S
playback. Streaming-while-downloading is intentionally deferred (see
ADR-6). Memory budget: ~12 s of WAV at 24 kHz mono 16-bit ≈ 576 KB,
fits in PSRAM.

---

## 9. `POST /devices/{device_code}/status` (heartbeat) [NORMATIVE]

### 9.1 Path

`
POST <base_url>/devices/<device_code>/status
`

`device_code` is from `/sd/config.json` (URL-encoded if it contains
non-ASCII; the default codes are ASCII-only).

### 9.2 Headers

| Header | Required | Value |
|---|---|---|
| `Content-Type` | yes | `application/json` |
| `X-Device-Token` | yes | `<device_token from config>` |

### 9.3 Body

`json
{
  "status": "online",
  "firmware_version": "0.1.0",
  "wifi_rssi_dbm": -55,
  "battery_pct": 80,
  "free_heap_bytes": 234567
}
`

Field rules:

| Field | Type | Required | Notes |
|---|---|---|---|
| `status` | string | yes | exactly `"online"` or `"offline"` |
| `firmware_version` | string | optional | from config |
| `wifi_rssi_dbm` | int | optional | from `WiFi.RSSI()` |
| `battery_pct` | int | optional | `0..100`; `-1` if no battery hardware |
| `free_heap_bytes` | int | optional | from `ESP.getFreeHeap()` |

The firmware SHOULD send all telemetry fields. Missing fields preserve
the previous value on the `Device` row (Phase 12 backend is
backward-compatible).

### 9.4 Cadence

| Event | Frequency |
|---|---|
| heartbeat (idle) | every 60 s |
| heartbeat (recording, sending, playing) | paused |
| heartbeat (after WiFi reconnect) | immediate, then resume 60 s cadence |
| `status: "offline"` final beat | optional; firmware MAY skip on power-off |

### 9.5 Response

HTTP 200 with body:

`json
{
  "status": "online",
  "last_seen_at": "2026-05-17T07:12:34.567+00:00"
}
`

The firmware SHOULD ignore the body. Heartbeat is fire-and-forget.

### 9.6 Status codes

| Code | Firmware action |
|---|---|
| 200 | continue |
| 401 | TFT `Device tidak terdaftar`, halt |
| 404 | TFT `Device tidak ditemukan`, halt |
| (other) | log, retry next 60 s tick |

The first heartbeat at boot is special: a 401 here MUST halt the
firmware before the user is allowed to interact (§10.1). Subsequent
heartbeat failures MUST NOT block the main loop.

---


## 10. Boot sequence [NORMATIVE]

The firmware MUST execute these steps in order. A failure at any step
that the table marks **halt** stops further progress.

| # | Step | On failure |
|---|---|---|
| 1 | Power on, init TFT | halt (no display = catastrophic) |
| 2 | Show splash `Lyla starting...` | — |
| 3 | Mount SD card | halt: `SD card error` |
| 4 | Read & validate `/sd/config.json` | halt: `Config error: <field>` |
| 5 | Init I2S input (mic) and I2S output (speaker) | halt: `Audio init error` |
| 6 | Init WiFi using `config.wifi` | retry forever, TFT `WiFi terputus` |
| 7 | Send first heartbeat (`status: "online"`) | 401 → halt; 5xx → log, continue |
| 8 | Play `/sd/sounds/greet_hello.wav` | log, continue |
| 9 | Render `face_neutral` | — |
| 10 | Enter main loop (IDLE) | — |

The button MUST NOT be sampled until step 10. Premature button events
during boot MUST be discarded.

### 10.1 First-heartbeat halt

Step 7 is the only network call before the user can interact. A 401
here unambiguously means the SD card carries an invalid token. The
firmware MUST halt with TFT `Device tidak terdaftar` and require
re-pair. This prevents the user from triggering audio captures that
will all fail authentication.

---

## 11. TFT user-facing copy [NORMATIVE]

All TFT messages MUST be in **Bahasa Indonesia**. They MUST NOT
contain HTTP status codes, English error names, stack traces, or token
values.

### 11.1 Frozen message catalog

These messages MUST be rendered on the **TFT screen text region** (the
strip below the BMO face area). Use the firmware's existing
`Adafruit_GFX` text helpers; do NOT switch fonts or render libraries
mid-flight.

| Trigger | TFT text (exact) |
|---|---|
| Boot splash | `Lyla starting...` |
| SD mount fail | `SD card error` |
| Config field invalid | `Config error: <field>` (e.g. `Config error: base_url`) |
| Audio init fail | `Audio init error` |
| WiFi disconnected | `WiFi terputus` |
| WiFi up but online unreachable mid-record | `Tidak ada internet` |
| TLS / DNS failure | `Tidak bisa hubungi server` |
| HTTP timeout | `Server tidak responsif` |
| Bad protocol version | `Versi server beda` |
| 401 from any device endpoint | `Device tidak terdaftar` |
| 404 `user_id` / `device_id` | `Akun belum siap` |
| 404 `device_code` (heartbeat) | `Device tidak ditemukan` |
| 5xx | `Server bermasalah, coba lagi` |
| 4xx (other) | `Permintaan ditolak` |
| Audio validation 400 | `Rekaman bermasalah` |
| 413 audio too large | `Rekaman terlalu panjang` |
| Bad JSON in response | `Respon tidak valid` |
| Missing SD audio file | `File audio hilang` |

### 11.2 `screen_text` rendering

When `directive.screen_text` is non-null, it replaces the static
message above for the duration of playback. After playback ends, the
firmware clears the screen text region and resumes the persistent
offline emotion (per ADR-13). Server-driven `face` overrides also
revert at this point.

### 11.3 Layout & truncation

TFT screen text region is 320 px wide × ~ 60 px tall, below the BMO
face (face ROI defined in `tft_face.cpp`). At the default 6×10
`Adafruit_GFX` font (text size 2 = 12×20 px), one row holds about 26
characters. Server already truncates `screen_text` to 60 chars total
with `…`; firmware honors `\n` for explicit line breaks and SHOULD
wrap on whitespace. Hard truncation past 60 chars is not the
firmware's responsibility.

---

## 12. State machine [NORMATIVE]

`
[BOOT] -> [IDLE]

[IDLE]
  on button press: -> [RECORDING]

[RECORDING]
  start I2S input (DMA), buffer to PSRAM (max 30 s, hard cap 960 KB)
  on button release: -> [SENDING]
  on max duration: -> [SENDING]

[SENDING]
  start filler playback (ack_thinking.wav) on I2S output, in parallel
  build multipart body in PSRAM (~ audio + 2 KB overhead)
  POST /agent/audio with X-Device-Token + telemetry
  on response 200: -> [PLAYING_RESPONSE]
  on response 401/404 first time: -> [HALTED]
  on any error: -> [SHOWING_ERROR]
  on timeout 30 s: -> [SHOWING_ERROR]

[PLAYING_RESPONSE]
  verify X-Lyla-Protocol: 1 (else -> [SHOWING_ERROR] mismatch)
  parse JSON, extract directive
  render directive.face + directive.screen_text on TFT
  if audio_code == "fallback_tts":
    GET <base_url><directive.fetch_url>, buffer-then-play (24 kHz)
  else:
    play /sd/sounds/<audio_code>.wav (rate from WAV header)
  on playback end: -> [IDLE]

[SHOWING_ERROR]
  play err_generic.wav
  show face_sad + Indonesian message (table 11.1)
  3 s delay
  -> [IDLE]

[HALTED]
  show face_sad + halt-class message
  blink status LED
  no further state transitions until power cycle
`

### 12.1 Concurrency model

The firmware MUST run audio I/O on FreeRTOS tasks separate from the
main control flow:

- I2S input (capture during `[RECORDING]`): high-priority task,
  DMA-driven.
- I2S output (playback during `[PLAYING_RESPONSE]`): high-priority
  task, DMA-driven.
- HTTP I/O (during `[SENDING]` and TTS fetch): runs on the main task
  or a worker task; the main loop polls state.
- Heartbeat: timer-driven (every 60 s), executes on a dedicated task or
  via FreeRTOS software timer. Paused while state is not `[IDLE]`.

Race-condition-prone boundaries (firmware MUST guard with mutex or
queue):
- Filler playback ↔ response playback handoff (don't double-start I2S).
- Heartbeat ↔ active request (heartbeat MUST NOT preempt an in-flight
  `POST /agent/audio`).

### 12.2 WiFi drop during request

If WiFi drops while in `[SENDING]` or while fetching TTS in
`[PLAYING_RESPONSE]`:
1. Abort the in-flight HTTP call (timeout within 5 s).
2. Stop any I2S DMA cleanly (don't truncate mid-buffer; let the current
   buffer flush).
3. -> `[SHOWING_ERROR]` with `Tidak bisa hubungi server`.
4. WiFi reconnect runs in background (§4.1) without firmware
   intervention.

The firmware MUST NOT attempt to "resume" a broken request. Voice
commands are atomic: re-record on next button press.

---


## 13. TLS posture [NORMATIVE]

### 13.1 MVP: `setInsecure()`

For the MVP, when `base_url` starts with `https://`, the firmware
MUST use `WiFiClientSecure` with `setInsecure()`:

`cpp
WiFiClientSecure client;
client.setInsecure();   // skip cert chain validation
client.setTimeout(30000);

HTTPClient http;
http.begin(client, full_url);
http.addHeader("X-Device-Token", config.device_token);
// ... build body, send
`

Trade-off:
- **Pro**: minimal code, no cert bundle to ship, no rotation pain.
- **Con**: vulnerable to active MITM if an attacker sits between ESP
  and the public endpoint (rogue WiFi, ISP tampering). The audio
  payload contains transcribed user speech which is privacy-sensitive.
  Acceptable for MVP. Not acceptable for sustained production.

### 13.2 Post-MVP upgrade path [INFORMATIVE]

When upgrading off `setInsecure()`:

1. Export the AWS-side certificate root CA (Amazon Root CA 1 PEM if
   ALB; ISRG Root X1 if Cloudflare/Let's Encrypt).
2. Embed in firmware as PROGMEM string `rootCaPem[]`.
3. Replace `client.setInsecure()` with `client.setCACert(rootCaPem)`.
4. Optionally pin a leaf cert via `client.setCertificate(...)` (not
   recommended for AWS-managed certs that auto-rotate).

Cost: ~5 KB flash for the CA bundle, ~20 lines of code. Plan to do
this before any production rollout beyond a single demo unit.

### 13.3 Token confidentiality

The `X-Device-Token` is the single secret on the device. Firmware
guarantees:
- MUST NOT print the full token via `Serial.print`.
- MUST NOT include the token in TFT text.
- MUST NOT include the token in heartbeat or error telemetry.
- MAY include the first 6 chars + `...` in DEBUG-level serial output
  for triage (e.g. `tk_liv...`).

If the token is compromised, the recovery procedure is documented in
`docs/PHASE_12_SUMMARY.md` (re-pair via dashboard, write new SD).

---

## 14. Hardware reference [NORMATIVE for pinmap, INFORMATIVE for the rest]

This section reflects the **actual** Taskbot/BMO ESP32-S3 hardware
(see `taskbot_online_pinmap.md` for full rationale). The pinmap is now
binding because firmware reuses the offline build's wiring; ADR-12
records why this section diverges from the original Phase 11 TFT
suggestion.

| Component | Bus | Pins (final) |
|---|---|---|
| ESP32-S3 WROOM (8 MB PSRAM) | — | — |
| TFT ILI9341 320×240 RGB565 | SPI shared | CS=14, DC=21, RST=47, MOSI=1, SCK=2, MISO=41 |
| microSD card | SDMMC 1-bit | CLK=39, CMD=38, D0=40 (Freenove on-board slot) |
| Touch sensor (TTP223) | GPIO | OUT=4 (wake-from-idle) |
| MPU6050 IMU | I2C | SDA=6, SCL=7 (shake-to-dizzy) |
| INMP441 mic | I2S input | WS=15, BCLK=16, SD=17 (3.3 V only) |
| MAX98357A speaker amp | I2S output | LRC=8, BCLK=9, DIN=10 (5 V VIN) |
| Push-to-talk button | GPIO | 18 (`INPUT_PULLUP`, active LOW) |
| Status LED | GPIO | 42 via 220 Ω resistor |

The TFT and the on-board microSD slot use **separate buses**. The TFT
runs on user SPI (MOSI=1, SCK=2, MISO=41), and the microSD uses the
dedicated SDMMC peripheral on GPIO 38/39/40. There is no bus contention
between display refresh and SD I/O. Firmware initializes
`Adafruit_ILI9341` over `SPIClass` and `SD_MMC.begin("/sdcard", true)`
in 1-bit mode independently.

### 14.1 Memory budget [NORMATIVE]

The audio buffer and the TFT framebuffer are the dominant allocations.

| Region | Bytes | Notes |
|---|---|---|
| TFT framebuffer (`GFXcanvas16` 320×240) | 153 600 | heap; reused by offline + online rendering |
| Audio capture buffer | 960 000 | `ps_malloc` in PSRAM (30 s mono 16-bit @ 16 kHz) |
| TTS playback buffer | up to 600 000 | PSRAM (12 s mono 16-bit @ 24 kHz) |
| Multipart preamble + trailer | ~ 1 500 | heap |
| ArduinoJson document | 4 096 | heap (sized for response shape) |
| TLS handshake buffers | ~ 32 000 | when `WiFiClientSecure` connects |
| FreeRTOS task stacks | ~ 30 000 | 5 tasks at 6 KB each |
| Application + libraries | balance | ~ 100 KB free heap floor |

Hard rules:
- Firmware MUST NOT hold the audio capture buffer and the TTS playback
  buffer simultaneously. Capture buffer is freed before issuing the
  TTS GET. PSRAM peak stays below 1.6 MB.
- The TFT framebuffer is allocated once at boot and lives forever.
  Offline + online rendering both write into this single buffer.
- If `ps_malloc` returns null at boot, firmware halts with TFT
  message "PSRAM tidak terdeteksi" (PlatformIO build flag
  `-DBOARD_HAS_PSRAM` + `-DCONFIG_SPIRAM_USE_MALLOC` MUST be set).

### 14.2 Power [INFORMATIVE]

USB power, 5 V / ≥ 1 A. MAX98357A draws up to 700 mA at peak. Battery
operation, deep sleep, and brown-out recovery are out of scope.

---

## 15. Versioning [NORMATIVE]

### 15.1 Protocol version

The contract is **protocol version 1**, advertised by the response
header `X-Lyla-Protocol: 1` on every `/agent/audio*` endpoint.

- Schema-additive changes (new optional field, new `audio_code` in a
  way that defaults to `ok_generic`) keep version 1.
- Removing a field, renaming a field, removing or repurposing an
  `audio_code` value, or changing the `directive` shape bumps the
  version to 2 and breaks compatibility.

The firmware MUST refuse to dispatch a directive when
`X-Lyla-Protocol` is missing or not equal to `"1"` (§6.6).

### 15.2 Firmware version

`firmware_version` is a semver string (`MAJOR.MINOR.PATCH`). The
firmware MUST report this in every audio request and every heartbeat.
The dashboard uses it for fleet triage.

Bumping `firmware_version` does NOT require a backend change. Backend
treats it as opaque metadata.

### 15.3 Out-of-scope today (frozen)

The following are **not** part of protocol version 1 and the firmware
MUST NOT depend on them:

- Wake-word ("Hey Lyla")
- Continuous / multi-turn conversation
- Real-time streaming audio (WebSocket, WebRTC)
- `POST /devices/{id}/rotate-token` endpoint
- BLE provisioning, captive portal
- OTA firmware update
- Battery sleep / deep-sleep
- Audio compression (Opus, AAC)
- Wake-on-button via ULP
- Voice biometrics

When any of these ship, the document version increments and the
`X-Lyla-Protocol` value MAY change.

---

## 16. Implementation checklist [NORMATIVE]

The firmware author MUST be able to tick every box before declaring v1
complete.

### Boot
- [ ] Read `/sd/config.json`; validate per §2.3
- [ ] Halt with localized TFT message on any validation failure
- [ ] Connect WiFi using `config.wifi`; exponential backoff per §4.1
- [ ] Send first heartbeat to `/devices/<device_code>/status`
- [ ] Halt on 401 first heartbeat (`Device tidak terdaftar`)
- [ ] Play `greet_hello.wav` on success
- [ ] Render `face_neutral` and enter IDLE

### Per request
- [ ] Capture mono 16 kHz 16-bit PCM into PSRAM buffer
- [ ] Build WAV header (44 bytes) per §6.3
- [ ] Generate fresh UUID v4 `client_request_id` (RFC 4122)
- [ ] Read `WiFi.RSSI()` for `wifi_rssi_dbm`
- [ ] Read battery (`-1` if no hardware)
- [ ] Track `recording_duration_ms` from button down to button up
- [ ] Send all telemetry fields in multipart body
- [ ] Send `X-Device-Token` header from config
- [ ] Set `http.setTimeout(30000)`
- [ ] Verify `X-Lyla-Protocol == "1"` on response
- [ ] Parse JSON, extract `directive` only
- [ ] Dispatch on `directive.audio_code` per §7.1
- [ ] Render `directive.face` and `directive.screen_text`
- [ ] Free audio capture buffer before TTS fetch

### Background
- [ ] Heartbeat every 60 s with full telemetry
- [ ] Pause heartbeat during `[RECORDING]` / `[SENDING]` / `[PLAYING_RESPONSE]`
- [ ] Reconnect WiFi with backoff (§4.1)
- [ ] No retries of `POST /agent/audio` (§6.4)

### Error paths
- [ ] All TFT text in Bahasa Indonesia (§11.1)
- [ ] No HTTP codes or stack traces on TFT
- [ ] No token leakage at any log level
- [ ] All paths (404, 401, 500, 502, timeout, JSON parse) handled
- [ ] Never crash / panic; always return to IDLE or HALTED
- [ ] Audio file missing on SD → fall back to `err_generic.wav`

### Security
- [ ] HTTPS via `WiFiClientSecure.setInsecure()` for `https://`
- [ ] Plain `WiFiClient` for `http://`
- [ ] Token is in PSRAM/heap only, never serialized to TFT or logs

---

## 17. Out of contract / future phases [INFORMATIVE]

When any of these ship, this document gets a version bump and the
firmware contract is renegotiated:

- AWS deployment specifics (DNS, ALB, IAM): operator concern, not
  firmware contract.
- Multi-device, multi-user (per-device tokens replacing the global one).
- Push notifications from backend to ESP (currently command queue is
  poll-based and unused in audio path).
- `DASHBOARD_AUTH_MODE=shared_header` for dashboard ↔ ESP cross-talk
  (the firmware does not call dashboard endpoints).
- Audio retention beyond the in-process TTS cache.

---

## 18. Cross-references

- `docs/ESP32_INTEGRATION_ADR.md` — decision log explaining each gap
  resolution.
- `docs/PHASE_11_ARCHITECTURE.md` — original protocol contract (frozen
  parts still valid).
- `docs/PHASE_11_FIRMWARE.md` — original firmware spec (superseded
  where it conflicts; otherwise valid).
- `docs/phase-12/ESP_BRIEF.md` — Phase 12 ESP integration brief
  (superseded where it conflicts; otherwise valid).
- `docs/PHASE_12_SUMMARY.md` — backend Phase 12 shipped artifact list.
- `docs/AUDIO_BACKEND.md` — backend audio runbook (Phase 10/11).
- `app/api/audio.py`, `app/api/devices.py`,
  `app/api/_auth_dependencies.py` — authoritative source for handler
  behavior. If this document and code disagree, code wins and this
  document MUST be updated.

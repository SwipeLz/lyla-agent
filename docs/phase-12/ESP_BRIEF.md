# Phase 12 — ESP32 Brief: Integration Readiness

This brief covers ESP32-S3 firmware additions needed to integrate with the Phase 12 backend (observability + simple auth + device pairing). Refer to [`docs/PHASE_11_FIRMWARE.md`](../PHASE_11_FIRMWARE.md) for the foundational firmware spec (I2S, WAV files, state machine, OLED rendering).

## What's new in Phase 12 (additive only)

1. **Backend is internet-facing**, not LAN-only — ESP nembak ke domain publik (VPS atau Cloudflare Tunnel), bukan IP lokal. URL pakai `https://`.
2. **HTTPS via `WiFiClientSecure` + `setInsecure()`** — skip cert verification untuk MVP. Trade-off documented below.
3. Config file format extended with `device_token` and structured WiFi credentials
4. Every audio request must include telemetry fields (firmware version, RSSI, battery, recording duration)
5. Heartbeat updated to include all telemetry
6. **`X-Device-Token` header required by default.** Backend ships with `REQUIRE_DEVICE_TOKEN=true`. ESP must always send the header.

Phase 11 firmware spec **stays valid in full**. This brief layers on top.

## Provisioning flow (operator perspective)

1. Operator opens dashboard at `https://<public-domain>` (VPS or Cloudflare Tunnel), logs in (creds dari `.env`, password sudah ter-hash via scrypt)
2. Navigate to `/devices` → click "Pair New Device"
3. Enter device name (e.g. "Lyla Demo Unit") → submit
4. Dashboard shows `config_json` blob in a copyable textarea
5. Operator fills in `wifi.ssid` and `wifi.password` fields locally
6. Save as `/sd/config.json` on SD card via PC card reader
7. Insert SD card into ESP, power on
8. ESP boots, reads config, joins WiFi, ready for commands

**No BLE pairing, no captive portal in MVP.** Manual SD-card transfer only. Trade-off: less polished UX, but trivial firmware (no extra Bluetooth stack, no AP mode).

**Token rotation = pair-ulang.** Tidak ada endpoint rotate-token di backend. Kalau token bocor, operator pair device lagi via dashboard, dapat `config_json` baru, tulis ulang ke SD card.

## `/sd/config.json` schema

```json
{
  "user_id": "9f58e349-63b2-4f30-8fce-277d8cc670d7",
  "device_id": "34074323-28c8-459c-a005-f9d9b8d26ddb",
  "device_code": "TASKBOT-DEMO-001",
  "device_token": "tk_live_abc123def456ghi789jkl012mno345pqr678",
  "base_url": "http://192.168.1.10:8765",
  "wifi": {
    "ssid": "MyHomeWifi",
    "password": "secretpassword"
  },
  "firmware_version": "0.1.0"
}
```

Validation on boot:
- All keys must be present, non-empty
- `base_url` must start with `http://` or `https://`
- `wifi.ssid` non-empty
- If validation fails: render "Config error: <field>" on OLED, halt

ESP firmware **never modifies** this file. Token rotation = operator updates SD card manually.

## Audio request lifecycle (changes)

`POST /agent/audio` multipart fields:

| Field | Phase 11 | Phase 12 | Notes |
|---|---|---|---|
| `file` | required | required | WAV bytes, unchanged |
| `user_id` | required | required | from config |
| `device_id` | required | required | from config |
| `timezone` | optional | optional | hardcode "Asia/Jakarta" |
| `client_request_id` | — | **NEW optional** | UUID v4 generated per request |
| `firmware_version` | — | **NEW optional** | from config |
| `wifi_rssi_dbm` | — | **NEW optional** | `WiFi.RSSI()` |
| `battery_pct` | — | **NEW optional** | -1 if unknown |
| `recording_duration_ms` | — | **NEW optional** | duration of audio capture |

Headers:

| Header | Phase 11 | Phase 12 |
|---|---|---|
| `Content-Type: multipart/form-data` | required | required |
| `X-Device-Token: <device_token>` | — | **NEW, required by default** (backend ships with `REQUIRE_DEVICE_TOKEN=true`) |

If backend rejects with 401 (token missing/invalid): ESP halts, shows "Device tidak terdaftar" on OLED, plays `err_generic.wav`. User must update SD card via re-pair flow.

## Heartbeat (extended)

`POST /devices/{device_code}/status` body — extended schema:

```json
{
  "status": "online",
  "firmware_version": "0.1.0",
  "wifi_rssi_dbm": -55,
  "battery_pct": 80,
  "free_heap_bytes": 234567,
  "uptime_sec": 3600
}
```

Fields beyond `status` are all optional from server's perspective. Send what you have:
- Battery readout requires hardware ADC + voltage divider; if not present, send `-1` or omit
- `free_heap_bytes` from `ESP.getFreeHeap()` — useful for OOM correlation

Schedule:

| Event | Frequency |
|---|---|
| Heartbeat (idle) | every 60s |
| Heartbeat (during recording/playback) | paused |
| WiFi reconnect | every 5s if disconnected, exponential backoff to 30s |
| Audio request timeout | 30s → trigger err_generic + return to IDLE |

## Telemetry implementation sketch

Use Arduino-ESP32 idioms (PlatformIO):

```cpp
String generate_request_id() {
    uint8_t bytes[16];
    esp_fill_random(bytes, 16);
    bytes[6] = (bytes[6] & 0x0F) | 0x40;  // RFC 4122 v4
    bytes[8] = (bytes[8] & 0x3F) | 0x80;
    char buf[37];
    snprintf(buf, sizeof(buf),
        "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
        bytes[0],bytes[1],bytes[2],bytes[3],
        bytes[4],bytes[5],bytes[6],bytes[7],
        bytes[8],bytes[9],bytes[10],bytes[11],
        bytes[12],bytes[13],bytes[14],bytes[15]);
    return String(buf);
}

int read_battery_pct() {
    // For ESP32-S3 with voltage divider on ADC pin
    // Map raw ADC reading to 0-100% based on Li-Po discharge curve
    // Return -1 if no battery (USB-powered build)
    int raw = analogRead(BATTERY_ADC_PIN);
    if (raw < 100) return -1;  // disconnected
    float voltage = raw * 3.3 / 4095.0 * 2.0;  // 2x for divider
    if (voltage > 4.15) return 100;
    if (voltage < 3.30) return 0;
    return (int)((voltage - 3.30) / 0.85 * 100);
}
```

## HTTPS via `WiFiClientSecure` + `setInsecure()`

Backend ada di publik (VPS / Cloudflare Tunnel) → URL pakai `https://`. ESP32 wajib pakai `WiFiClientSecure`, tapi untuk MVP **kita skip cert verification** dengan `setInsecure()`:

```cpp
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

WiFiClientSecure client;
client.setInsecure();  // MVP: skip cert chain validation
HTTPClient http;
http.begin(client, config.base_url + "/agent/audio");
http.addHeader("X-Device-Token", config.device_token);
// ... multipart body, send
```

Trade-off:
- **Plus**: 2 baris perubahan dari versi LAN HTTP. Tidak perlu bundle root CA, tidak perlu update CA store waktu cert rotate.
- **Minus**: rentan MITM kalau attacker bisa intercept jalur ESP→Cloudflare/VPS (butuh akses ke jaringan WiFi atau ISP attack). Untuk demo MVP risiko ini diterima.

Upgrade path post-MVP: bundle Cloudflare/Let's Encrypt root CA bundle ke flash, ganti `setInsecure()` dengan `setCACert(rootCaPem)`. Sekitar 20 baris extra + 5KB flash.

## Error handling table (extended from Phase 11)

| Failure | OLED message | Audio | Recovery |
|---|---|---|---|
| Config file missing/malformed | "Config error: <field>" | (none, halt) | manual SD card replace |
| WiFi can't connect (≤30s) | "WiFi terputus" | beep tone | auto-retry forever, exponential backoff |
| TLS handshake error (DNS / cert / SNI) | "Tidak bisa hubungi server" | err_generic.wav | retry with backoff; if persistent, halt with diagnostic |
| Backend unreachable (timeout) | "Server tidak responsif" | err_generic.wav | return to IDLE, allow retry |
| 401 from `/agent/audio` | "Device tidak terdaftar" | err_generic.wav | halt, manual SD card update via re-pair |
| 5xx from backend | "Server bermasalah, coba lagi" | err_generic.wav | return to IDLE |
| 4xx (other) from backend | "Permintaan ditolak" | err_generic.wav | return to IDLE |
| Bad JSON in response | "Response tidak valid" | err_generic.wav | return to IDLE |
| Protocol version mismatch (`X-Lyla-Protocol != 1`) | "Versi server beda" | err_generic.wav | return to IDLE |

**All OLED messages MUST be Indonesian.** No HTTP codes, no stack traces, no English. ESP firmware is end-user facing.

## Boot sequence (revised)

```
1. Power on
2. OLED init → splash "Lyla starting..."
3. Mount SD card
   ├── failure → "SD card error" (halt, blink LED red)
   └── success → continue
4. Read /sd/config.json
   ├── missing → "Config missing" (halt)
   ├── malformed → "Config error: <field>" (halt)
   └── valid → continue
5. Init I2S input + output
6. Init WiFi using config.wifi.{ssid, password}
   ├── failure within 30s → "WiFi terputus", retry forever (background)
   └── success → continue
7. Send first heartbeat with status="online"
   ├── 401 → halt with "Device tidak terdaftar"
   ├── 5xx → log warning, continue (will retry next heartbeat)
   └── success → continue
8. Play /sd/sounds/greet_hello.wav
9. Show face_neutral on OLED
10. Enter main loop (idle, listening for button)
```

## Recommended dev workflow

1. **Phase 1 — backend smoke (local override)**: temporarily set `REQUIRE_DEVICE_TOKEN=false` in dev env. Skip `X-Device-Token` header. Test happy path with curl/Swagger first. **Revert to `true` before any internet exposure.**
2. **Phase 2 — token enforcement**: flip `REQUIRE_DEVICE_TOKEN=true` (production default). Verify 401 path works. Add header in firmware.
3. **Phase 3 — TLS smoke**: point firmware to public domain (`https://...`), verify `WiFiClientSecure.setInsecure()` connects without crash.
4. **Phase 4 — telemetry validation**: open dashboard `/observability` page. Send a few requests. Verify telemetry fields appear in drill-down.
5. **Phase 5 — heartbeat verification**: power off WiFi for 90s, dashboard should show device offline.
6. **Phase 6 — error injection**: unplug speaker mid-playback, ensure firmware doesn't crash.

## Checklist for ESP firmware author

Boot:
- [ ] Mount SD card, validate `/sd/config.json` schema (all fields present)
- [ ] Connect WiFi using `config.wifi.{ssid, password}`
- [ ] Send opening heartbeat to `/devices/{device_code}/status`
- [ ] Display Indonesian error messages on all OLED failure paths

Per request:
- [ ] Generate UUID v4 as `client_request_id`
- [ ] Read `WiFi.RSSI()` for `wifi_rssi_dbm`
- [ ] Read battery (-1 if no hardware) for `battery_pct`
- [ ] Track `recording_duration_ms` from button-press to button-release
- [ ] Include all telemetry fields in multipart body
- [ ] Send `X-Device-Token` header
- [ ] Verify `X-Lyla-Protocol: 1` response header
- [ ] Parse `directive` field, dispatch on `audio_code`
- [ ] Render `directive.face` and `directive.screen_text` on OLED

Background:
- [ ] Heartbeat every 60s with full telemetry
- [ ] Pause heartbeat during active recording/playback
- [ ] WiFi reconnect with backoff

Error paths:
- [ ] Handle 401 → halt with "Device tidak terdaftar"
- [ ] Handle 5xx → "Server bermasalah" + err_generic
- [ ] Handle network timeout → "Server tidak responsif" + err_generic
- [ ] Never crash on any error; always return to IDLE state

## What's NOT in Phase 12 firmware

- BLE pairing (defer to Phase 14+)
- WiFi captive portal (defer)
- HTTPS with full cert verification (MVP uses `setInsecure()`; root CA bundle planned post-MVP)
- OTA firmware update (defer)
- Battery indicator on OLED (just send to backend, dashboard renders it)
- Wake-word detection (defer)
- Multi-user device sharing
- Audio code namespace expansion (the 7 codes from Phase 11 are frozen)
- Token rotation flow on-device (re-pairing via dashboard + SD card replace is the manual procedure)

## Reference

- [`docs/PHASE_11_ARCHITECTURE.md`](../PHASE_11_ARCHITECTURE.md) — frozen contracts (audio_code enum, face enum, response shape)
- [`docs/PHASE_11_FIRMWARE.md`](../PHASE_11_FIRMWARE.md) — firmware foundation (boot, I2S, state machine)
- [`BACKEND_BRIEF.md`](BACKEND_BRIEF.md) — companion brief for backend changes

## Hand-off

Brief ini lengkap untuk operator ESP firmware. Setelah backend Phase 12 done, operator bisa langsung:
1. Pair device via dashboard
2. Save config to SD
3. Power on ESP
4. Verify heartbeat appears in dashboard `/observability` device grid
5. Test full audio request → see all telemetry in drill-down view

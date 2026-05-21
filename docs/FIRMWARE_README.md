# Firmware Runbook — Lyla / Taskbot ESP32-S3

This document is the operator-facing runbook for building, flashing, and
troubleshooting the ESP32-S3 firmware in `firmware/`.

**Contract source of truth:** [`docs/ESP32_INTEGRATION_CONTRACT.md`](ESP32_INTEGRATION_CONTRACT.md).
**Decision log:** [`docs/ESP32_INTEGRATION_ADR.md`](ESP32_INTEGRATION_ADR.md).
**SD card preparation:** [`firmware/sd_template/README.md`](../firmware/sd_template/README.md).

---

## What this firmware does

A single binary that combines:

1. **Offline emotion engine** (Smooth-v5 baseline): TFT BMO face,
   touch-to-satisfied, MPU6050 shake-to-dizzy, blinking, look-around.
   Always on. Works without internet.
2. **Online voice integration** (Phase 11c): push-to-talk button records
   audio, sends to `POST /agent/audio`, plays the response from SD card
   based on the server's `directive.audio_code`. Falls back to
   `err_generic` + Indonesian on-screen message if WiFi or server fails.

Per ADR-13, the two layers coexist: offline runs always, online activates
only when WiFi is up and the user presses the PTT button.

---

## Source layout

```
firmware/
├── platformio.ini             ; toolchain config
├── sd_template/               ; what to copy onto the microSD card
│   ├── config.json.example
│   └── README.md
└── src/
    ├── config.h               ; pinmap + compile-time constants
    ├── sd_config.h/.cpp       ; reads /config.json from SD
    ├── tft_face.h/.cpp        ; BMO face renderer + server overrides
    ├── audio_capture.h/.cpp   ; INMP441 I2S input
    ├── audio_playback.h/.cpp  ; MAX98357A I2S output, SD WAV + in-memory WAV
    ├── network_client.h/.cpp  ; WiFi + HTTPS, multipart POST, TTS GET, heartbeat
    ├── directive_dispatcher.h/.cpp  ; parses /agent/audio response
    ├── online_state.h/.cpp    ; online tier FSM (Idle/Recording/Sending/etc.)
    └── main.cpp               ; setup() + loop(), button + touch + MPU
```

---

## Prerequisites

### 1. PlatformIO

We use PlatformIO instead of Arduino IDE because it pins library
versions for reproducibility (ADR-7).

Install via VS Code marketplace ("PlatformIO IDE" extension), or
standalone:

```bash
pip install platformio
```

Verify:

```bash
pio --version
# expect: PlatformIO Core, version 6.x or higher
```

### 2. Arduino-ESP32 + USB driver

PlatformIO downloads the toolchain automatically on first build. On
Windows, install the CP210x or CH9102 USB-to-UART driver matching your
ESP32-S3 board.

### 3. Hardware

- ESP32-S3-WROOM-1 dev board with **8 MB PSRAM** (mandatory).
- TFT ILI9341 320×240 SPI, INMP441 mic, MAX98357A speaker amp,
  microSD module, MPU6050, TTP223 touch sensor, push button, status LED.
- Wiring per `taskbot_online_pinmap.md` (also documented in Contract §14
  and `firmware/src/config.h`).
- microSD card formatted FAT32 with `config.json` and `/sounds/*.wav`
  (see `firmware/sd_template/README.md`).
- Backend deployed and reachable over the URL you'll put in
  `config.json`.

---

## Build

From the project root:

```bash
pio run -d firmware
```

Or change into the firmware folder:

```bash
cd firmware
pio run
```

Expected output:

```
Building in release mode
...
Linking .pio/build/esp32-s3-devkitc-1/firmware.elf
Retrieving maximum program size .pio/build/esp32-s3-devkitc-1/firmware.elf
Checking size .pio/build/esp32-s3-devkitc-1/firmware.elf
RAM:   [=         ]  10.5% (used 34xxx bytes from 327680 bytes)
Flash: [====      ]  35.x% (used 1xxxxxx bytes from 4194304 bytes)
========================== [SUCCESS] Took XX.XX seconds ==========================
```

If you see **"flash too small"** or **partition errors**, ensure
`board_build.partitions = huge_app.csv` in `platformio.ini`. The
default is fine for ESP32-S3-WROOM with 4 MB or 8 MB flash.

---

## Flash

Connect the ESP32-S3 over USB. Then:

```bash
pio run -d firmware -t upload
```

PlatformIO auto-detects the serial port. To force a port:

```bash
pio run -d firmware -t upload --upload-port COM5      # Windows
pio run -d firmware -t upload --upload-port /dev/ttyUSB0   # Linux
pio run -d firmware -t upload --upload-port /dev/cu.usbserial-X  # macOS
```

If the chip doesn't enter download mode automatically: hold **BOOT**,
tap **RESET**, release BOOT, retry. Some ESP32-S3-WROOM boards need
this.

---

## Monitor serial logs

```bash
pio device monitor -d firmware -b 115200
```

Filters are configured to decode ESP exception backtraces automatically
(`monitor_filters = direct, esp32_exception_decoder` in
`platformio.ini`).

Expected boot log:

```
[lyla] boot, firmware=0.1.0 protocol=1
[lyla] config ok device_code=TASKBOT-DEMO-001 base_url=https://lyla.example.com
[lyla] wifi connected, ip=192.168.1.123 rssi=-55
[lyla] setup complete; entering main loop
```

If you see `[lyla][err]`, cross-reference the troubleshooting table
below.

---

## First-run procedure (end-to-end)

1. Build & flash the firmware (above).
2. Prepare the SD card per `firmware/sd_template/README.md`. Specifically:
   - Pair the device on the dashboard, copy `config_json` into `/config.json` on the SD.
   - Fill `wifi.ssid` / `wifi.password`.
   - Place 10 WAV files in `/sounds/`.
3. Configure the backend `.env`:
   ```bash
   REQUIRE_DEVICE_TOKEN=true
   DEVICE_API_TOKEN=<paste device.api_token from POST /devices/pair response>
   ```
   Per ADR-11, the global `DEVICE_API_TOKEN` MUST equal the paired device''s
   token for the 1-device MVP.
4. Restart `uvicorn`.
5. Insert the SD card into the ESP32-S3.
6. Power on.

Boot timeline (expected, from cold boot):

| T+    | Event                                            |
|-------|--------------------------------------------------|
| 0.0 s | TFT splash "Lyla starting..."                    |
| 0.2 s | SD mounted, config parsed                        |
| 0.5 s | I2S input + output drivers installed             |
| 1.0 s | WiFi connected (or "Joining WiFi..." persists)   |
| 1.5 s | First heartbeat sent                             |
| 1.8 s | `greet_hello.wav` plays                          |
| 2.5 s | MPU6050 calibration complete                     |
| 3.0 s | Idle, BMO face visible, ready for input          |

Press the PTT button (GPIO18). Expected timeline:

| T+    | Event                                            |
|-------|--------------------------------------------------|
| 0.0 s | Button down, mic starts capturing                |
| ...   | User speaks                                       |
| -     | Button up                                         |
| 0.0 s | `ack_thinking.wav` starts (filler)               |
| 0.2 s | `POST /agent/audio` in flight                    |
| 3.0 s | Server response received                         |
| 3.0 s | TFT face overrides to server `directive.face`    |
| 3.1 s | SD WAV plays (or TTS fetched + played)           |
| ~5 s  | Playback ends, returns to offline emotion        |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| TFT blank, no splash | Power, wiring, or SPI bus mis-init | Check 3V3 to TFT VCC; verify TFT_CS=14, DC=21, RST=47, MOSI=1, SCK=2, MISO=41 |
| `Framebuffer allocation failed` | PSRAM not detected | Verify `BOARD_HAS_PSRAM` build flag set; verify board has PSRAM (S3-WROOM-1 N16R8 or N8R8) |
| `SD card error` on TFT | SD not detected | FAT32 format; check CS=5; share MOSI/SCK/MISO with TFT |
| `Config error: <field>` | Invalid `/config.json` | Check JSON syntax; UUIDs must be lowercase 36-char; `base_url` must start with `http://` or `https://` |
| `WiFi terputus` persists | Wrong SSID/password or WiFi out of range | Edit `wifi.ssid` / `wifi.password` in `/config.json`; SSID is case-sensitive |
| `Tidak bisa hubungi server` | DNS or HTTPS handshake failure | Check `base_url` is reachable from your network; for AWS, verify ALB / Caddy is up; for HTTPS, MVP uses `setInsecure()` so cert validity is not the issue |
| `Server tidak responsif` | Backend timeout or down | Check `uvicorn` logs; verify `/healthz` returns 200 from a browser at the same URL |
| `Device tidak terdaftar` (HTTP 401) | Token mismatch | Verify `DEVICE_API_TOKEN` env on backend equals the device token in `/config.json`; re-pair on dashboard if unsure |
| `Akun belum siap` (HTTP 404) | `user_id` or `device_id` not in DB | Re-pair via dashboard; the pair endpoint always emits valid UUIDs |
| `Versi server beda` | Backend protocol mismatch | Check `X-Lyla-Protocol: 1` header in the response; if server returns a different value, the binary protocol is incompatible — backend upgrade required |
| `Respon tidak valid` | Backend returned malformed JSON | Check `directive` is present in the response; backend bug |
| `File audio hilang` | Missing WAV on SD | Check `/sounds/` contains the 10 required files |
| Audio crackles or stutters | I2S buffer underrun | Check 5V supply to MAX98357A is stable (≥1A); verify wires are short |
| Mic captures only static | INMP441 wired wrong | INMP441 wants 3.3V, not 5V; L/R must be tied to GND for left channel; verify WS=15, BCLK=16, SD=17 |
| BMO face freezes | Online state stuck | Check serial monitor for `[lyla][err]`; reset device |
| Touch sensor unresponsive | TTP223 active polarity | If your module is active-LOW, change `LYLA_TOUCH_ACTIVE_HIGH` to `0` in `config.h` and rebuild |
| Shake doesn''t trigger dizzy | MPU6050 not detected | Check I2C wiring SDA=6, SCL=7; check 3.3V power; serial should print `Calibrating MPU6050...` at boot |
| Compile error: `undefined reference to ...` | Missing library | Run `pio pkg install -d firmware`; check `lib_deps` in `platformio.ini` |
| Compile warning about `arduino-esp32` version | New 3.x core not yet on PlatformIO 6.7 | Either pin `platform = espressif32@6.7.0` exactly, or update PlatformIO platforms via `pio pkg update` |

---

## Common firmware tweaks

### Change PTT button polarity

If your push button is wired with a pullup-to-3V3 (active-HIGH) instead
of pulldown-to-GND with internal pullup, edit `main.cpp`:

```cpp
bool poll_button_pressed_edge() {
  bool raw = (digitalRead(LYLA_PTT_PIN) == HIGH);  // was LOW
  ...
}
```

Same for `poll_button_released_edge`.

### Change recording length cap

Default 30 s. Edit `LYLA_MAX_RECORD_MS` in `config.h`. The PSRAM ceiling
is 60 s safely; beyond that, also bump `LYLA_MAX_RECORD_BYTES` and verify
`heap_caps_malloc(MALLOC_CAP_SPIRAM)` succeeds.

### Change face animations

The Smooth-v5 emotion engine lives entirely in `tft_face.cpp`. Element
helpers (`draw_happy_eyes`, `draw_satisfied_eyes`, etc.) match the
existing offline implementation. Add a new emotion by:
1. Add an enum value to `Emotion` in `tft_face.cpp`.
2. Add the rendering case in `render_emotion_solid`.
3. Wire it from main loop or online state.

### Change polling frequency

Frame rate is 25 FPS via `LYLA_TFT_FRAME_MS = 40`. If you see audible
glitches during recording, lower to 20 FPS (50 ms) — the TFT push uses
SPI shared with SD which may compete with audio I/O on heavy load.

---

## Memory budget at runtime

Approximate peak (Contract §14.1):

| Region | Bytes |
|---|---|
| TFT framebuffer (heap) | 153 600 |
| Audio capture buffer (PSRAM, when recording) | 960 000 |
| TTS playback buffer (PSRAM, when fallback_tts) | up to 600 000 |
| Multipart body (PSRAM, transient) | ~ 962 000 |
| TLS handshake (heap, transient) | ~ 32 000 |

The audio capture buffer and TTS buffer **never coexist**. Capture is
freed before TTS GET. Multipart body is freed after `http.POST`
returns.

Peak PSRAM: ~ 1.6 MB. Peak heap: ~ 220 KB. Both well within ESP32-S3
8 MB PSRAM + 320 KB DRAM budget.

---

## Wiring quick reference (Contract §14)

| Component | Pins |
|---|---|
| TFT ILI9341 | CS=14, DC=21, RST=47, MOSI=1, SCK=2, MISO=41 |
| microSD | CS=5, MOSI=1, SCK=2, MISO=41 (shared SPI bus) |
| Touch sensor | OUT=4 |
| MPU6050 | SDA=6, SCL=7 |
| INMP441 mic | WS=15, BCLK=16, SD=17 (3.3 V VCC only) |
| MAX98357A speaker | LRC=8, BCLK=9, DIN=10 (5 V VIN) |
| Push-to-talk | GPIO18 (INPUT_PULLUP, active LOW) |
| Status LED | GPIO42 via 220 Ω resistor |

---

## Where to file bugs

- Firmware behavior bugs: this repo, mention `[firmware]` in the issue title.
- Backend contract violations: `[contract]` — also append a new ADR.
- AWS deployment issues: `AWS_DEPLOYMENT.md`.

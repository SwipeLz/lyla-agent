# Phase 11 — Firmware Architecture (ESP32-S3)

> **SUPERSEDED IN PART by [`ESP32_INTEGRATION_CONTRACT.md`](ESP32_INTEGRATION_CONTRACT.md).**
> Where this document and the Contract disagree, the Contract wins.
> See [`ESP32_INTEGRATION_ADR.md`](ESP32_INTEGRATION_ADR.md) for the rationale
> behind each resolution. This file is preserved for historical context and for
> sections (hardware pinout, WAV header layout, SD layout) that the Contract
> cross-references.

This document specifies what the **ESP32-S3 firmware** must build to talk to the FastAPI backend. Read [`PHASE_11_ARCHITECTURE.md`](PHASE_11_ARCHITECTURE.md) first for the protocol contract.

## Hardware assumed

| Component | Pinout (suggested, change as you wire) |
|---|---|
| ESP32-S3 dev board | — |
| INMP441 mic (I2S input) | WS=42, SCK=41, SD=2 |
| MAX98357A speaker (I2S output) | LRC=15, BCLK=16, DIN=17 |
| microSD (SPI) | MISO=37, MOSI=35, SCK=36, CS=39 |
| OLED SSD1306 (I2C) | SDA=8, SCL=9 |
| Push-to-talk button | GPIO 0 (with pullup) |
| Status LED (optional) | GPIO 21 |

The **two I2S peripherals** of ESP32-S3 are used independently — one for mic capture, one for speaker output. Don't try to share.

## Suggested toolchain

- **PlatformIO** with Arduino-ESP32 v3.x (recommended) OR ESP-IDF v5.x.
- Arduino-ESP32 has higher-level libs and faster prototyping. ESP-IDF gives finer control over I2S, RTOS tasks, and memory.
- File assumes Arduino-ESP32 idioms; ESP-IDF translation is mostly 1:1.

Required libraries:

| Library | Purpose |
|---|---|
| `WiFi` (built-in) | network stack |
| `HTTPClient` (built-in) | POST/GET to FastAPI |
| `ArduinoJson` v7 | parse `directive` from response |
| `SD` (built-in) | microSD I/O |
| `I2S` (Arduino-ESP32 builtin) | mic + speaker |
| `U8g2` or `Adafruit_SSD1306` | OLED rendering |

## Directory layout on microSD card

```
/sd/
├── sounds/
│   ├── ack_thinking.wav         # "sebentar yaa..." (~1.5s)
│   ├── ack_still_thinking.wav   # "masih dipikir nih..." (~1s)
│   ├── ack_slow_network.wav     # "kayaknya internetnya lambat..." (~1.5s)
│   ├── ok_expense.wav           # "siap, sudah tercatat" (~2s)
│   ├── ok_task.wav              # "task sudah tercatat" (~1.5s)
│   ├── ok_reminder.wav          # "pengingat sudah saya pasang" (~2s)
│   ├── ok_summary.wav           # "ringkasan hari ini" (~1.5s)
│   ├── ok_generic.wav           # "OK" (~1s)
│   ├── err_generic.wav          # "yah maaf, ada kesalahan, coba lagi ya" (~2s)
│   └── greet_hello.wav          # "halo!" (~1s, used at boot)
└── config.json                  # device_id, user_id, base_url, wifi_ssid (boot config)
```

All WAV files: **mono, 16-bit PCM, 16 kHz**. ESP firmware streams these directly to MAX98357A without resampling. Total size ≤2 MB.

## Boot sequence

```
1. Power on
2. Mount SPIFFS (for partitioning) and SD card (for audio cache)
3. Read /sd/config.json → device_id, user_id, base_url, wifi creds
4. Init OLED, show splash "Lyla starting..."
5. Init I2S input + output
6. Connect WiFi, retry on failure with exponential backoff (max 30s)
7. Show face_neutral, play /sd/sounds/greet_hello.wav
8. Enter main loop (idle, listening for button)
```

If SD card is missing or `config.json` is malformed: render error on OLED, blink LED, halt. Do not attempt to start without provisioning.

## Main loop (state machine)

```
[IDLE]
  └── on button press → [RECORDING]

[RECORDING]
  ├── allocate audio buffer (RAM, capped at 60s)
  ├── start I2S input task
  ├── on button release → [SENDING]
  └── on max duration (30s) → [SENDING]

[SENDING]
  ├── trigger filler audio playback ("ack_thinking.wav") on I2S output
  ├── start HTTP POST /agent/audio (multipart upload of buffer)
  ├── show face_thinking on OLED
  ├── on response 200 → [PLAYING_RESPONSE]
  ├── on timeout (30s) or error → [SHOWING_ERROR]

[PLAYING_RESPONSE]
  ├── parse JSON, extract directive
  ├── verify X-Lyla-Protocol: 1 header (else → [SHOWING_ERROR])
  ├── render directive.face on OLED
  ├── render directive.screen_text on OLED
  ├── if directive.audio_code == "fallback_tts":
  │      └── start HTTP GET <directive.fetch_url>, stream-play to I2S output
  ├── else:
  │      └── play /sd/sounds/<directive.audio_code>.wav
  ├── on playback end → [IDLE]

[SHOWING_ERROR]
  ├── play /sd/sounds/err_generic.wav
  ├── show face_sad + error blurb on OLED
  ├── 3s delay, then → [IDLE]
```

The state machine MUST be implemented as a non-blocking task (FreeRTOS task or `loop()` with state variable). I2S playback runs on its own DMA-driven background task; main loop polls state.

## Audio capture details

INMP441 outputs 24-bit samples in I2S Philips standard. ESP32-S3 reads 32-bit slots; pack to 16-bit by right-shifting (drop the bottom 8 bits of the 24-bit sample, then sign-extend).

```c
// pseudo
int32_t sample32;
i2s_read(I2S_NUM_0, &sample32, sizeof(sample32), &bytes_read, portMAX_DELAY);
int16_t sample16 = (int16_t)(sample32 >> 14);  // 24-bit MSB-aligned in 32-bit slot
buffer[i++] = sample16;
```

Buffer size: 16000 samples/s × 2 bytes × 30s max = 960 KB. ESP32-S3 has 512 KB SRAM. Use **PSRAM** (8MB on most S3 boards) for the buffer:

```c
audio_buffer = (int16_t *) ps_malloc(MAX_AUDIO_BYTES);
```

## WAV header for upload

Backend expects valid WAV bytes. Build the 44-byte header on the fly when uploading:

```c
struct WavHeader {
  char riff[4];           // "RIFF"
  uint32_t file_size;     // total - 8
  char wave[4];           // "WAVE"
  char fmt[4];            // "fmt "
  uint32_t fmt_size;      // 16
  uint16_t fmt_format;    // 1 (PCM)
  uint16_t channels;      // 1
  uint32_t sample_rate;   // 16000
  uint32_t byte_rate;     // sample_rate * channels * sample_width
  uint16_t block_align;   // channels * sample_width
  uint16_t bits_per_sample; // 16
  char data[4];           // "data"
  uint32_t data_size;     // raw audio bytes
};
```

Send: header (44 bytes) + raw PCM samples as the `file` field of multipart upload.

## HTTP upload pattern

Arduino-ESP32 `HTTPClient` does not stream multipart natively. Two options:

- **Option A (simple, works for ≤512 KB):** build the multipart body in PSRAM, then `http.POST(body)`.
- **Option B (streaming, no PSRAM peak):** use `HTTPClient::sendRequest("POST", &stream, content_length)` with a custom Stream that emits multipart boundaries + WAV header + PCM bytes on demand.

Pick Option A first. Switch to B if memory pressure shows up in profiling.

```c
// Option A sketch
String boundary = "----LylaBoundary12345";
String preamble = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"user_id\"\r\n\r\n" + USER_ID + "\r\n"
                + "--" + boundary + "\r\nContent-Disposition: form-data; name=\"device_id\"\r\n\r\n" + DEVICE_ID + "\r\n"
                + "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"voice.wav\"\r\n"
                + "Content-Type: audio/wav\r\n\r\n";
String trailer = "\r\n--" + boundary + "--\r\n";

size_t body_size = preamble.length() + sizeof(WavHeader) + audio_data_size + trailer.length();
uint8_t *body = (uint8_t *) ps_malloc(body_size);
// ... assemble body ...
HTTPClient http;
http.begin(BASE_URL "/agent/audio");
http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);
int code = http.POST(body, body_size);
String response = http.getString();
free(body);
```

## Response parsing

Use ArduinoJson v7 with a sized DynamicJsonDocument:

```c
JsonDocument doc;
DeserializationError err = deserializeJson(doc, response);
if (err) { go_to_error(); return; }

const char *audio_code = doc["directive"]["audio_code"];
const char *face = doc["directive"]["face"];
const char *screen_text = doc["directive"]["screen_text"];
const char *fetch_url = doc["directive"]["fetch_url"];  // may be null
```

Drop the JSON document before allocating the audio playback buffer to free heap.

## Audio code dispatch (the core decision)

```c
void play_response(const char *audio_code, const char *fetch_url) {
  if (strcmp(audio_code, "fallback_tts") == 0) {
    if (fetch_url == nullptr) { play_sd("err_generic.wav"); return; }
    stream_play_url(fetch_url);  // HTTP GET, stream-decode, push to I2S
    return;
  }

  // All other audio_codes map 1:1 to /sd/sounds/<code>.wav
  char path[64];
  snprintf(path, sizeof(path), "/sounds/%s.wav", audio_code);
  if (!play_sd(path)) {
    // Unknown code or missing file — defensive fallback
    play_sd("/sounds/ok_generic.wav");
  }
}
```

**No regex, no string matching on `reply`, no NLP.** The server-side classifier already did the work; the firmware is a dumb dispatcher.

## SD card playback

Read WAV file, validate header (RIFF/WAVE, 16kHz mono 16-bit), then DMA-stream samples to I2S output. Most ESP32 SD audio libs (`Audio.h`, `ESP32-audioI2S`) handle this already. Pick one and avoid hand-rolling the WAV parser.

## TTS streaming playback (`fallback_tts`)

Server returns `audio/wav` 24kHz mono. Two playback strategies:

- **Buffer-then-play:** download whole response, write to a temp file or PSRAM blob, then play. Latency = full TTS time + transfer time. Simpler.
- **Stream-while-playing:** start I2S DMA after first ~8 KB, fill buffer as more bytes arrive. Latency = first-byte time. Risky if WiFi stalls (audio underruns sound terrible).

Pick buffer-then-play for v1. The filler audio (`ack_thinking` / `ack_still_thinking`) hides this latency well enough.

```c
void stream_play_url(const char *fetch_url) {
  HTTPClient http;
  String full_url = String(BASE_URL) + fetch_url;
  http.begin(full_url);
  int code = http.GET();
  if (code != 200) { play_sd("/sounds/err_generic.wav"); return; }

  size_t len = http.getSize();
  uint8_t *buf = (uint8_t *) ps_malloc(len);
  http.getStream().readBytes(buf, len);
  http.end();

  // skip 44-byte WAV header, push PCM to I2S
  i2s_write_pcm(buf + 44, len - 44, 24000);
  free(buf);
}
```

Always set a timeout on `HTTPClient`: `http.setTimeout(15000);` so a stuck server doesn't hang the firmware.

## OLED rendering

```c
void render_face(const char *face) {
  if (strcmp(face, "happy") == 0) draw_pixmap(face_happy_xbm, ...);
  else if (strcmp(face, "sad") == 0) draw_pixmap(face_sad_xbm, ...);
  else if (strcmp(face, "thinking") == 0) start_dots_animation();
  else draw_pixmap(face_neutral_xbm, ...);
}

void render_screen_text(const char *text) {
  if (text == nullptr) return;
  oled.clearBuffer();
  oled.setFont(u8g2_font_6x10_tf);
  oled.drawStr(0, 30, text);
  oled.sendBuffer();
}
```

Pre-bake face pixmaps as `XBM` arrays in firmware (small, fast). Don't load images from SD on every response — too slow.

## Filler audio orchestration

The trick is **start filler the instant the request goes out**, parallel to the network call:

```c
void send_command_async() {
  // Both happen concurrently:
  start_play_filler("/sounds/ack_thinking.wav");  // I2S task

  // HTTP POST runs on main task; I2S DMA runs in background
  send_audio_to_backend();

  // After 3s, optionally start ack_still_thinking
  if (response_pending && elapsed > 3000) {
    queue_play_filler("/sounds/ack_still_thinking.wav");
  }
}
```

When the response arrives, **fade out** the filler (don't hard-cut — clicky sounds are bad UX) before playing the resolution audio.

## Error handling

| Failure | Detection | Firmware action |
|---|---|---|
| WiFi disconnected | `WiFi.status() != WL_CONNECTED` | OLED "WiFi terputus", LED red blink, retry every 5s |
| HTTP timeout | `http.GET()/POST()` returns negative | Play `err_generic.wav`, OLED "Coba lagi sebentar", → IDLE |
| Bad protocol version | `X-Lyla-Protocol != "1"` | Play `err_generic.wav`, OLED "Versi server beda", → IDLE |
| Bad JSON shape | `deserializeJson` error or missing keys | Play `err_generic.wav`, OLED "Respon aneh", → IDLE |
| Missing SD file | `SD.exists()` returns false | Beep, OLED "File audio hilang", → IDLE |
| Out of memory | `ps_malloc` returns null | Reboot the ESP (last resort) |

The firmware **MUST NOT** crash. Reboot is acceptable as last resort but avoid; it surprises the user.

## Power and timing budget

| Phase | Duration | CPU |
|---|---|---|
| Idle | continuous | low (deep sleep optional later) |
| Recording | up to 30s | medium (I2S DMA + ADC) |
| Sending | ~3-5s | medium (HTTP + I2S filler in parallel) |
| Playing response | ~2-12s | medium-high (HTTP GET + I2S decode) |

For battery-powered builds, defer deep sleep to Phase 12. v1 assumes USB power.

## Provisioning (one-time, before deployment)

`/sd/config.json`:

```json
{
  "device_id": "34074323-28c8-459c-a005-f9d9b8d26ddb",
  "user_id": "9f58e349-63b2-4f30-8fce-277d8cc670d7",
  "base_url": "http://192.168.1.10:8765",
  "wifi_ssid": "MyWifi",
  "wifi_password": "secret",
  "device_token": ""
}
```

> **STALE — see [`ESP32_INTEGRATION_CONTRACT.md`](ESP32_INTEGRATION_CONTRACT.md) §2.3.**
> Phase 12 made `device_token` **required** and the schema moved to a structured
> `wifi: {ssid, password}` object. The example above is preserved for historical
> context only. Use the Contract schema in real provisioning.

`device_token` is reserved for future hardware-auth (Phase 13+); leave empty.

> **STALE — superseded by Phase 12.** `device_token` is **mandatory and
> enforced** by `app/api/_auth_dependencies.require_device_token` when
> `REQUIRE_DEVICE_TOKEN=true` (default in production). Get the value from
> `POST /devices/pair`. Authoritative reference:
> [`ESP32_INTEGRATION_CONTRACT.md`](ESP32_INTEGRATION_CONTRACT.md) §3.

The user runs `python -m scripts.seed_dev` once on the backend, copies the printed UUIDs into this JSON, and writes the JSON to the SD card via PC. Firmware never modifies this file.

## Recording the pre-recorded WAV files

For first version, record yourself or use a free TTS (Google Cloud TTS web UI, Microsoft Edge "read aloud", ElevenLabs free tier) and export. Specs:

- Mono, 16-bit PCM, 16 kHz sample rate
- File size <100 KB each (~3s of speech)
- Use `ffmpeg` to enforce specs:
  ```
  ffmpeg -i source.wav -ac 1 -ar 16000 -sample_fmt s16 ok_expense.wav
  ```

Test playback on PC first (Windows Media Player handles WAV PCM 16-bit perfectly), then copy to SD card.

## Updating audio packs without reflashing

Pop SD card → mount on PC → drop new WAV → reinsert. Firmware reads from SD on each playback, no caching, no version check.

For OTA audio updates: defer to Phase 13. Don't over-engineer.

## Security considerations

> **STALE — superseded by Phase 12 + Contract §3, §13.** The bullets below
> reflect Phase 11's pre-auth posture and are kept for historical context only.
> Current contract: HTTPS via `WiFiClientSecure.setInsecure()` is the MVP
> default for internet-facing deployments, and `device_token` is enforced.

- **HTTP not HTTPS** in v1 because cert handling on ESP32 is annoying. WiFi must be trusted (LAN only). For production deploy: switch to HTTPS, embed CA bundle in PROGMEM.
- `device_token` not enforced server-side yet; Phase 11 ships without auth. Phase 13 adds it.
- WAV files on SD card: anyone with physical access can swap them. Mitigation deferred.

## Testing the firmware

Without ESP hardware:

- **Unit-test the audio_code dispatcher** in a tiny C++ project on PC; mock SD + HTTP.
- **Unit-test the JSON parser** with sample server responses.

With ESP hardware:

- Manual smoke: button → record → check OLED face changes → check audio plays.
- Latency measurement: instrument `Serial.print(millis())` at each state transition; target <5s for `ok_*` codes, <12s for `fallback_tts`.

## Out of scope for firmware Phase 11

- Wake-word ("Hey Lyla").
- Continuous conversation.
- Battery / sleep modes.
- HTTPS.
- OTA firmware updates.
- Audio compression (Opus, AAC).
- Visual face animations beyond static pixmaps.
- Multi-language UI (Indonesian only).

## Suggested file structure (PlatformIO project)

```
firmware/
├── platformio.ini
├── data/                   # SPIFFS contents (if used)
└── src/
    ├── main.cpp            # state machine + setup()/loop()
    ├── config.h            # pins, constants
    ├── audio_capture.cpp   # I2S input, INMP441 read
    ├── audio_capture.h
    ├── audio_playback.cpp  # I2S output, MAX98357A write, WAV parser
    ├── audio_playback.h
    ├── network.cpp         # HTTPClient wrapper, multipart builder
    ├── network.h
    ├── directive.cpp       # parse + dispatch on audio_code
    ├── directive.h
    ├── ui_oled.cpp         # face pixmaps + screen_text rendering
    ├── ui_oled.h
    ├── sd_audio.cpp        # SD mount, WAV file enumeration
    └── sd_audio.h
```

Reference implementations and example code: provided after this phase ships. Focus first on getting the protocol right; firmware code is mechanical once the contract is clear.

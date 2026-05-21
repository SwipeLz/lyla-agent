// firmware/src/config.h
// Pin map + compile-time constants for the Taskbot/BMO ESP32-S3 firmware.
// Pin assignment is normative and matches:
//   - taskbot_online_pinmap.md (operator-facing wiring guide)
//   - docs/ESP32_INTEGRATION_CONTRACT.md §14 (binding contract)
// Modify pins ONLY if you also re-validate the offline emotion engine.

#pragma once

#include <Arduino.h>

// 1. TFT ILI9341 320x240 (offline + online face renderer)
#define LYLA_TFT_CS     14
#define LYLA_TFT_DC     21
#define LYLA_TFT_RST    47
#define LYLA_TFT_MOSI    1
#define LYLA_TFT_SCK     2
#define LYLA_TFT_MISO   41

#define LYLA_TFT_WIDTH        320
#define LYLA_TFT_HEIGHT       240
#define LYLA_TFT_SPI_HZ       27000000UL
#define LYLA_TFT_FRAME_MS     40
#define LYLA_TFT_TRANSITION_MS 360

// Face region of interest (matches Smooth-v5).
#define LYLA_FACE_ROI_X       18
#define LYLA_FACE_ROI_Y       48
#define LYLA_FACE_ROI_W      284
#define LYLA_FACE_ROI_H      160

// Server screen_text region (below the face). Cleared on online_idle.
#define LYLA_TEXT_ROI_X        4
#define LYLA_TEXT_ROI_Y      210
#define LYLA_TEXT_ROI_W      312
#define LYLA_TEXT_ROI_H       28

// 2. Offline sensors (Smooth-v5 inputs; do NOT change)
#define LYLA_TOUCH_PIN         4
#define LYLA_TOUCH_ACTIVE_HIGH 1

#define LYLA_I2C_SDA           6
#define LYLA_I2C_SCL           7

// 3. INMP441 microphone (I2S input, port 0)
#define LYLA_MIC_I2S_NUM       I2S_NUM_0
#define LYLA_MIC_WS           15
#define LYLA_MIC_BCLK         16
#define LYLA_MIC_SD           17
#define LYLA_MIC_SAMPLE_RATE 16000
#define LYLA_MIC_BITS_PER_SAMPLE 16

// 4. MAX98357A speaker (I2S output, port 1).
// Sample rate is dynamic: 16 kHz for SD-card files, 24 kHz for Gemini TTS.
#define LYLA_SPK_I2S_NUM       I2S_NUM_1
#define LYLA_SPK_LRC           8
#define LYLA_SPK_BCLK          9
#define LYLA_SPK_DIN          10

// 5. microSD (on-board SDMMC slot on Freenove ESP32-S3 WROOM).
// 1-bit SDMMC mode at the dedicated peripheral pins. NOT shared with
// the TFT SPI bus, so there is no bus contention during simultaneous
// audio playback + display refresh.
#define LYLA_SD_CLK   39
#define LYLA_SD_CMD   38
#define LYLA_SD_D0    40

// 6. Push-to-talk + status LED
#define LYLA_PTT_PIN          18
#define LYLA_LED_PIN          42

// 7. Audio buffer ceilings (Contract §14.1)
// 30 s record cap = 30 * 16000 samples * 2 bytes = 960000 bytes.
#define LYLA_MAX_RECORD_MS         30000
#define LYLA_MIN_RECORD_MS           300
#define LYLA_MAX_RECORD_BYTES   (LYLA_MAX_RECORD_MS * (LYLA_MIC_SAMPLE_RATE / 1000) * 2)

// 12 s TTS playback cap at 24 kHz mono = 576000 bytes.
#define LYLA_MAX_TTS_BYTES        600000
#define LYLA_MULTIPART_OVERHEAD_BYTES 2048

// 8. Network + timing budgets (Contract §4.2, §6.4, §8.4, §9.4)
#define LYLA_HTTP_AUDIO_TIMEOUT_MS    30000
#define LYLA_HTTP_TTS_TIMEOUT_MS      15000
#define LYLA_HTTP_HEARTBEAT_TIMEOUT_MS 10000
#define LYLA_WIFI_BACKOFF_INITIAL_MS   1000
#define LYLA_WIFI_BACKOFF_MAX_MS      30000
#define LYLA_HEARTBEAT_INTERVAL_MS    60000
#define LYLA_OFFLINE_NOTICE_MS         2000

// 9. Compile-time identity (overridden by platformio.ini build_flags)
#ifndef LYLA_FIRMWARE_VERSION
#define LYLA_FIRMWARE_VERSION "0.1.0"
#endif

#ifndef LYLA_PROTOCOL_VERSION
#define LYLA_PROTOCOL_VERSION "1"
#endif

#define LYLA_USER_AGENT "Lyla-ESP32S3/" LYLA_FIRMWARE_VERSION

// 10. Logging helpers
#define LYLA_LOG(fmt, ...)  Serial.printf("[lyla] " fmt "\n", ##__VA_ARGS__)
#define LYLA_WARN(fmt, ...) Serial.printf("[lyla][warn] " fmt "\n", ##__VA_ARGS__)
#define LYLA_ERR(fmt, ...)  Serial.printf("[lyla][err]  " fmt "\n", ##__VA_ARGS__)

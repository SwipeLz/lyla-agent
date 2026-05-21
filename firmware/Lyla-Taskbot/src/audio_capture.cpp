#include "audio_capture.h"

#include <driver/i2s.h>
#include <esp_heap_caps.h>

#include "config.h"

namespace lyla {

namespace {

uint8_t* g_buffer = nullptr;
size_t g_capacity_bytes = 0;
size_t g_write_offset = 0;
bool g_running = false;
bool g_installed = false;
uint16_t g_last_peak = 0;

constexpr size_t kReadChunkSamples = 512;

bool install_i2s_driver() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = LYLA_MIC_SAMPLE_RATE;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 8;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;
  cfg.tx_desc_auto_clear = false;
  cfg.fixed_mclk = 0;

  if (i2s_driver_install(LYLA_MIC_I2S_NUM, &cfg, 0, nullptr) != ESP_OK) {
    return false;
  }

  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = LYLA_MIC_BCLK;
  pins.ws_io_num = LYLA_MIC_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = LYLA_MIC_SD;
  if (i2s_set_pin(LYLA_MIC_I2S_NUM, &pins) != ESP_OK) {
    i2s_driver_uninstall(LYLA_MIC_I2S_NUM);
    return false;
  }
  i2s_zero_dma_buffer(LYLA_MIC_I2S_NUM);
  return true;
}

}

bool audio_capture_init() {
  if (g_installed) return true;
  if (!install_i2s_driver()) {
    LYLA_ERR("audio_capture: i2s install failed");
    return false;
  }
  g_installed = true;
  return true;
}

void audio_capture_start() {
  if (!g_installed) return;
  if (g_buffer == nullptr) {
    g_capacity_bytes = LYLA_MAX_RECORD_BYTES;
    g_buffer = (uint8_t*)heap_caps_malloc(g_capacity_bytes, MALLOC_CAP_SPIRAM);
    if (g_buffer == nullptr) {
      LYLA_ERR("audio_capture: ps_malloc failed (%u bytes)", (unsigned)g_capacity_bytes);
      g_capacity_bytes = 0;
      return;
    }
  }
  g_write_offset = 0;
  i2s_start(LYLA_MIC_I2S_NUM);
  g_running = true;
}

bool audio_capture_pump() {
  if (!g_running || g_buffer == nullptr) return false;
  if (g_write_offset >= g_capacity_bytes) {
    return false;
  }
  int32_t raw[kReadChunkSamples];
  size_t bytes_read = 0;
  esp_err_t err = i2s_read(LYLA_MIC_I2S_NUM, raw, sizeof(raw), &bytes_read,
                           pdMS_TO_TICKS(20));
  if (err != ESP_OK || bytes_read == 0) {
    return true;
  }
  size_t samples = bytes_read / sizeof(int32_t);
  size_t bytes_pending = samples * sizeof(int16_t);
  if (g_write_offset + bytes_pending > g_capacity_bytes) {
    samples = (g_capacity_bytes - g_write_offset) / sizeof(int16_t);
    bytes_pending = samples * sizeof(int16_t);
  }
  int16_t* dst = reinterpret_cast<int16_t*>(g_buffer + g_write_offset);
  uint16_t peak = 0;
  for (size_t i = 0; i < samples; ++i) {
    int32_t s = raw[i] >> 14;
    if (s > 32767) s = 32767;
    if (s < -32768) s = -32768;
    int16_t v = (int16_t)s;
    dst[i] = v;
    uint16_t a = (uint16_t)(v < 0 ? -v : v);
    if (a > peak) peak = a;
  }
  g_last_peak = peak;
  g_write_offset += bytes_pending;
  return true;
}

size_t audio_capture_stop() {
  if (!g_running) return g_write_offset;
  i2s_stop(LYLA_MIC_I2S_NUM);
  g_running = false;
  return g_write_offset;
}

const uint8_t* audio_capture_buffer() {
  return g_buffer;
}

size_t audio_capture_size_bytes() {
  return g_write_offset;
}

void audio_capture_release() {
  if (g_buffer != nullptr) {
    heap_caps_free(g_buffer);
    g_buffer = nullptr;
  }
  g_capacity_bytes = 0;
  g_write_offset = 0;
}

uint32_t audio_capture_sample_rate() {
  return LYLA_MIC_SAMPLE_RATE;
}

}

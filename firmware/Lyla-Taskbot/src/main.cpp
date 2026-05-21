// firmware/src/main.cpp
// Boot + main loop. Wires offline emotion engine + online voice integration.
// Boot sequence per Contract §10; coexistence per ADR-13.

#include <Arduino.h>
#include <MPU6050_tockn.h>
#include <Wire.h>

#include "audio_capture.h"
#include "audio_playback.h"
#include "config.h"
#include "directive_dispatcher.h"
#include "network_client.h"
#include "online_state.h"
#include "sd_config.h"
#include "tft_face.h"

namespace {

lyla::DeviceConfig g_cfg;
MPU6050 g_mpu(Wire);
bool g_mpu_ready = false;

float g_calib_x = 0.0f, g_calib_y = 0.0f;
float g_last_ax = 0.0f, g_last_ay = 0.0f, g_last_az = 0.0f;
float g_shake_filtered = 0.0f;
unsigned long g_last_shake_at = 0;
constexpr float kShakeTrigger = 17.0f;
constexpr unsigned long kShakeLockoutMs = 1100;

bool g_last_touch_raw = false;
bool g_last_touch_stable = false;
unsigned long g_touch_changed_at = 0;
unsigned long g_last_touch_at = 0;
constexpr unsigned long kTouchDebounceMs = 45;
constexpr unsigned long kSatisfiedHoldMs = 1400;

bool g_last_button_state = false;
unsigned long g_button_changed_at = 0;
constexpr unsigned long kButtonDebounceMs = 30;

unsigned long g_last_frame_at = 0;

bool read_touch_stable() {
  bool raw = digitalRead(LYLA_TOUCH_PIN);
#if LYLA_TOUCH_ACTIVE_HIGH
  bool active = raw;
#else
  bool active = !raw;
#endif
  unsigned long now = millis();
  if (active != g_last_touch_raw) {
    g_last_touch_raw = active;
    g_touch_changed_at = now;
  }
  if ((now - g_touch_changed_at) >= kTouchDebounceMs) {
    g_last_touch_stable = active;
  }
  return g_last_touch_stable;
}

void update_mpu() {
  if (!g_mpu_ready) return;
  g_mpu.update();
  float ax = g_mpu.getAccX();
  float ay = g_mpu.getAccY();
  float az = g_mpu.getAccZ();
  float raw_shake = (fabsf(ax - g_last_ax) + fabsf(ay - g_last_ay) +
                    fabsf(az - g_last_az)) * 10.0f;
  g_shake_filtered = g_shake_filtered * 0.70f + raw_shake * 0.30f;
  g_last_ax = ax;
  g_last_ay = ay;
  g_last_az = az;
}

void calibrate_mpu() {
  lyla::show_status_message("BMO", "Calibrating MPU6050...");
  float sx = 0.0f, sy = 0.0f;
  for (int i = 0; i < 100; ++i) {
    g_mpu.update();
    sx += g_mpu.getAngleX();
    sy += g_mpu.getAngleY();
    delay(8);
  }
  g_calib_x = sx / 100.0f;
  g_calib_y = sy / 100.0f;
  g_mpu.update();
  g_last_ax = g_mpu.getAccX();
  g_last_ay = g_mpu.getAccY();
  g_last_az = g_mpu.getAccZ();
  g_shake_filtered = 0.0f;
  g_mpu_ready = true;
}

void halt_with_message(const char* line1, const char* line2) {
  lyla::show_status_message(line1, line2);
  pinMode(LYLA_LED_PIN, OUTPUT);
  for (;;) {
    digitalWrite(LYLA_LED_PIN, HIGH);
    delay(400);
    digitalWrite(LYLA_LED_PIN, LOW);
    delay(400);
  }
}

bool poll_button_pressed_edge() {
  bool raw = (digitalRead(LYLA_PTT_PIN) == LOW);
  unsigned long now = millis();
  if (raw != g_last_button_state) {
    if (now - g_button_changed_at >= kButtonDebounceMs) {
      g_button_changed_at = now;
      bool prev = g_last_button_state;
      g_last_button_state = raw;
      return raw && !prev;
    }
  } else {
    g_button_changed_at = now;
  }
  return false;
}

bool poll_button_released_edge() {
  bool raw = (digitalRead(LYLA_PTT_PIN) == LOW);
  unsigned long now = millis();
  if (raw != g_last_button_state) {
    if (now - g_button_changed_at >= kButtonDebounceMs) {
      g_button_changed_at = now;
      bool prev = g_last_button_state;
      g_last_button_state = raw;
      return !raw && prev;
    }
  } else {
    g_button_changed_at = now;
  }
  return false;
}

}

void setup() {
  Serial.begin(115200);
  delay(200);
  LYLA_LOG("boot, firmware=%s protocol=%s", LYLA_FIRMWARE_VERSION, LYLA_PROTOCOL_VERSION);

  pinMode(LYLA_TOUCH_PIN, INPUT);
  pinMode(LYLA_PTT_PIN, INPUT_PULLUP);
  pinMode(LYLA_LED_PIN, OUTPUT);
  digitalWrite(LYLA_LED_PIN, LOW);

  Wire.begin(LYLA_I2C_SDA, LYLA_I2C_SCL);

  if (!lyla::init_tft()) {
    halt_with_message("BMO", "TFT init failed");
  }
  lyla::show_status_message("BMO", "Lyla starting...");
  delay(400);

  auto cfg_outcome = lyla::load_device_config(g_cfg);
  if (cfg_outcome.result != lyla::ConfigLoadResult::Ok) {
    String msg = lyla::config_load_result_message(cfg_outcome);
    if (cfg_outcome.detail.length() > 0) {
      msg += ": ";
      msg += cfg_outcome.detail;
    }
    halt_with_message("BMO", msg.c_str());
  }
  LYLA_LOG("config ok device_code=%s base_url=%s",
           g_cfg.device_code.c_str(), g_cfg.base_url.c_str());

  if (!lyla::audio_capture_init()) {
    halt_with_message("BMO", "Audio init error");
  }
  if (!lyla::audio_playback_init()) {
    halt_with_message("BMO", "Audio init error");
  }

  lyla::show_status_message("BMO", "Joining WiFi...");
  lyla::network_init(g_cfg);
  bool wifi_ok = lyla::network_wifi_connect(15000);
  if (wifi_ok) {
    if (!lyla::network_post_heartbeat(g_cfg, true)) {
      LYLA_WARN("first heartbeat failed (non-fatal)");
    }
  } else {
    LYLA_WARN("starting offline-only; wifi will retry in background");
  }

  lyla::audio_playback_play_sd("/sounds/greet_hello.wav");

  g_mpu.begin();
  calibrate_mpu();

  lyla::clear_status_message();
  lyla::online_init(g_cfg);
  g_last_button_state = (digitalRead(LYLA_PTT_PIN) == LOW);
  g_button_changed_at = millis();
  randomSeed((uint32_t)esp_random());
  LYLA_LOG("setup complete; entering main loop");
}

void loop() {
  unsigned long now = millis();

  update_mpu();
  bool touched = read_touch_stable();
  if (touched) {
    g_last_touch_at = now;
  }

  bool shake_hit = false;
  if (g_mpu_ready &&
      (now - g_last_shake_at > kShakeLockoutMs) &&
      g_shake_filtered > kShakeTrigger) {
    shake_hit = true;
    g_last_shake_at = now;
  }

  lyla::offline_dispatch_inputs(touched, shake_hit);

  if (poll_button_pressed_edge()) {
    lyla::online_on_button_pressed();
  }
  if (poll_button_released_edge()) {
    lyla::online_on_button_released();
  }

  lyla::online_loop(now);
  lyla::update_offline_inputs();

  if (now - g_last_frame_at >= LYLA_TFT_FRAME_MS) {
    g_last_frame_at = now;
    lyla::render_frame();
  }
}

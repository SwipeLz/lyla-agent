#include "online_state.h"

#include "audio_capture.h"
#include "audio_playback.h"
#include "config.h"
#include "directive_dispatcher.h"
#include "network_client.h"
#include "tft_face.h"

namespace lyla {

namespace {

const DeviceConfig* g_cfg = nullptr;

OnlineState g_state = OnlineState::Idle;
unsigned long g_state_entered_at = 0;
unsigned long g_record_started_at = 0;
unsigned long g_last_heartbeat_at = 0;

bool g_button_held = false;

const char* g_halt_msg = nullptr;

void transition(OnlineState next) {
  g_state = next;
  g_state_entered_at = millis();
  set_offline_input_suppressed(next != OnlineState::Idle);
}

void show_status_for_seconds(const char* msg, unsigned long ms) {
  show_status_message_persistent(msg);
  (void)ms;
}

void enter_error(const char* msg) {
  audio_playback_play_sd("/sounds/err_generic.wav");
  set_server_face_override(ServerFace::Sad, String());
  show_status_for_seconds(msg, 3000);
  transition(OnlineState::ShowingError);
}

void enter_offline_notice() {
  audio_playback_play_sd("/sounds/err_generic.wav");
  set_server_face_override(ServerFace::Sad, String());
  show_status_for_seconds("Tidak ada internet", LYLA_OFFLINE_NOTICE_MS);
  transition(OnlineState::ShowingOfflineNotice);
}

const char* indonesian_for_status(int http_status) {
  if (http_status == 401) return "Device tidak terdaftar";
  if (http_status == 404) return "Akun belum siap";
  if (http_status == 413) return "Rekaman terlalu panjang";
  if (http_status == 422) return "Permintaan ditolak";
  if (http_status == 400) return "Rekaman bermasalah";
  if (http_status == 502) return "Coba lagi sebentar";
  if (http_status >= 500) return "Server bermasalah, coba lagi";
  if (http_status >= 400) return "Permintaan ditolak";
  return "Coba lagi sebentar";
}

bool is_halt_status(int http_status) {
  return http_status == 401 || http_status == 404;
}

void send_audio_and_play(uint32_t recording_duration_ms) {
  if (g_cfg == nullptr) {
    enter_error("Config error");
    return;
  }
  if (!network_wifi_is_connected()) {
    audio_capture_release();
    enter_offline_notice();
    return;
  }

  audio_playback_play_sd("/sounds/ack_thinking.wav");

  AudioRequestTelemetry tele = {};
  tele.client_request_id = network_generate_uuid_v4();
  tele.wifi_rssi_dbm = network_wifi_rssi();
  tele.battery_pct = -1;
  tele.recording_duration_ms = recording_duration_ms;

  AudioPostResult res = network_post_audio(*g_cfg,
                                           audio_capture_buffer(),
                                           audio_capture_size_bytes(),
                                           audio_capture_sample_rate(),
                                           tele);

  audio_capture_release();

  if (res.http_status == 200) {
    if (!res.protocol_version_ok) {
      enter_error("Versi server beda");
      return;
    }
    Directive d;
    if (!directive_parse(res.body, d)) {
      enter_error("Respon tidak valid");
      return;
    }
    transition(OnlineState::PlayingResponse);
    directive_dispatch(*g_cfg, d);
    transition(OnlineState::Idle);
    clear_server_face_override();
    clear_status_message();
    return;
  }

  if (res.http_status <= 0) {
    if (res.error.length() > 0) {
      LYLA_WARN("audio post network err: %s", res.error.c_str());
    }
    enter_error("Server tidak responsif");
    return;
  }

  if (is_halt_status(res.http_status)) {
    online_request_halt(indonesian_for_status(res.http_status));
    return;
  }

  enter_error(indonesian_for_status(res.http_status));
}

}

void online_init(const DeviceConfig& cfg) {
  g_cfg = &cfg;
  g_state = OnlineState::Idle;
  g_state_entered_at = millis();
  g_last_heartbeat_at = 0;
  g_button_held = false;
}

void online_on_button_pressed() {
  if (g_state != OnlineState::Idle) return;
  if (g_cfg == nullptr) return;
  if (!network_wifi_is_connected()) {
    enter_offline_notice();
    return;
  }
  if (!audio_capture_init()) {
    enter_error("Audio init error");
    return;
  }
  audio_capture_start();
  g_record_started_at = millis();
  g_button_held = true;
  transition(OnlineState::Recording);
}

void online_on_button_released() {
  if (g_state != OnlineState::Recording) {
    g_button_held = false;
    return;
  }
  g_button_held = false;
  uint32_t duration_ms = (uint32_t)(millis() - g_record_started_at);
  size_t recorded = audio_capture_stop();
  if (recorded == 0 || duration_ms < LYLA_MIN_RECORD_MS) {
    audio_capture_release();
    transition(OnlineState::Idle);
    return;
  }
  transition(OnlineState::Sending);
  send_audio_and_play(duration_ms);
}

void online_loop(unsigned long now) {
  network_wifi_loop();

  switch (g_state) {
    case OnlineState::Idle: {
      if (now - g_last_heartbeat_at >= LYLA_HEARTBEAT_INTERVAL_MS) {
        g_last_heartbeat_at = now;
        if (g_cfg != nullptr && network_wifi_is_connected()) {
          (void)network_post_heartbeat(*g_cfg, true);
        }
      }
      break;
    }
    case OnlineState::Recording: {
      if (g_button_held) {
        bool ok = audio_capture_pump();
        if (!ok) {
          uint32_t dur = (uint32_t)(now - g_record_started_at);
          audio_capture_stop();
          g_button_held = false;
          if (audio_capture_size_bytes() > 0 && dur >= LYLA_MIN_RECORD_MS) {
            transition(OnlineState::Sending);
            send_audio_and_play(dur);
          } else {
            audio_capture_release();
            transition(OnlineState::Idle);
          }
        }
        if (now - g_record_started_at >= LYLA_MAX_RECORD_MS) {
          online_on_button_released();
        }
      }
      break;
    }
    case OnlineState::Sending:
    case OnlineState::PlayingResponse:
      break;
    case OnlineState::ShowingError:
      if (now - g_state_entered_at >= 3000) {
        clear_server_face_override();
        clear_status_message();
        transition(OnlineState::Idle);
      }
      break;
    case OnlineState::ShowingOfflineNotice:
      if (now - g_state_entered_at >= LYLA_OFFLINE_NOTICE_MS) {
        clear_server_face_override();
        clear_status_message();
        transition(OnlineState::Idle);
      }
      break;
    case OnlineState::Halted:
      break;
  }
}

OnlineState online_current_state() {
  return g_state;
}

bool online_is_active() {
  return g_state != OnlineState::Idle && g_state != OnlineState::Halted;
}

void online_request_halt(const char* indonesian_msg) {
  g_halt_msg = indonesian_msg;
  set_server_face_override(ServerFace::Sad, String());
  show_status_message_persistent(indonesian_msg ? indonesian_msg : "Halt");
  transition(OnlineState::Halted);
  pinMode(LYLA_LED_PIN, OUTPUT);
  digitalWrite(LYLA_LED_PIN, HIGH);
}

}

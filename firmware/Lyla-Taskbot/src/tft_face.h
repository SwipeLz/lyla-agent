// firmware/src/tft_face.h
// BMO face renderer (Smooth-v5 emotion engine) + server face override layer.
// Per ADR-13: offline emotion runs always; server directive.face becomes a
// temporary override during PLAYING_RESPONSE. Reverts on online_idle.

#pragma once

#include <Arduino.h>

namespace lyla {

enum class ServerFace : uint8_t {
  None = 0,
  Happy,
  Sad,
  Thinking,
  Neutral,
};

bool init_tft();

void update_offline_inputs();

void render_frame();

void set_server_face_override(ServerFace face, const String& screen_text);

void clear_server_face_override();

void show_status_message(const char* line1, const char* line2);

void show_status_message_persistent(const char* msg);

void clear_status_message();

void set_offline_input_suppressed(bool suppressed);

void offline_dispatch_inputs(bool touched, bool shake_detected);

}

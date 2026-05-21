// firmware/src/online_state.h
// Online tier state machine (Contract §12, ADR-13).
// Coexists with offline emotion engine; suppresses offline input transitions
// while a voice request is in flight. WiFi-down falls back to offline-only.

#pragma once

#include <Arduino.h>

#include "sd_config.h"

namespace lyla {

enum class OnlineState : uint8_t {
  Idle = 0,
  Recording,
  Sending,
  PlayingResponse,
  ShowingError,
  ShowingOfflineNotice,
  Halted,
};

void online_init(const DeviceConfig& cfg);

void online_loop(unsigned long now);

void online_on_button_pressed();

void online_on_button_released();

OnlineState online_current_state();

bool online_is_active();

void online_request_halt(const char* indonesian_msg);

}

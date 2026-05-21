// firmware/src/directive_dispatcher.h
// Parses /agent/audio response and dispatches to playback + face override.
// Implements Contract §7 (audio_code enum, face enum, fetch_url handling).

#pragma once

#include <Arduino.h>

#include "sd_config.h"
#include "tft_face.h"

namespace lyla {

enum class AudioCode : uint8_t {
  Unknown = 0,
  OkExpense,
  OkTask,
  OkReminder,
  OkSummary,
  OkGeneric,
  ErrGeneric,
  FallbackTts,
};

struct Directive {
  AudioCode audio_code;
  ServerFace face;
  String screen_text;
  String fetch_url;
};

bool directive_parse(const String& json_body, Directive& out);

const char* directive_sd_path_for(AudioCode code);

void directive_dispatch(const DeviceConfig& cfg, const Directive& d);

}

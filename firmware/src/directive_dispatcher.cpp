#include "directive_dispatcher.h"

#include <ArduinoJson.h>

#include "audio_playback.h"
#include "config.h"
#include "network_client.h"
#include "tft_face.h"

namespace lyla {

namespace {

AudioCode parse_audio_code(const String& s) {
  if (s == "ok_expense")   return AudioCode::OkExpense;
  if (s == "ok_task")      return AudioCode::OkTask;
  if (s == "ok_reminder")  return AudioCode::OkReminder;
  if (s == "ok_summary")   return AudioCode::OkSummary;
  if (s == "ok_generic")   return AudioCode::OkGeneric;
  if (s == "err_generic")  return AudioCode::ErrGeneric;
  if (s == "fallback_tts") return AudioCode::FallbackTts;
  return AudioCode::Unknown;
}

ServerFace parse_face(const String& s) {
  if (s == "happy")    return ServerFace::Happy;
  if (s == "sad")      return ServerFace::Sad;
  if (s == "thinking") return ServerFace::Thinking;
  if (s == "neutral")  return ServerFace::Neutral;
  return ServerFace::Neutral;
}

}

bool directive_parse(const String& json_body, Directive& out) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, json_body);
  if (err) {
    LYLA_WARN("directive: json parse failed: %s", err.c_str());
    return false;
  }
  JsonObject d = doc["directive"].as<JsonObject>();
  if (d.isNull()) {
    LYLA_WARN("directive: missing 'directive' object");
    return false;
  }
  String code_s = d["audio_code"].as<const char*>() ? d["audio_code"].as<String>() : String();
  String face_s = d["face"].as<const char*>() ? d["face"].as<String>() : String();
  out.audio_code = parse_audio_code(code_s);
  out.face = parse_face(face_s);
  out.screen_text = d["screen_text"].as<const char*>() ? d["screen_text"].as<String>() : String();
  out.fetch_url = d["fetch_url"].as<const char*>() ? d["fetch_url"].as<String>() : String();
  if (out.audio_code == AudioCode::Unknown) {
    LYLA_WARN("directive: unknown audio_code='%s', falling back to ok_generic", code_s.c_str());
    out.audio_code = AudioCode::OkGeneric;
  }
  return true;
}

const char* directive_sd_path_for(AudioCode code) {
  switch (code) {
    case AudioCode::OkExpense:   return "/sounds/ok_expense.wav";
    case AudioCode::OkTask:      return "/sounds/ok_task.wav";
    case AudioCode::OkReminder:  return "/sounds/ok_reminder.wav";
    case AudioCode::OkSummary:   return "/sounds/ok_summary.wav";
    case AudioCode::OkGeneric:   return "/sounds/ok_generic.wav";
    case AudioCode::ErrGeneric:  return "/sounds/err_generic.wav";
    default:                     return "/sounds/ok_generic.wav";
  }
}

void directive_dispatch(const DeviceConfig& cfg, const Directive& d) {
  set_server_face_override(d.face, d.screen_text);

  if (d.audio_code == AudioCode::FallbackTts) {
    if (d.fetch_url.length() == 0) {
      LYLA_WARN("directive: fallback_tts without fetch_url");
      audio_playback_play_sd("/sounds/err_generic.wav");
      return;
    }
    TtsFetchResult tts = network_get_tts(cfg, d.fetch_url);
    if (tts.http_status != 200 || tts.bytes == nullptr) {
      LYLA_WARN("directive: tts fetch failed status=%d err=%s",
                tts.http_status, tts.error.c_str());
      if (tts.bytes != nullptr) {
        free(tts.bytes);
      }
      audio_playback_play_sd("/sounds/err_generic.wav");
      return;
    }
    if (!tts.protocol_version_ok) {
      LYLA_WARN("directive: tts protocol mismatch");
      free(tts.bytes);
      audio_playback_play_sd("/sounds/err_generic.wav");
      return;
    }
    bool ok = audio_playback_play_wav_bytes(tts.bytes, tts.bytes_len);
    free(tts.bytes);
    if (!ok) {
      audio_playback_play_sd("/sounds/err_generic.wav");
    }
    return;
  }

  const char* path = directive_sd_path_for(d.audio_code);
  if (!audio_playback_play_sd(path)) {
    if (d.audio_code != AudioCode::ErrGeneric) {
      audio_playback_play_sd("/sounds/err_generic.wav");
    }
  }
}

}

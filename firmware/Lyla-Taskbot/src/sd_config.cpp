#include "sd_config.h"

#include <ArduinoJson.h>
#include <SD_MMC.h>

#include "config.h"

namespace lyla {

namespace {

constexpr const char* kConfigPath = "/config.json";
constexpr size_t kMaxConfigBytes = 4096;

bool is_uuid_v4_like(const String& s) {
  if (s.length() != 36) return false;
  for (int i = 0; i < 36; ++i) {
    char c = s[i];
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      if (c != '-') return false;
    } else {
      bool hex = (c >= '0' && c <= '9') ||
                 (c >= 'a' && c <= 'f') ||
                 (c >= 'A' && c <= 'F');
      if (!hex) return false;
    }
  }
  return true;
}

bool starts_with_scheme(const String& url) {
  return url.startsWith("http://") || url.startsWith("https://");
}

ConfigLoadOutcome fail(ConfigLoadResult code, const String& detail) {
  return ConfigLoadOutcome{code, detail};
}

}

ConfigLoadOutcome load_device_config(DeviceConfig& out) {
  SD_MMC.setPins(LYLA_SD_CLK, LYLA_SD_CMD, LYLA_SD_D0);
  if (!SD_MMC.begin("/sdcard", true, false, BOARD_MAX_SDMMC_FREQ, 5)) {
    return fail(ConfigLoadResult::SDMountFailed, "");
  }

  if (!SD_MMC.exists(kConfigPath)) {
    return fail(ConfigLoadResult::FileMissing, kConfigPath);
  }

  File f = SD_MMC.open(kConfigPath, FILE_READ);
  if (!f) {
    return fail(ConfigLoadResult::FileMissing, kConfigPath);
  }
  if (f.size() > kMaxConfigBytes) {
    f.close();
    return fail(ConfigLoadResult::FileTooLarge, String(f.size()));
  }

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, f);
  f.close();
  if (err) {
    return fail(ConfigLoadResult::ParseError, err.c_str());
  }

  out.user_id = doc["user_id"].as<const char*>() ? doc["user_id"].as<String>() : String();
  out.device_id = doc["device_id"].as<const char*>() ? doc["device_id"].as<String>() : String();
  out.device_code = doc["device_code"].as<const char*>() ? doc["device_code"].as<String>() : String();
  out.device_token = doc["device_token"].as<const char*>() ? doc["device_token"].as<String>() : String();
  out.base_url = doc["base_url"].as<const char*>() ? doc["base_url"].as<String>() : String();
  out.firmware_version = doc["firmware_version"].as<const char*>() ? doc["firmware_version"].as<String>() : String();

  JsonObject wifi_obj = doc["wifi"].as<JsonObject>();
  if (!wifi_obj.isNull()) {
    out.wifi_ssid = wifi_obj["ssid"].as<const char*>() ? wifi_obj["ssid"].as<String>() : String();
    out.wifi_password = wifi_obj["password"].as<const char*>() ? wifi_obj["password"].as<String>() : String();
  }

  while (out.base_url.endsWith("/")) {
    out.base_url.remove(out.base_url.length() - 1);
  }

  if (!is_uuid_v4_like(out.user_id)) {
    return fail(ConfigLoadResult::MissingField, "user_id");
  }
  if (!is_uuid_v4_like(out.device_id)) {
    return fail(ConfigLoadResult::MissingField, "device_id");
  }
  if (out.device_code.length() == 0 || out.device_code.length() > 64) {
    return fail(ConfigLoadResult::MissingField, "device_code");
  }
  if (out.device_token.length() == 0) {
    return fail(ConfigLoadResult::MissingField, "device_token");
  }
  if (out.base_url.length() == 0 || !starts_with_scheme(out.base_url)) {
    return fail(ConfigLoadResult::InvalidScheme, "base_url");
  }
  if (out.wifi_ssid.length() == 0 || out.wifi_ssid.length() > 32) {
    return fail(ConfigLoadResult::MissingField, "wifi.ssid");
  }
  if (out.firmware_version.length() == 0) {
    out.firmware_version = LYLA_FIRMWARE_VERSION;
  }

  return ConfigLoadOutcome{ConfigLoadResult::Ok, String()};
}

const char* config_load_result_message(const ConfigLoadOutcome& o) {
  switch (o.result) {
    case ConfigLoadResult::Ok:              return "OK";
    case ConfigLoadResult::SDMountFailed:   return "SD card error";
    case ConfigLoadResult::FileMissing:     return "Config missing";
    case ConfigLoadResult::FileTooLarge:    return "Config too large";
    case ConfigLoadResult::ParseError:      return "Config parse error";
    case ConfigLoadResult::MissingField:    return "Config error: field";
    case ConfigLoadResult::InvalidScheme:   return "Config error: base_url";
    default:                                 return "Config error";
  }
}

String request_url(const DeviceConfig& cfg, const String& path) {
  String url = cfg.base_url;
  if (!path.startsWith("/")) {
    url += "/";
  }
  url += path;
  return url;
}

}

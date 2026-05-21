// firmware/src/sd_config.h
// Reads and validates /config.json from the microSD card per Contract §2.
// Returns a structured DeviceConfig. Halts the firmware on any failure.

#pragma once

#include <Arduino.h>

namespace lyla {

struct DeviceConfig {
  String user_id;
  String device_id;
  String device_code;
  String device_token;
  String base_url;
  String wifi_ssid;
  String wifi_password;
  String firmware_version;
};

enum class ConfigLoadResult : uint8_t {
  Ok = 0,
  SDMountFailed,
  FileMissing,
  FileTooLarge,
  ParseError,
  MissingField,
  InvalidScheme,
};

struct ConfigLoadOutcome {
  ConfigLoadResult result;
  String detail;
};

ConfigLoadOutcome load_device_config(DeviceConfig& out);

const char* config_load_result_message(const ConfigLoadOutcome& outcome);

String request_url(const DeviceConfig& cfg, const String& path);

}

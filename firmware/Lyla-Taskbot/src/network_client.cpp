#include "network_client.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <esp_heap_caps.h>
#include <esp_random.h>

#include "config.h"

namespace lyla {

namespace {

constexpr const char* kBoundary = "----LylaBMOBoundary7f3a";
const String g_ct_multipart = String("multipart/form-data; boundary=") + kBoundary;

unsigned long g_wifi_backoff_ms = LYLA_WIFI_BACKOFF_INITIAL_MS;
unsigned long g_wifi_next_attempt_at = 0;
String g_wifi_ssid;
String g_wifi_password;

bool url_is_https(const String& url) {
  return url.startsWith("https://");
}

WiFiClient* make_client_for(const String& url) {
  if (url_is_https(url)) {
    auto* secure = new WiFiClientSecure();
    if (secure == nullptr) return nullptr;
    secure->setInsecure();
    secure->setTimeout(30);
    return secure;
  }
  return new WiFiClient();
}

void release_client(WiFiClient* client) {
  delete client;
}

void schedule_next_attempt() {
  g_wifi_next_attempt_at = millis() + g_wifi_backoff_ms;
  g_wifi_backoff_ms *= 2;
  if (g_wifi_backoff_ms > LYLA_WIFI_BACKOFF_MAX_MS) {
    g_wifi_backoff_ms = LYLA_WIFI_BACKOFF_MAX_MS;
  }
}

void reset_backoff() {
  g_wifi_backoff_ms = LYLA_WIFI_BACKOFF_INITIAL_MS;
  g_wifi_next_attempt_at = 0;
}

}

bool network_init(const DeviceConfig& cfg) {
  g_wifi_ssid = cfg.wifi_ssid;
  g_wifi_password = cfg.wifi_password;
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  return true;
}

bool network_wifi_connect(uint32_t timeout_ms) {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.begin(g_wifi_ssid.c_str(), g_wifi_password.c_str());
  unsigned long deadline = millis() + timeout_ms;
  while (millis() < deadline) {
    if (WiFi.status() == WL_CONNECTED) {
      reset_backoff();
      LYLA_LOG("wifi connected, ip=%s rssi=%d",
               WiFi.localIP().toString().c_str(), WiFi.RSSI());
      return true;
    }
    delay(200);
  }
  LYLA_WARN("wifi connect timeout (status=%d)", WiFi.status());
  schedule_next_attempt();
  return false;
}

bool network_wifi_is_connected() {
  return WiFi.status() == WL_CONNECTED;
}

int network_wifi_rssi() {
  if (WiFi.status() != WL_CONNECTED) return 0;
  return WiFi.RSSI();
}

void network_wifi_loop() {
  if (WiFi.status() == WL_CONNECTED) {
    reset_backoff();
    return;
  }
  if (millis() < g_wifi_next_attempt_at) return;
  WiFi.disconnect();
  WiFi.begin(g_wifi_ssid.c_str(), g_wifi_password.c_str());
  schedule_next_attempt();
}

String network_generate_uuid_v4() {
  uint8_t b[16];
  esp_fill_random(b, sizeof(b));
  b[6] = (b[6] & 0x0F) | 0x40;
  b[8] = (b[8] & 0x3F) | 0x80;
  char buf[37];
  snprintf(buf, sizeof(buf),
           "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
           b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
           b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]);
  return String(buf);
}

}

namespace lyla {

namespace {

void append_str(uint8_t*& cursor, const String& s) {
  size_t n = s.length();
  memcpy(cursor, s.c_str(), n);
  cursor += n;
}

void append_bytes(uint8_t*& cursor, const uint8_t* data, size_t len) {
  memcpy(cursor, data, len);
  cursor += len;
}

void put_u32_le(uint8_t* dst, uint32_t v) {
  dst[0] = v & 0xFF;
  dst[1] = (v >> 8) & 0xFF;
  dst[2] = (v >> 16) & 0xFF;
  dst[3] = (v >> 24) & 0xFF;
}

void put_u16_le(uint8_t* dst, uint16_t v) {
  dst[0] = v & 0xFF;
  dst[1] = (v >> 8) & 0xFF;
}

void build_wav_header(uint8_t* hdr, uint32_t sample_rate,
                      uint16_t bits_per_sample, uint16_t channels,
                      uint32_t pcm_bytes) {
  hdr[0] = 'R'; hdr[1] = 'I'; hdr[2] = 'F'; hdr[3] = 'F';
  put_u32_le(hdr + 4, 36 + pcm_bytes);
  hdr[8] = 'W'; hdr[9] = 'A'; hdr[10] = 'V'; hdr[11] = 'E';
  hdr[12] = 'f'; hdr[13] = 'm'; hdr[14] = 't'; hdr[15] = ' ';
  put_u32_le(hdr + 16, 16);
  put_u16_le(hdr + 20, 1);
  put_u16_le(hdr + 22, channels);
  put_u32_le(hdr + 24, sample_rate);
  put_u32_le(hdr + 28, sample_rate * channels * (bits_per_sample / 8));
  put_u16_le(hdr + 32, channels * (bits_per_sample / 8));
  put_u16_le(hdr + 34, bits_per_sample);
  hdr[36] = 'd'; hdr[37] = 'a'; hdr[38] = 't'; hdr[39] = 'a';
  put_u32_le(hdr + 40, pcm_bytes);
}

String form_field(const String& name, const String& value) {
  String s = "--";
  s += kBoundary;
  s += "\r\nContent-Disposition: form-data; name=\"";
  s += name;
  s += "\"\r\n\r\n";
  s += value;
  s += "\r\n";
  return s;
}

String file_field_header() {
  String s = "--";
  s += kBoundary;
  s += "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"voice.wav\"\r\n";
  s += "Content-Type: audio/wav\r\n\r\n";
  return s;
}

String trailer() {
  String s = "\r\n--";
  s += kBoundary;
  s += "--\r\n";
  return s;
}

}

AudioPostResult network_post_audio(const DeviceConfig& cfg,
                                   const uint8_t* wav_pcm,
                                   size_t pcm_bytes,
                                   uint32_t sample_rate,
                                   const AudioRequestTelemetry& telemetry) {
  AudioPostResult result = {0, false, String(), String()};
  if (!network_wifi_is_connected()) {
    result.error = "wifi";
    return result;
  }
  if (wav_pcm == nullptr || pcm_bytes == 0) {
    result.error = "empty audio";
    return result;
  }

  String preamble;
  preamble.reserve(512);
  preamble += form_field("user_id", cfg.user_id);
  preamble += form_field("device_id", cfg.device_id);
  preamble += form_field("timezone", "Asia/Jakarta");
  preamble += form_field("client_request_id", telemetry.client_request_id);
  preamble += form_field("firmware_version", cfg.firmware_version);
  preamble += form_field("wifi_rssi_dbm", String(telemetry.wifi_rssi_dbm));
  preamble += form_field("battery_pct", String(telemetry.battery_pct));
  preamble += form_field("recording_duration_ms", String(telemetry.recording_duration_ms));
  preamble += file_field_header();

  String tail = trailer();

  size_t total_size = preamble.length() + 44 + pcm_bytes + tail.length();
  if (total_size > LYLA_MAX_RECORD_BYTES + LYLA_MULTIPART_OVERHEAD_BYTES + 64) {
    result.error = "body too large";
    return result;
  }

  uint8_t* body = (uint8_t*)heap_caps_malloc(total_size, MALLOC_CAP_SPIRAM);
  if (body == nullptr) {
    result.error = "ps_malloc";
    return result;
  }
  uint8_t* cursor = body;
  append_str(cursor, preamble);
  uint8_t hdr[44];
  build_wav_header(hdr, sample_rate, LYLA_MIC_BITS_PER_SAMPLE, 1, (uint32_t)pcm_bytes);
  append_bytes(cursor, hdr, sizeof(hdr));
  append_bytes(cursor, wav_pcm, pcm_bytes);
  append_str(cursor, tail);

  String url = request_url(cfg, "/agent/audio");
  WiFiClient* client = make_client_for(url);
  if (client == nullptr) {
    heap_caps_free(body);
    result.error = "client";
    return result;
  }
  HTTPClient http;
  http.setTimeout(LYLA_HTTP_AUDIO_TIMEOUT_MS);
  http.setReuse(false);
  if (!http.begin(*client, url)) {
    heap_caps_free(body);
    release_client(client);
    result.error = "begin";
    return result;
  }
  http.addHeader("Content-Type", g_ct_multipart);
  http.addHeader("X-Device-Token", cfg.device_token);
  http.addHeader("User-Agent", LYLA_USER_AGENT);
  http.addHeader("Accept", "application/json");

  static const char* kCollectKeys[] = {"X-Lyla-Protocol"};
  http.collectHeaders(kCollectKeys, 1);

  int code = http.POST(body, total_size);
  result.http_status = code;
  if (code > 0) {
    String proto = http.header("X-Lyla-Protocol");
    result.protocol_version_ok = (proto == LYLA_PROTOCOL_VERSION);
    result.body = http.getString();
  } else {
    result.error = HTTPClient::errorToString(code);
  }
  http.end();
  release_client(client);
  heap_caps_free(body);
  return result;
}

}

namespace lyla {

TtsFetchResult network_get_tts(const DeviceConfig& cfg, const String& fetch_url) {
  TtsFetchResult result = {0, false, nullptr, 0, String()};
  if (!network_wifi_is_connected()) {
    result.error = "wifi";
    return result;
  }
  String url = request_url(cfg, fetch_url);
  WiFiClient* client = make_client_for(url);
  if (client == nullptr) {
    result.error = "client";
    return result;
  }
  HTTPClient http;
  http.setTimeout(LYLA_HTTP_TTS_TIMEOUT_MS);
  http.setReuse(false);
  if (!http.begin(*client, url)) {
    release_client(client);
    result.error = "begin";
    return result;
  }
  http.addHeader("X-Device-Token", cfg.device_token);
  http.addHeader("User-Agent", LYLA_USER_AGENT);
  http.addHeader("Accept", "audio/wav");

  static const char* kCollectKeys[] = {"X-Lyla-Protocol"};
  http.collectHeaders(kCollectKeys, 1);

  int code = http.GET();
  result.http_status = code;
  if (code != HTTP_CODE_OK) {
    if (code > 0) {
      String proto = http.header("X-Lyla-Protocol");
      result.protocol_version_ok = (proto == LYLA_PROTOCOL_VERSION);
    } else {
      result.error = HTTPClient::errorToString(code);
    }
    http.end();
    release_client(client);
    return result;
  }
  String proto = http.header("X-Lyla-Protocol");
  result.protocol_version_ok = (proto == LYLA_PROTOCOL_VERSION);

  int len = http.getSize();
  if (len <= 0 || (size_t)len > LYLA_MAX_TTS_BYTES) {
    result.error = String("size ") + String(len);
    http.end();
    release_client(client);
    return result;
  }
  uint8_t* buf = (uint8_t*)heap_caps_malloc((size_t)len, MALLOC_CAP_SPIRAM);
  if (buf == nullptr) {
    result.error = "ps_malloc";
    http.end();
    release_client(client);
    return result;
  }
  WiFiClient* stream = http.getStreamPtr();
  size_t total_read = 0;
  unsigned long deadline = millis() + LYLA_HTTP_TTS_TIMEOUT_MS;
  while (total_read < (size_t)len && millis() < deadline) {
    int avail = stream->available();
    if (avail <= 0) {
      delay(5);
      continue;
    }
    int chunk = stream->read(buf + total_read, (size_t)len - total_read);
    if (chunk <= 0) break;
    total_read += chunk;
  }
  if (total_read != (size_t)len) {
    heap_caps_free(buf);
    http.end();
    release_client(client);
    result.error = "short read";
    return result;
  }
  result.bytes = buf;
  result.bytes_len = total_read;
  http.end();
  release_client(client);
  return result;
}

bool network_post_heartbeat(const DeviceConfig& cfg, bool online) {
  if (!network_wifi_is_connected()) return false;

  JsonDocument doc;
  doc["status"] = online ? "online" : "offline";
  doc["firmware_version"] = cfg.firmware_version;
  doc["wifi_rssi_dbm"] = network_wifi_rssi();
  doc["battery_pct"] = -1;
  doc["free_heap_bytes"] = (int)ESP.getFreeHeap();

  String body;
  serializeJson(doc, body);

  String url = request_url(cfg, String("/devices/") + cfg.device_code + String("/status"));
  WiFiClient* client = make_client_for(url);
  if (client == nullptr) return false;
  HTTPClient http;
  http.setTimeout(LYLA_HTTP_HEARTBEAT_TIMEOUT_MS);
  http.setReuse(false);
  if (!http.begin(*client, url)) {
    release_client(client);
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", cfg.device_token);
  http.addHeader("User-Agent", LYLA_USER_AGENT);

  int code = http.POST(body);
  http.end();
  release_client(client);
  if (code == HTTP_CODE_OK) {
    LYLA_LOG("heartbeat OK device=%s rssi=%d",
             cfg.device_code.c_str(), network_wifi_rssi());
    return true;
  }
  if (code > 0) {
    LYLA_WARN("heartbeat HTTP %d on %s/devices/%s/status",
              code, cfg.base_url.c_str(), cfg.device_code.c_str());
  } else {
    LYLA_WARN("heartbeat network err %d (%s)",
              code, HTTPClient::errorToString(code).c_str());
  }
  return false;
}

}

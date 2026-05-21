// firmware/src/audio_capture.h
// I2S input from INMP441 microphone (Contract §6.3).
// Captures mono 16-bit PCM at 16 kHz into PSRAM.

#pragma once

#include <Arduino.h>

namespace lyla {

bool audio_capture_init();

void audio_capture_start();

bool audio_capture_pump();

size_t audio_capture_stop();

const uint8_t* audio_capture_buffer();

size_t audio_capture_size_bytes();

void audio_capture_release();

uint32_t audio_capture_sample_rate();

uint16_t audio_capture_last_peak();

}

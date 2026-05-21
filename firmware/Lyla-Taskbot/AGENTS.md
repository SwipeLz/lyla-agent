# Repository Guidelines

## Project Structure & Module Organization
This repository is a PlatformIO firmware project for an ESP32-S3 board. Main application code lives in `src/`, with the current entry point at `src/main.cpp`. Shared headers belong in `include/`, reusable components in `lib/`, and embedded tests in `test/`. Build configuration is defined in `platformio.ini`, which currently targets the `4d_systems_esp32s3_gen4_r8n16` environment. Generated output such as `.pio/` should remain untracked.

## Build, Test, and Development Commands
Run all commands from the repository root.

- `pio run` builds the firmware for the configured board.
- `pio run -t upload` flashes the firmware to a connected device.
- `pio device monitor` opens the serial monitor for runtime logs.
- `pio test` runs PlatformIO unit tests from `test/`.

If PlatformIO is not on your `PATH`, use `platformio` instead of `pio`.

## Coding Style & Naming Conventions
Use C++ with Arduino-style structure: `setup()` for initialization and `loop()` for repeated work. Follow the existing style in `src/main.cpp`: 2-space indentation, braces on the same line, and concise comments only where behavior is not obvious. Use `PascalCase` for class names, `camelCase` for functions and variables, and `UPPER_SNAKE_CASE` for macros and constants. Keep hardware-specific logic isolated in small functions rather than growing `loop()` into a monolith.

## Testing Guidelines
Place new tests under `test/`, organized by feature or module. Prefer small, deterministic unit tests that can run through `pio test` without manual hardware interaction. Name test files and directories so their target is obvious, for example `test/display/test_render.cpp`. Before opening a PR, run at least `pio run` and `pio test`.

## Commit & Pull Request Guidelines
Recent history mixes conventional commits and phase-based summaries, such as `feat: tambah fitur...` and `Phase 12: observability dashboard...`. Keep commit subjects short, imperative, and specific. Prefer formats like `feat: add display driver init` or `fix: guard null serial input`. PRs should explain the firmware change, note the target hardware or wiring assumptions, list verification steps, and include serial output or photos when UI/device behavior changes.

## Configuration & Safety Notes
Treat `platformio.ini` as the source of truth for board and framework settings. Do not commit secrets, local ports, or generated build artifacts. When changing pin mappings, timing, or peripherals, document the hardware impact in the PR so others can reproduce the setup safely.

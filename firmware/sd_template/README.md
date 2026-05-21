# microSD Card Template — Lyla / Taskbot ESP32-S3

This folder is the **template content** for the microSD card that ships with
each ESP32-S3 device. Copy these files to a fresh FAT32-formatted microSD
(≥4 GB), fill in `config.json`, then insert the card into the device.

The firmware reads from the SD root, not from any subfolder beyond `/sounds/`.

## What goes on the SD card

```
/  (root)
├── config.json              ← you create this from the template (see below)
└── sounds/
    ├── greet_hello.wav      ← required, plays at boot
    ├── ack_thinking.wav     ← optional but strongly recommended
    ├── ack_still_thinking.wav  ← optional filler
    ├── ack_slow_network.wav    ← optional filler
    ├── ok_expense.wav       ← required, success: expense added
    ├── ok_task.wav          ← required, success: task added
    ├── ok_reminder.wav      ← required, success: reminder set
    ├── ok_summary.wav       ← required, success: today's summary
    ├── ok_generic.wav       ← required, fallback success
    └── err_generic.wav      ← required, any failure
```

All WAV files: **mono, 16-bit PCM, 16 kHz sample rate**. Convert with:

```bash
ffmpeg -i source.wav -ac 1 -ar 16000 -sample_fmt s16 ok_expense.wav
```

Total `/sounds/` size should be under 2 MB. The audio files are not provided
here; record them yourself or use a free TTS (Cloud TTS web UI, Edge TTS,
ElevenLabs free tier). All copy must be in **Bahasa Indonesia**.

Suggested phrasing:

| File | Suggested phrase |
|---|---|
| `greet_hello.wav` | "Halo!" |
| `ack_thinking.wav` | "Sebentar yaa..." |
| `ack_still_thinking.wav` | "Masih dipikir nih..." |
| `ack_slow_network.wav` | "Kayaknya internetnya lambat..." |
| `ok_expense.wav` | "Siap, sudah tercatat" |
| `ok_task.wav` | "Task sudah tercatat" |
| `ok_reminder.wav` | "Pengingat sudah saya pasang" |
| `ok_summary.wav` | "Ringkasan hari ini" |
| `ok_generic.wav` | "OK" |
| `err_generic.wav` | "Yah maaf, ada kesalahan, coba lagi ya" |

## Step-by-step setup

1. Format the microSD card as **FAT32** (Windows: right-click → Format →
   File system: FAT32; macOS: Disk Utility → MS-DOS (FAT)).
2. Copy `config.json.example` to the card root, then **rename it to
   `config.json`**.
3. Pair the device on the dashboard:
   - Open `https://<your-domain>/login` and log in.
   - Go to `/devices` → "Pair New Device" → enter a name → submit.
   - Copy the response JSON.
4. Open `config.json` on the SD card in any text editor. Replace the
   `PASTE_FROM_DASHBOARD_PAIR_RESPONSE` placeholders with the values from the
   dashboard response. Set `wifi.ssid` and `wifi.password` to your local WiFi.
5. Set `base_url` to the public domain you deployed the backend on (e.g.
   `https://lyla.example.com`). For LAN development, use
   `http://<host-ip>:8765`.
6. Save `config.json`. UTF-8 encoding, no BOM.
7. Create a `/sounds/` folder on the SD card and copy the 10 WAV files
   listed above into it.
8. Eject the card and insert it into the ESP32-S3.
9. Power on. The TFT should show the BMO splash, calibrate the MPU6050,
   play `greet_hello.wav`, and enter the idle loop with the BMO face.

## Verifying the setup

After boot, verify on the dashboard:
1. `/devices` page shows your device with **green "Online" pill** within
   60 seconds.
2. `/observability` shows the heartbeat in the device grid.
3. Press the push-to-talk button (GPIO18), say a command, release. The
   request appears in the live tail within 3 seconds.

## Updating audio without reflashing firmware

Pop the SD card → mount on PC → drop new WAV files in `/sounds/` →
reinsert. Firmware reads files on each playback; no caching, no version
check.

## Changing the base URL

Edit `config.json` on the SD card. Power-cycle the ESP. No firmware
reflash required.

## Token rotation

Re-pair via dashboard (`POST /devices/pair`). The old `device_token` is
invalidated server-side once the new device row is paired. Update the SD
card with the new `device_token` value.

## Security notes

- Anyone with physical access to the SD card can read `device_token`.
  This is acceptable for the 1-device MVP; the public surface is gated
  by `X-Device-Token` server-side.
- The token grants access to `POST /agent/audio` only; it cannot read
  user data, and no dashboard auth.
- For a stolen device: re-pair on the dashboard, the old token stops
  working immediately.

## Cross-references

- Contract on the wire: [`../../docs/ESP32_INTEGRATION_CONTRACT.md`](../../docs/ESP32_INTEGRATION_CONTRACT.md)
- Hardware pinout: [`taskbot_online_pinmap.md`](../../taskbot_online_pinmap.md)
  if available, otherwise see Contract §14.
- Backend pair flow: `docs/PHASE_12_SUMMARY.md`.

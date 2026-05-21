# WIRING GUIDE — Lyla / Taskbot ESP32-S3 (Freenove WROOM)

Wiring final untuk firmware di `firmware/Lyla-Taskbot/`. Pinmap ini sudah
match dengan `src/config.h` dan `docs/ESP32_INTEGRATION_CONTRACT.md` §14.

**Board target:** Freenove ESP32-S3 WROOM (8 MB PSRAM, 16 MB flash).
**Power:** USB 5V minimal 1A (untuk MAX98357A).

---

## Tabel pinout lengkap

| Modul | Pin Modul | GPIO ESP32-S3 | Power | Catatan |
|---|---|---:|---|---|
| **TFT ILI9341 320×240** | CS | 14 | 3V3 | SPI bus shared dengan modul TFT lain (kalau ada) |
| | DC | 21 | | |
| | RST | 47 | | |
| | MOSI / SDI | 1 | | |
| | SCK / CLK | 2 | | |
| | MISO / SDO | 41 | | |
| | LED / BL | 3V3 langsung | | |
| | VCC | 3V3 atau 5V | | Cek modul kamu — ada yang 3V3 only, ada yang built-in regulator 5V |
| | GND | GND | | |
| **microSD on-board** | (built-in slot) | 38/39/40 | 3V3 (built-in) | Jangan disambung kabel — pakai slot fisik di board |
| | CLK (built-in) | 39 | | |
| | CMD (built-in) | 38 | | |
| | D0 (built-in) | 40 | | |
| **Touch sensor TTP223** | OUT / SIG | 4 | 3V3 | Default active-HIGH |
| | VCC | 3V3 | | |
| | GND | GND | | |
| **MPU6050 IMU** | SDA | 6 | 3V3 | I2C address 0x68 (AD0=GND) |
| | SCL | 7 | | |
| | VCC | 3V3 | | Jangan 5V |
| | GND | GND | | |
| | AD0 | GND | | Wajib ke GND, supaya address = 0x68 |
| **INMP441 mic** | WS / LRCL | 15 | **3V3 ONLY** | I2S input |
| | SCK / BCLK | 16 | | |
| | SD / DOUT | 17 | | |
| | L/R | GND | | Pilih left channel |
| | VDD | 3V3 | | **Jangan 5V — chip akan rusak** |
| | GND | GND | | |
| **MAX98357A speaker amp** | LRC / WS | 8 | **5V** | I2S output |
| | BCLK | 9 | | |
| | DIN | 10 | | |
| | VIN | 5V | | 3V3 boleh tapi volume kecil |
| | GND | GND | | |
| | SD / GAIN | biarkan | | Default gain 9 dB |
| | Speaker + | speaker + | | 4-8 Ω 3W speaker |
| | Speaker − | speaker − | | |
| **Push-to-talk button** | kaki 1 | 18 | — | INPUT_PULLUP, active-LOW |
| | kaki 2 | GND | | Tidak perlu resistor pull-up eksternal |
| **Status LED** | anoda (+) | 42 (lewat 220Ω) | — | Optional |
| | katoda (−) | GND | | |

---

## Wiring per bus

### Bus 1: SPI user (TFT only)

```
  ESP32-S3                ILI9341 TFT
  ─────────               ───────────
  GPIO 14 ───────────► CS
  GPIO 21 ───────────► DC (RS)
  GPIO 47 ───────────► RST
  GPIO  1 ───────────► MOSI (SDI)
  GPIO  2 ───────────► SCK (CLK)
  GPIO 41 ◄─────────── MISO (SDO)
  3V3      ───────────► VCC, BL
  GND      ───────────► GND
```

### Bus 2: SDMMC peripheral (on-board microSD)

```
  ESP32-S3                on-board slot
  ─────────               ─────────────
  GPIO 38 (built-in) ───► CMD
  GPIO 39 (built-in) ───► CLK
  GPIO 40 (built-in) ───► D0
```

**Tidak perlu diwire manual.** Slot fisik di Freenove sudah ter-route ke
GPIO ini. Cukup masukkan microSD ke slot.

### Bus 3: I2C (MPU6050)

```
  ESP32-S3                MPU6050
  ─────────               ───────
  GPIO  6 ───────────► SDA
  GPIO  7 ───────────► SCL
  3V3      ───────────► VCC
  GND      ───────────► GND, AD0
```

### Bus 4: I2S input (mic INMP441)

```
  ESP32-S3                INMP441
  ─────────               ───────
  GPIO 15 ───────────► WS (LRCL)
  GPIO 16 ───────────► SCK (BCLK)
  GPIO 17 ◄─────────── SD (DOUT)
  3V3      ───────────► VDD  ⚠️ JANGAN 5V
  GND      ───────────► GND, L/R
```

### Bus 5: I2S output (speaker MAX98357A)

```
  ESP32-S3                MAX98357A
  ─────────               ─────────
  GPIO  8 ───────────► LRC (WS)
  GPIO  9 ───────────► BCLK
  GPIO 10 ───────────► DIN
  5V       ───────────► VIN
  GND      ───────────► GND

  speaker (4-8Ω 3W)
  ─────────
  pin +    ───────────► MAX98357A SPK+
  pin −    ───────────► MAX98357A SPK−
```

### GPIO standalone (touch + button + LED)

```
  TTP223 touch              ESP32-S3
  ────────────              ─────────
  OUT      ───────────► GPIO 4
  VCC      ───────────► 3V3
  GND      ───────────► GND

  Push button               ESP32-S3
  ───────────              ─────────
  kaki 1   ───────────► GPIO 18
  kaki 2   ───────────► GND

  LED (optional)            ESP32-S3
  ─────                    ─────────
  anoda (+) ──[220Ω]──► GPIO 42
  katoda (−) ────────► GND
```

---

## Power supply

| Modul | Tegangan | Arus puncak |
|---|---|---|
| ESP32-S3 WROOM | 5V via USB | ~500 mA |
| TFT ILI9341 | 3V3 atau 5V | ~150 mA dengan backlight |
| INMP441 | 3V3 | ~1.5 mA |
| MAX98357A | **5V** | ~700 mA puncak |
| MPU6050 | 3V3 | ~4 mA |
| TTP223 | 3V3 | ~2 mA |

**Total puncak ~1.4 A.** USB port laptop kadang kurang ampere; pakai
**powered USB hub** atau **5V external supply** kalau ESP brown-out.

Tanda brown-out:
- LED ESP redup saat boot
- Random reset
- Audio crackle / glitch
- WiFi disconnect random

---

## Common ground

**WAJIB:** semua GND modul harus tersambung jadi satu common ground.
Termasuk speaker GND. Skip ini = noise audio, sensor random, atau
modul dead.

```
  ESP32 GND ─┬─ TFT GND
             ├─ INMP441 GND
             ├─ MAX98357A GND
             ├─ MPU6050 GND
             ├─ TTP223 GND
             ├─ button GND
             └─ LED katoda
```

---

## Checklist sebelum power-on

- [ ] microSD sudah masuk ke **slot on-board** (bukan modul SPI eksternal)
- [ ] microSD sudah di-format FAT32, isinya `/config.json` + `/sounds/*.wav`
- [ ] INMP441 ke 3V3, **bukan 5V** (chip akan rusak permanen kalau salah)
- [ ] MAX98357A ke 5V (volume kecil kalau cuma 3V3)
- [ ] MPU6050 AD0 ke GND (untuk address 0x68; firmware mengasumsikan ini)
- [ ] Semua GND tersambung common
- [ ] TFT MOSI/MISO/SCK = GPIO 1/2/41 (jangan ketuker)
- [ ] PTT button: tidak perlu resistor pull-up eksternal (firmware pakai INPUT_PULLUP internal)
- [ ] Power supply 5V ≥ 1A (cek dengan adaptor 2A kalau ragu)

---

## Wiring mistakes paling sering

| Gejala | Kemungkinan penyebab | Fix |
|---|---|---|
| TFT blank / white screen | VCC TFT salah voltage | Cek modul kamu — ada yang 3V3-only |
| TFT garbled / random pixel | MOSI/SCK ketuker | Verify GPIO 1 = MOSI, GPIO 2 = SCK |
| `SD card error` di TFT | SD card rusak / bukan FAT32 | Format ulang FAT32 (bukan exFAT untuk SD ≥64 GB) |
| Boot loop / `Brownout detector` | Power kurang | Powered USB hub atau external 5V |
| Audio cuma noise / static | INMP441 dapat 5V | **GANTI** chip, kasih 3V3 |
| Audio out lemah | MAX98357A dapat 3V3 | Kasih 5V (sinyal data tetap 3V3 aman) |
| Speaker tidak bunyi sama sekali | MAX98357A SD pin di-pull-LOW | Biarkan SD floating atau pull HIGH |
| MPU6050 not detected | AD0 floating atau ke 3V3 | AD0 ke GND (address 0x68) |
| MPU6050 di address 0x69 | AD0 ke 3V3 | Pindah AD0 ke GND |
| Touch tidak responsif | Polarity TTP223 salah | Edit `LYLA_TOUCH_ACTIVE_HIGH` di `config.h` ke 0 |
| Button tidak respons | Wiring kebalik | Pin 1 → GPIO 18, pin 2 → GND. Internal pull-up handle sisanya |
| Random restart waktu speaker bunyi | Speaker draw arus besar, brown-out | External 5V supply, jangan dari USB laptop |

---

## Cek wiring via serial monitor

Setelah flash firmware, buka `pio device monitor -b 115200`. Boot log
yang sehat:

```
[lyla] boot, firmware=0.1.0 protocol=1
[lyla] config ok device_code=TASKBOT-XXX base_url=https://...
[lyla] wifi connected, ip=192.168.X.X rssi=-XX
[lyla] heartbeat OK device=TASKBOT-XXX rssi=-XX
[lyla] setup complete; entering main loop
```

Indikator wiring fail per modul:
- **TFT fail:** `Framebuffer allocation failed` → PSRAM tidak detected, atau wiring TFT salah
- **SD fail:** `SD card error` di TFT → on-board slot kosong atau SD rusak
- **MPU6050 fail:** `MPU ERROR` di TFT atau `MPU 0x69 — Connect AD0 to GND` → AD0 ke 3V3, harus ke GND
- **WiFi fail:** `WiFi terputus` persists → SSID/password salah di config.json
- **Heartbeat fail:** `heartbeat HTTP 401` → token mismatch, server `.env` belum sync (ADR-11)

---

## Skema fisik

```
                                  ┌─────────────────────┐
                                  │  Freenove ESP32-S3  │
   ┌──────────┐   GPIO1,2,14,21,  │     WROOM 8MB       │
   │  ILI9341 │◄───41,47───────── │                     │
   │   TFT    │                   │  Built-in slot ◄── microSD
   └──────────┘                   │                     │
                                  │   GPIO38/39/40      │
   ┌──────────┐                   │                     │
   │ INMP441  │── GPIO15,16,17 ──►│   I2S0 (mic)        │
   │   mic    │   3V3+GND          │                     │
   └──────────┘                   │                     │
                                  │                     │
   ┌──────────┐                   │                     │
   │MAX98357A │── GPIO8,9,10 ────►│   I2S1 (speaker)    │
   │ speaker  │   5V+GND           │                     │
   └──────────┘                   │                     │
                                  │                     │
   ┌──────────┐                   │                     │
   │ MPU6050  │── GPIO6,7 ───────►│   I2C (Wire)        │
   │   IMU    │   3V3+GND+AD0:GND  │                     │
   └──────────┘                   │                     │
                                  │                     │
   ┌──────────┐                   │                     │
   │  TTP223  │── GPIO4 ─────────►│   touch sensor      │
   │  touch   │   3V3+GND          │                     │
   └──────────┘                   │                     │
                                  │                     │
        button ──── GPIO18 ──────►│   PTT (record)      │
        button ──── GND            │                     │
                                  │                     │
        LED+ ──[220Ω]── GPIO42 ──►│   status LED        │
        LED− ──── GND              │                     │
                                  │                     │
                                  │   USB-C ── 5V ≥1A ───┐
                                  └─────────────────────┘
```

---

## Cross-references

- Pinmap di kode: [`src/config.h`](src/config.h)
- Contract section 14: [`../../docs/ESP32_INTEGRATION_CONTRACT.md`](../../docs/ESP32_INTEGRATION_CONTRACT.md)
- ADR-12 (TFT divergence): [`../../docs/ESP32_INTEGRATION_ADR.md`](../../docs/ESP32_INTEGRATION_ADR.md)
- SD card prep: [`sd_template/README.md`](sd_template/README.md)
- Firmware build & flash: [`../../docs/FIRMWARE_README.md`](../../docs/FIRMWARE_README.md)

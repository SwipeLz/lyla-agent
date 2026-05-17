# Architecture

## Overall Architecture
Taskbot follows a decoupled client-server architecture where a lightweight hardware client interacts with a powerful centralized backend.

## ESP32-S3 Role
The ESP32-S3 acts *only* as a local interaction controller. It is not the main AI agent. Its responsibilities include:
- Driving the OLED face engine
- Managing local states
- Audio recording (in later phases)
- Buzzer/speaker feedback
- Polling for device commands from the backend

## VPS/Backend Role
The VPS serves as the main backend and AI runtime. It handles all business logic, data persistence, and complex AI processing.
- Built using **FastAPI** for high performance and asynchronous capabilities.
- Exposes APIs for text commands, dashboard interfaces, and device polling.

## Google ADK Role
The agent runtime is powered by **Google ADK**. It orchestrates the AI logic, tool calling, and conversational interactions based on user input.

## SQLite Role
**SQLite** is used as the database for the MVP. It allows for rapid prototyping and simplified setup. The implementation will use `DATABASE_URL` configurations to remain migration-friendly to PostgreSQL for production deployments.

## Design Decisions
- **Why agent runtime runs on VPS instead of ESP32:** The ESP32 lacks the processing power, memory, and environment to run complex AI models and Python-based agent runtimes like Google ADK effectively. Offloading this to the VPS ensures scalability, easier updates, and better performance.
- **Why ESP-Claw/OpenClaw are not used for MVP:** To reduce complexity in the initial stages and focus on core task and expense management logic, generic frameworks are avoided in favor of a tailored, minimal implementation.

## Future Expansion Path
Future phases will introduce audio capabilities (STT/TTS), a web-based dashboard, WhatsApp notifications, and full ESP32 firmware integration.

## Open Decisions

### Dashboard Auth Mode (MVP)

**Decision:** `dashboard_auth_mode = "none"` untuk MVP.

**Konteks:** Setting `dashboard_auth_mode` (lihat `app/config.py`) menerima dua nilai yang valid:
- `"none"` — Dashboard Endpoint (`/dashboard/*`) dilayani tanpa pengecekan header autentikasi.
- `"shared_header"` — Setiap request ke Dashboard Endpoint wajib menyertakan header `X-Dashboard-Token` yang nilainya cocok dengan `dashboard_token` di config; mismatch menghasilkan HTTP 401.

Spec `agent-runtime-and-apis` (Requirement 14) menandai pilihan antara kedua mode tersebut sebagai **Open Decision** dan mewajibkan mode terpilih untuk MVP dicatat beserta rasionalnya (Requirement 18.4).

**Rasional pemilihan `"none"` untuk MVP:**
- Pada Phase 8, dashboard hanya dijalankan di lokal/VPS internal (tidak terekspos ke publik). Tidak ada UI publik atau pengguna eksternal yang perlu dilindungi pada tahap ini.
- Memilih `"none"` mengurangi friksi pengembangan dan debugging selama MVP (curl/CLI internal langsung dapat memanggil endpoint tanpa konfigurasi token tambahan).
- Jalur `"shared_header"` tetap diimplementasikan dan tersedia sebagai konfigurasi (`dashboard_auth_mode = "shared_header"` + `dashboard_token = <secret>`); transisi ke deployment publik nantinya cukup mengubah nilai konfigurasi tanpa refactor kode (config-only switch).

**Konsekuensi:**
- Sebelum dashboard diekspos ke jaringan publik, operator harus memflip `dashboard_auth_mode` ke `"shared_header"` dan menyediakan `dashboard_token` yang kuat. Default `"none"` cocok hanya untuk lokal/VPS internal.
- Jika kebutuhan auth meningkat (mis. multi-user dashboard, OAuth), keputusan ini harus ditinjau ulang dan dicatat sebagai keputusan baru di bagian ini.

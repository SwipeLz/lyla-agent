"""Application settings loader.

Single source of truth for environment configuration. The ``.env`` file at
the **project root** is loaded regardless of where the Python process is
launched from (``uvicorn`` from the repo root, ``pytest``, ``adk web``
from ``agents/``, scripts in ``scripts/``, etc.) by resolving it via an
absolute path computed from this file's location.

If you want to change a setting (e.g. the Gemini model), edit the root
``.env`` once and every component picks it up.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# This file lives at: <project_root>/app/config.py
# So <project_root> is parents[1].
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # Phase 0–3 settings (preserved)
    app_env: str = "development"
    database_url: str = "sqlite:///./taskbot.db"
    google_api_key: str = ""
    google_adk_model: str = "gemini-3-flash-preview"
    device_api_token: str = ""
    timezone: str = "Asia/Jakarta"

    # Phase 4–8 settings (new)
    # agent_mode: "" → auto by google_api_key; or "real" / "fake"
    agent_mode: str = ""
    # Reminder Scheduler
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 60
    # Dashboard auth
    # dashboard_auth_mode: "none" | "shared_header"
    dashboard_auth_mode: str = "none"
    # dashboard_token: used only when dashboard_auth_mode == "shared_header"
    dashboard_token: str = ""

    # Phase 10 audio settings.
    # MAX_AUDIO_UPLOAD_MB is decimal (10 MB = 10_000_000 bytes).
    # AUDIO_STT_MODE / AUDIO_TTS_MODE accept "fake" or "gemini".
    audio_stt_mode: str = "fake"
    audio_tts_mode: str = "fake"
    fake_stt_transcript: str = "catat makan siang 20000"
    max_audio_upload_mb: int = 10
    fake_tts_format: str = "wav"
    fake_tts_sample_rate: int = 16000

    # Phase 11 real-provider settings.
    # Used only when AUDIO_STT_MODE == "gemini" or AUDIO_TTS_MODE == "gemini".
    audio_stt_provider_model: str = "gemini-3-flash-preview"
    audio_tts_provider_model: str = "gemini-3.1-flash-tts-preview"
    audio_tts_voice: str = "Leda"
    tts_cache_ttl_seconds: int = 300

    # Phase 12 — dashboard auth + observability (internet-facing).
    # Single-user MVP. Password is scrypt-hashed via stdlib `hashlib.scrypt`;
    # generate the env value with `python -m scripts.hash_dashboard_password`.
    # Empty `dashboard_password_scrypt` is fail-closed: every login attempt 401.
    # Sessions are stored in-memory (server restart = re-login).
    # `cookie_secure=True` requires TLS termination upstream (tunnel / reverse proxy).
    # `require_device_token=True` forces ESP requests to carry `X-Device-Token`.
    dashboard_username: str = "admin"
    dashboard_password_scrypt: str = ""
    session_ttl_hours: int = 24
    cookie_secure: bool = True
    require_device_token: bool = True
    login_rate_limit_max_fails: int = 5
    login_rate_limit_window_seconds: int = 300
    base_url: str = "http://127.0.0.1:8765"
    mvp_user_email: str = "demo@taskbot.local"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

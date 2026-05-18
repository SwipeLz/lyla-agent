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
    # AUDIO_STT_MODE / AUDIO_TTS_MODE only support "fake" in Phase 10;
    # real provider modes (e.g. "google", "openai") are deferred.
    audio_stt_mode: str = "fake"
    audio_tts_mode: str = "fake"
    fake_stt_transcript: str = "catat makan siang 20000"
    max_audio_upload_mb: int = 10
    fake_tts_format: str = "wav"
    fake_tts_sample_rate: int = 16000

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

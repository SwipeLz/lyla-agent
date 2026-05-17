import os
from app.config import Settings

def test_config_loads_defaults():
    # Provide an empty environment to test defaults
    # Pydantic Settings reads from environment automatically
    settings = Settings(
        app_env="test",
        google_api_key="test_key",
        device_api_token="test_token"
    )
    # Phase 0–3 defaults preserved
    assert settings.app_env == "test"
    assert settings.database_url == "sqlite:///./taskbot.db"
    assert settings.google_adk_model == "gemini-3-flash-preview"
    assert settings.timezone == "Asia/Jakarta"
    assert settings.google_api_key == "test_key"
    assert settings.device_api_token == "test_token"


def test_config_phase4_8_defaults():
    # New fields added in agent-runtime-and-apis spec must have the
    # documented defaults so that test/CI behavior stays hermetic.
    settings = Settings()
    assert settings.agent_mode == ""
    assert settings.scheduler_enabled is False
    assert settings.scheduler_interval_seconds == 60
    assert settings.dashboard_auth_mode == "none"
    assert settings.dashboard_token == ""


def test_config_phase4_8_overrides():
    # Verify that the new fields can be overridden via constructor
    # (which is how pydantic-settings exposes env-driven configuration).
    settings = Settings(
        agent_mode="fake",
        scheduler_enabled=True,
        scheduler_interval_seconds=30,
        dashboard_auth_mode="shared_header",
        dashboard_token="dev-token",
    )
    assert settings.agent_mode == "fake"
    assert settings.scheduler_enabled is True
    assert settings.scheduler_interval_seconds == 30
    assert settings.dashboard_auth_mode == "shared_header"
    assert settings.dashboard_token == "dev-token"

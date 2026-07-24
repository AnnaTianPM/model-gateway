"""Application settings loaded from environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Network
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000

    # Security
    admin_token: str = "replace-with-a-long-random-token"
    gateway_master_key: str = "replace-with-a-generated-encryption-key"

    # Storage
    database_path: str = "/app/data/gateway.db"

    # Logging
    log_level: str = "INFO"
    log_prompt_content: bool = False

    # Behavior
    force_response_language: str = "off"

    # Version
    app_version_file: str = "/app/VERSION"
    git_commit: str = "unknown"
    deployment_env: str = "home-lan"

    # Client key
    default_client_key_name: str = "initial-client"
    trust_proxy_headers: bool = False

    # Provider key env refs
    nvidia_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    @property
    def db_path(self) -> Path:
        return Path(self.database_path)

    @property
    def version(self) -> str:
        version_file = Path(self.app_version_file)
        if version_file.exists():
            return version_file.read_text().strip()
        return "dev"

    @property
    def config_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "config"


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


_settings: Settings | None = None

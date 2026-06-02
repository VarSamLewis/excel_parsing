"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration – every env var the app needs."""

    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model_mapper: str = Field(
        default="gpt-4o", description="Model name for mapping"
    )
    openai_model_validator: str = Field(
        default="gpt-4o-mini", description="Model name for validation"
    )
    openai_base_url: str = Field(
        default="", description="Optional OpenAI-compatible base URL"
    )
    log_level: str = Field(default="INFO", description="Logging level")

    model_config = {
        "env_file": ("backend/.env", ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @property
    def openai_available(self: "Settings") -> bool:
        """Report OpenAI readiness; args: self (Settings); returns: bool."""
        return bool(self.openai_api_key)


settings = Settings()

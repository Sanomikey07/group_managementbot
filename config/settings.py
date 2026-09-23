from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_id: int = Field(..., alias="API_ID")
    api_hash: str = Field(..., alias="API_HASH")
    bot_token: str = Field(..., alias="BOT_TOKEN")
    owner_id: int = Field(..., alias="OWNER_ID")
    mongo_uri: str = Field("mongodb://localhost:27017", alias="MONGO_URI")
    mongo_db: str = Field("demon_admin_bot", alias="MONGO_DB")
    bot_username: str | None = Field(None, alias="BOT_USERNAME")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    command_rate_limit: int = Field(8, alias="COMMAND_RATE_LIMIT", ge=1, le=100)
    command_rate_window: int = Field(10, alias="COMMAND_RATE_WINDOW", ge=1, le=300)
    max_broadcast_concurrency: int = Field(8, alias="MAX_BROADCAST_CONCURRENCY", ge=1, le=50)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    @field_validator("bot_token", "api_hash", "mongo_uri")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required configuration value is empty")
        return value.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

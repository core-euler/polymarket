from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/polymarket",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        alias="CELERY_RESULT_BACKEND",
    )

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_allowed_user_ids_raw: str = Field(default="", alias="TELEGRAM_ALLOWED_USER_IDS")

    polymarket_gamma_base_url: str = Field(
        default="https://gamma-api.polymarket.com",
        alias="POLYMARKET_GAMMA_BASE_URL",
    )
    polymarket_clob_base_url: str = Field(
        default="https://clob.polymarket.com",
        alias="POLYMARKET_CLOB_BASE_URL",
    )
    polymarket_data_base_url: str = Field(
        default="https://data-api.polymarket.com",
        alias="POLYMARKET_DATA_BASE_URL",
    )

    comet_api_key: str = Field(default="", alias="COMET_API_KEY")
    comet_model_default: str = Field(default="", alias="COMET_MODEL_DEFAULT")

    seed_run_llm: bool = Field(default=False, alias="SEED_RUN_LLM")
    seed_drain_max_iterations: int = Field(default=20, alias="SEED_DRAIN_MAX_ITERATIONS")

    internal_api_base_url: str = Field(
        default="http://api:8000",
        alias="INTERNAL_API_BASE_URL",
    )

    @property
    def telegram_allowed_user_ids(self) -> List[int]:
        if not self.telegram_allowed_user_ids_raw.strip():
            return []
        return [int(value.strip()) for value in self.telegram_allowed_user_ids_raw.split(",") if value.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


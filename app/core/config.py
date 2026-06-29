from functools import lru_cache
from typing import Literal

from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]


class Settings(BaseSettings):
    """Typed environment-backed application configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Environment = "development"
    log_level: str = "INFO"
    telegram_bot_token: str = Field(min_length=1)
    database_url: str = "sqlite+aiosqlite:///./data/newstock_alert_bot.sqlite3"
    scheduler_timezone: str = "Asia/Kolkata"
    browser_headless: bool = True
    browser_timeout_seconds: PositiveInt = 30
    browser_pool_size: PositiveInt = 2
    browser_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    amazon_min_delay_ms: PositiveInt = 250
    amazon_max_delay_ms: PositiveInt = 1500
    amazon_retry_backoff_seconds: float = 0.75
    stock_check_interval_seconds: PositiveInt = 300
    stock_check_worker_limit: PositiveInt = 2
    stock_check_retry_attempts: PositiveInt = 2


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

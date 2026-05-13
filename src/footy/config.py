"""Centralised app settings, loaded from .env or process env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://footy:footy_dev_password@localhost:5432/footy"
    football_data_token: str | None = None
    football_data_url: str = "https://api.football-data.org/v4"


@lru_cache
def get_settings() -> Settings:
    return Settings()

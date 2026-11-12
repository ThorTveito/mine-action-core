from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://mac:mac@localhost:5440/mac"
    country_code: str = "KRV"  # fictional country, used in record codes


@lru_cache
def get_settings() -> Settings:
    return Settings()

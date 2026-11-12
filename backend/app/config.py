from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-secret-change-me-please-0123456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://mac:mac@localhost:5440/mac"
    country_code: str = "KRV"  # fictional country, used in record codes

    app_env: str = "development"  # set to "production" when deployed
    secret_key: str = DEV_SECRET  # signs auth tokens; MUST be overridden in production
    token_ttl_minutes: int = 480

    # Demo deployment helpers (synthetic data only).
    demo_mode: bool = False  # create demo users and show their credentials on the login form
    demo_password: str = "demo-password"
    seed_on_empty: bool = False  # load synthetic data on boot if the database has no hazards
    static_dir: str | None = None  # serve the built frontend from here (single-container deploy)

    @model_validator(mode="after")
    def _no_dev_secret_in_production(self) -> Self:
        if self.app_env == "production" and self.secret_key == DEV_SECRET:
            raise ValueError("SECRET_KEY must be set when APP_ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

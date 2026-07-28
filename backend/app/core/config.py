from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    environment: str = "development"
    app_name: str = "SRIS Enterprise"
    secret_key: str = "development-secret-change-me-" * 3
    encryption_master_key: str = ""
    database_url: str = "sqlite:///./sris.db"
    redis_url: str = "redis://localhost:6379/0"
    access_token_minutes: int = 20
    refresh_token_days: int = 14
    allowed_origins: str = "http://localhost:8000"
    cookie_secure: bool = False
    object_storage_endpoint: str | None = None
    object_storage_bucket: str = "sris-backups"
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    object_storage_region: str = "eu-west-1"
    bootstrap_demo: bool = False

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.allowed_origins.split(",") if x.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

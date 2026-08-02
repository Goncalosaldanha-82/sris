from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "ATLAS_DATABASE_URL",
        "sqlite+pysqlite:///./.atlas/atlas_platform.db",
    )
    jwt_secret: str = os.getenv("ATLAS_JWT_SECRET", "change-me-before-production")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(os.getenv("ATLAS_ACCESS_TOKEN_MINUTES", "60"))


settings = Settings()

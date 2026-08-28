"""Backend configuration, loaded from environment variables.

Credentials are never hardcoded. If Supabase is not configured the backend
falls back to in-memory storage so the API can still be run locally (useful
for frontend development and for tests).
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".png", ".jpg", ".jpeg"})

ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpg",
        "image/jpeg",
    }
)

MAX_UPLOAD_BYTES: int = 20 * 1024 * 1024  # 20 MB


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the backend."""

    supabase_url: str
    supabase_key: str
    supabase_bucket: str
    cors_origins: tuple[str, ...]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings read from the environment."""
    raw_origins = os.getenv("CORS_ORIGINS", "*")
    origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip())

    return Settings(
        supabase_url=os.getenv("SUPABASE_URL", "").strip(),
        supabase_key=os.getenv("SUPABASE_KEY", "").strip(),
        supabase_bucket=os.getenv("SUPABASE_BUCKET", "documents").strip(),
        cors_origins=origins or ("*",),
    )

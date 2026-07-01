from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MISTRAL_API_KEY: str
    DATABASE_URL: str | None = None
    SUPABASE_DB_URL: str | None = None
    SUPABASE_DATABASE_URL: str | None = None
    SUPABASE_URL: str | None = None
    SUPABASE_PUBLISHABLE_KEY: str | None = None
    SUPABASE_PUBLIC_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    GOOGLE_CLIENT_ID: str | None = None

    RAG_TOP_K: int = 3
    MISTRAL_CHAT_MODEL: str = "mistral-small-latest"
    MISTRAL_EMBED_MODEL: str = "mistral-embed"

    DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() in {"release", "production", "prod"}:
            return False
        return value

    @property
    def async_database_url(self) -> str:
        raw_url = self.SUPABASE_DB_URL or self.SUPABASE_DATABASE_URL or self.DATABASE_URL
        if not raw_url:
            raise ValueError(
                "Set SUPABASE_DB_URL, SUPABASE_DATABASE_URL, or DATABASE_URL to your "
                "Supabase Postgres connection string."
            )

        url = raw_url.strip()
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]

        parsed = urlparse(url)
        if parsed.hostname and "." not in parsed.hostname and self.SUPABASE_URL:
            supabase_host = urlparse(self.SUPABASE_URL).hostname
            if supabase_host and supabase_host.endswith(".supabase.co"):
                db_host = f"db.{supabase_host}"
                netloc = parsed.netloc.replace(parsed.hostname, db_host, 1)
                url = urlunparse(parsed._replace(netloc=netloc))

        # Supabase often provides sslmode=require, while asyncpg expects ssl=require.
        if "sslmode=" in url:
            url = url.replace("sslmode=", "ssl=")

        return url


settings = Settings()

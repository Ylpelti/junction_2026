from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    db_pool_size: int = Field(default=3, ge=1, le=20)
    db_max_overflow: int = Field(default=2, ge=0, le=20)
    db_pool_timeout: int = Field(default=10, ge=1, le=120)
    db_pool_recycle: int = Field(default=300, ge=30)

    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "cancersignal"
    postgres_user: str = "cancersignal"
    postgres_password: SecretStr | None = None
    database_url_override: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")

    @model_validator(mode="after")
    def validate_database(self):
        if self.database_url_override is not None:
            try:
                url = make_url(self.database_url_override.get_secret_value())
                if url.drivername not in ("postgres", "postgresql", "postgresql+psycopg") or not url.host or not url.database:
                    raise ValueError()
                _ = url.port
            except Exception:
                raise ValueError("DATABASE_URL must be a PostgreSQL URL with a host and database") from None
        elif self.postgres_password is None:
            raise ValueError("Set DATABASE_URL or POSTGRES_PASSWORD")
        return self

    @property
    def database_url(self) -> URL:
        if self.database_url_override is not None:
            return make_url(self.database_url_override.get_secret_value()).set(drivername="postgresql+psycopg")
        # URL.create safely handles special characters in credentials.
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


class WebSettings(BaseSettings):
    """HTTP settings load without requiring database credentials at app startup."""
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins):
        normalized = []
        for origin in origins:
            origin = origin.strip().rstrip("/")
            parsed = urlsplit(origin)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname or "*" in origin
                    or parsed.username is not None or parsed.password is not None
                    or parsed.path or parsed.query or parsed.fragment):
                raise ValueError("CORS_ORIGINS entries must be exact HTTP(S) origins, such as http://localhost:3000.")
            _ = parsed.port  # Validate a supplied port as well as the host.
            if origin not in normalized:
                normalized.append(origin)
        return normalized


@lru_cache
def get_web_settings() -> WebSettings:
    return WebSettings()


class PipelineSettings(BaseSettings):
    """Analysis pipeline switches; no database credentials or API keys here.

    CANCERSIGNAL_EXTRACTION=off keeps the structured-only demo extractor (default).
    CANCERSIGNAL_EXTRACTION=llm adds LLM note extraction (app/extraction). Provider
    settings (EXTRACTION_MODEL, EXTRACTION_API_KEY, ...) come from the environment
    or from CANCERSIGNAL_EXTRACTION_ENV_FILE. Live calls happen only when
    CANCERSIGNAL_EXTRACTION_ALLOW_LIVE=true; otherwise only cached responses work.
    """
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        env_prefix="CANCERSIGNAL_",
        extra="ignore",
    )

    extraction: Literal["off", "llm"] = "off"
    extraction_env_file: Path | None = None
    extraction_allow_live: bool = False
    extraction_cache_dir: Path | None = None

    explanation: Literal["deterministic", "llm"] = "deterministic"
    explanation_env_file: Path | None = None
    explanation_allow_live: bool = False
    explanation_cache_dir: Path | None = None

    # Auto uses complete history while it fits, then PostgreSQL lexical retrieval.
    # Hybrid explicitly opts into local embeddings; requests never download weights.
    retrieval: Literal["auto", "baseline", "lexical", "hybrid"] = "auto"
    retrieval_top_k: int = Field(default=5, ge=1)
    retrieval_max_source_chars: int = Field(default=32000, ge=1)
    retrieval_model_cache: Path | None = None
    retrieval_auto_index: bool = True


@lru_cache
def get_pipeline_settings() -> PipelineSettings:
    return PipelineSettings()

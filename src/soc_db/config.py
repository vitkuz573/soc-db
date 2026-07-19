from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOC_DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Paths ---
    data_dir: Path = Path(__file__).resolve().parent.parent.parent / "data"
    schema_file: Path = Path(__file__).resolve().parent.parent.parent / "schema" / "chip-schema.json"

    # --- Logging ---
    log_level: str = "WARNING"
    log_format: str = "json"

    # --- API server ---
    api_host: str = "0.0.0.0"  # nosec — intentional for containerised deployment
    api_port: int = 8000
    api_cors_origins: list[str] = ["*"]

    # --- Authentication ---
    api_key: str | None = None

    # --- Rate limiting (requests per window per client) ---
    api_rate_limit: int = 100
    api_rate_limit_window: int = 60

    # --- Cache ---
    cache_ttl: int = 300

    # --- SQLite database ---
    db_path: Path = Path(__file__).resolve().parent.parent.parent / "data" / "soc-db.db"
    use_json: bool = False  # SOC_DB_USE_JSON env var — when True, fall back to JSON files


settings = Settings()

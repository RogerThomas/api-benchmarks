"""Shared settings for the Python benchmark apps (pydantic-settings).

In docker every field is set by env vars from each framework's compose.<fw>.yml
(JWT_SECRET, UPSTREAM_URL, DB_HOST, …); the defaults below only matter when
running an app directly on the host (e.g. against `task upstream-native`).
Field names map to env vars case-insensitively, so `db_host` reads `DB_HOST`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = "bench-secret-please-change"

    upstream_url: str = "http://127.0.0.1:6700"
    upstream_api_key: str = "upstream-secret-key"

    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "bench"
    db_user: str = "bench"
    db_password: str = "bench"
    db_pool_size: int = 64

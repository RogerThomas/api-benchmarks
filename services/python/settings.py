"""Shared settings for the Python benchmark apps (pydantic-settings).

In docker every field is set by env vars from each framework's compose.<fw>.yml
(JWT_SECRET, UPSTREAM_URL, DB_HOST, …); the defaults below only matter when
running an app directly on the host (e.g. against `task upstream-native`).
Field names map to env vars case-insensitively, so `db_host` reads `DB_HOST`.
"""

from functools import cached_property
from typing import Any

import ryjwt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = "bench-secret-please-change-0123456"  # ryjwt wants >= 32 bytes for HS256

    upstream_url: str = "http://127.0.0.1:6700"
    upstream_api_key: str = "upstream-secret-key"
    http_pool_size: int = 64  # same outbound budget as Gin/Elysia/Spring

    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "bench"
    db_user: str = "bench"
    db_password: str = "bench"
    db_pool_size: int = 64

    @property
    def db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def upstream_client_options(self) -> dict[str, Any]:
        """The one lothc client config every Python framework uses, so test 3
        differs only in the framework. `max_connections` caps requests in
        flight; any beyond it wait for a free slot (like Gin's MaxConnsPerHost)."""
        return {
            "base_url": self.upstream_url,
            "bearer_token": self.upstream_api_key,
            "max_connections": self.http_pool_size,
            "connect_timeout": 1,
            "read_timeout": 5,
            "timeout": 10,
            "follow_redirects": False,
        }

    @cached_property
    def jwt_key(self) -> ryjwt.SecretKey:
        """Built once per process, so requests only pay for the decode."""
        return ryjwt.SecretKey(self.jwt_secret, algorithms=["HS256"])

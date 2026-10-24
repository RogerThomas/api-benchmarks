"""Shared settings for the Python benchmark apps.

Plain values, inlined: nothing here is a real secret (they're fixed benchmark
fixtures), and the hosts are the compose service names on the bench network.
The runner and the non-Python apps get the same values from compose.base.yml /
compose.<fw>.yml.
"""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class Settings:
    jwt_secret: str = "b7c1e9a4f2d68350a1c9e7b5d3f10864a2c6e8b0d4f79351"
    jwt_algorithm: Literal["HS256"] = "HS256"

    upstream_url: str = "http://upstream:8000"
    upstream_api_key: str = "upk_bench_9f8e7d6c5b4a32100fedcba987654321"
    http_pool_size: int = 64  # same outbound budget as Gin/Elysia/Spring

    db_host: str = "postgres"
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

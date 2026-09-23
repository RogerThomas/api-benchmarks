"""The `client.indexes` resource: create, get, and list indexes."""

from dataclasses import dataclass
from typing import Literal

from ._models import CreateIndexRequest, Index, IndexPage
from ._query import build_list_params
from ._transport import Transport


@dataclass
class Indexes:
    _transport: Transport

    def create(
        self,
        *,
        type: Literal["json", "blob"],  # noqa: A002 - matches the wire field name (ARCHITECTURE.md's own ergonomics)
        tags: dict[str, str] | None = None,
        key: str | None = None,
    ) -> Index:
        body = CreateIndexRequest(type=type, tags=tags or {}, key=key)
        return self._transport.post("indexes", response_type=Index, json=body)

    def get(self, index_id: str) -> Index:
        return self._transport.get(f"indexes/{index_id}", response_type=Index)

    def get_by_key(self, key: str) -> Index:
        return self._transport.get(f"indexes/by-key/{key}", response_type=Index)

    def list(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        tags: dict[str, str] | None = None,
        key: str | None = None,
    ) -> IndexPage:
        params = build_list_params(limit=limit, cursor=cursor, tags=tags, key=key)
        return self._transport.get("indexes", response_type=IndexPage, params=params)

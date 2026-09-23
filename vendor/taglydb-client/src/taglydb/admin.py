"""The `admin.principals` resource: create principals and manage their API keys."""

from dataclasses import dataclass

from ._models import (
    ApiKeyInfoPage,
    CreatedPrincipal,
    CreatePrincipalRequest,
    MintedApiKey,
    MintKeyRequest,
    Principal,
    PrincipalPage,
)
from ._query import build_list_params
from ._transport import Transport


@dataclass
class Principals:
    _transport: Transport

    def create(self, *, key: str, tags: dict[str, str] | None = None) -> CreatedPrincipal:
        body = CreatePrincipalRequest(key=key, tags=tags or {})
        return self._transport.post("admin/principals", response_type=CreatedPrincipal, json=body)

    def get(self, principal_id: str) -> Principal:
        return self._transport.get(f"admin/principals/{principal_id}", response_type=Principal)

    def list(self, *, limit: int | None = None, cursor: str | None = None) -> PrincipalPage:
        params = build_list_params(limit=limit, cursor=cursor, tags=None, key=None)
        return self._transport.get("admin/principals", response_type=PrincipalPage, params=params)

    def mint_key(self, principal_id: str, *, key: str) -> MintedApiKey:
        body = MintKeyRequest(key=key)
        return self._transport.post(
            f"admin/principals/{principal_id}/keys", response_type=MintedApiKey, json=body
        )

    def list_keys(
        self, principal_id: str, *, limit: int | None = None, cursor: str | None = None
    ) -> ApiKeyInfoPage:
        params = build_list_params(limit=limit, cursor=cursor, tags=None, key=None)
        return self._transport.get(
            f"admin/principals/{principal_id}/keys", response_type=ApiKeyInfoPage, params=params
        )

    def revoke_key(self, principal_id: str, key_id: str) -> None:
        self._transport.delete(f"admin/principals/{principal_id}/keys/{key_id}")

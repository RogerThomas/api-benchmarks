"""The `client.items` resource: create, list, and retrieve JSON/blob items."""

from dataclasses import dataclass

import msgspec
from lothc import Form

from ._models import (
    CreateJsonItemRequest,
    Item,
    ItemPage,
    ItemWithData,
    ItemWithDataPage,
    ItemWithDataPageWire,
    ItemWithDataWire,
    JsonValue,
)
from ._query import build_list_params
from ._transport import Transport


def _with_decoded_data(wire: ItemWithDataWire) -> ItemWithData:
    fields = msgspec.structs.asdict(wire)
    fields["data"] = msgspec.json.decode(wire.data)
    return ItemWithData(**fields)


@dataclass
class Items:
    _transport: Transport

    def create_json(
        self,
        index_id: str,
        *,
        data: JsonValue,
        tags: dict[str, str] | None = None,
        key: str | None = None,
    ) -> Item:
        body = CreateJsonItemRequest(tags=tags or {}, data=data, key=key)
        return self._transport.post(f"indexes/{index_id}/items", response_type=Item, json=body)

    def create_blob(
        self,
        index_id: str,
        *,
        data: bytes,
        tags: dict[str, str] | None = None,
        key: str | None = None,
    ) -> Item:
        form: Form = {
            "tags": ("tags.json", msgspec.json.encode(tags or {}), "application/json"),
            "data": ("data.bin", data, "application/octet-stream"),
        }
        # Omit the part entirely rather than sending an empty string — the server only accepts
        # "no key" as the part being absent.
        if key is not None:
            form["key"] = key
        return self._transport.post_form(f"indexes/{index_id}/items", response_type=Item, form=form)

    def list(
        self,
        index_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        tags: dict[str, str] | None = None,
        key: str | None = None,
    ) -> ItemPage:
        params = build_list_params(limit=limit, cursor=cursor, tags=tags, key=key)
        return self._transport.get(
            f"indexes/{index_id}/items", response_type=ItemPage, params=params
        )

    def get_json(self, index_id: str, item_id: str) -> JsonValue:
        raw = self._transport.get_bytes(f"indexes/{index_id}/items/{item_id}")
        return msgspec.json.decode(raw)

    def get_blob(self, index_id: str, item_id: str) -> bytes:
        return self._transport.get_bytes(f"indexes/{index_id}/items/{item_id}")

    def get_json_by_key(self, index_id: str, key: str) -> JsonValue:
        raw = self._transport.get_bytes(f"indexes/{index_id}/items/by-key/{key}")
        return msgspec.json.decode(raw)

    def get_blob_by_key(self, index_id: str, key: str) -> bytes:
        return self._transport.get_bytes(f"indexes/{index_id}/items/by-key/{key}")

    def get_full(self, index_id: str, item_id: str) -> ItemWithData:
        """Metadata plus decompressed `data` for one item, in a single call. JSON indexes
        only — raises `ValidationError` (422 `wrong_index_type`) for a blob index."""
        wire = self._transport.get(
            f"indexes/{index_id}/items/{item_id}/full", response_type=ItemWithDataWire
        )
        return _with_decoded_data(wire)

    def list_with_data(
        self,
        index_id: str,
        *,
        tags: dict[str, str] | None = None,
        key: str | None = None,
    ) -> ItemWithDataPage:
        """Every matching item's metadata plus its decompressed `data`, in one response.
        JSON indexes only, and — unlike `list` — not paginated: returns everything that
        matches `tags`/`key`."""
        params = build_list_params(limit=None, cursor=None, tags=tags, key=key)
        page = self._transport.get(
            f"indexes/{index_id}/items/data", response_type=ItemWithDataPageWire, params=params
        )
        return ItemWithDataPage(items=[_with_decoded_data(item) for item in page.items])

"""The `client.simple_items` resource: create and retrieve items with no index to create or
manage yourself — for "just store one thing and get it back."

Each item still lives in a real, implicit, per-principal index under the hood (chosen by
whether you call `create_json` or `create_blob`) — see `SimpleItem.index_id` /
`SimpleItemWithData.index_id` on the responses if you ever want to "graduate" to the full
`client.indexes`/`client.items` API for one of these items. Retrieval here is sandboxed to
items created this same way — it will never find an item from an explicitly-created index,
even one you own.
"""

from dataclasses import dataclass

import msgspec
from lothc import Form

from ._models import (
    CreateJsonItemRequest,
    JsonValue,
    SimpleItem,
    SimpleItemWithData,
    SimpleItemWithDataWire,
)
from ._transport import Transport


def _with_decoded_data(wire: SimpleItemWithDataWire) -> SimpleItemWithData:
    fields = msgspec.structs.asdict(wire)
    fields["data"] = msgspec.json.decode(wire.data)
    return SimpleItemWithData(**fields)


@dataclass
class SimpleItems:
    _transport: Transport

    def create_json(
        self, *, data: JsonValue, tags: dict[str, str] | None = None, key: str | None = None
    ) -> SimpleItem:
        body = CreateJsonItemRequest(tags=tags or {}, data=data, key=key)
        return self._transport.post("items", response_type=SimpleItem, json=body)

    def create_blob(
        self, *, data: bytes, tags: dict[str, str] | None = None, key: str | None = None
    ) -> SimpleItem:
        form: Form = {
            "tags": ("tags.json", msgspec.json.encode(tags or {}), "application/json"),
            "data": ("data.bin", data, "application/octet-stream"),
        }
        if key is not None:
            form["key"] = key
        return self._transport.post_form("items", response_type=SimpleItem, form=form)

    def get_json(self, item_id: str) -> JsonValue:
        raw = self._transport.get_bytes(f"items/{item_id}")
        return msgspec.json.decode(raw)

    def get_blob(self, item_id: str) -> bytes:
        return self._transport.get_bytes(f"items/{item_id}")

    def get_full(self, item_id: str) -> SimpleItemWithData:
        """Metadata plus decompressed `data` for one item. JSON items only — raises
        `ValidationError` (422 `wrong_index_type`) for a blob item."""
        wire = self._transport.get(f"items/{item_id}/full", response_type=SimpleItemWithDataWire)
        return _with_decoded_data(wire)

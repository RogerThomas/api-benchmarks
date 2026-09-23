"""msgspec Structs taglydb request bodies are built from and response bodies decode into.

lothc decodes JSON straight into these — no manual dict-mapping layer. Wire field names that
aren't already snake_case are aliased with `msgspec.field(name=...)`.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

import msgspec

type IndexType = Literal["blob", "json"]
# Item `data` is arbitrary valid JSON (ARCHITECTURE.md: "not merely an object"), so `Any` would be
# imprecise — this is any JSON-representable value, nothing else. Sequence/Mapping (not list/dict)
# so a concrete literal like {"a": [1, 2]} — whose inferred type is never literally
# `dict[str, JsonValue]` — is still structurally assignable; dict/list are invariant in their
# value type, Sequence/Mapping are covariant.
type JsonValue = bool | int | float | str | Sequence["JsonValue"] | Mapping[str, "JsonValue"] | None


class Principal(msgspec.Struct):
    """A principal that owns indexes and items."""

    id: str
    key: str
    tags: dict[str, str]
    created_at: datetime = msgspec.field(name="createdAt")


class PrincipalPage(msgspec.Struct):
    items: list[Principal]
    next_cursor: str | None = msgspec.field(name="nextCursor")


class CreatePrincipalRequest(msgspec.Struct):
    key: str
    tags: dict[str, str]


class NewCredential(msgspec.Struct):
    """The one-time full `sk-...` credential minted alongside a new principal."""

    id: str
    secret: str = msgspec.field(name="key")


class CreatedPrincipal(msgspec.Struct):
    """The response to creating a principal: the principal plus its first API key."""

    id: str
    key: str
    tags: dict[str, str]
    created_at: datetime = msgspec.field(name="createdAt")
    api_key: NewCredential = msgspec.field(name="apiKey")


class MintKeyRequest(msgspec.Struct):
    key: str


class MintedApiKey(msgspec.Struct):
    """A freshly minted API key, including its one-time `sk-...` secret."""

    id: str
    label: str = msgspec.field(name="key")
    secret: str = msgspec.field(name="credential")
    created_at: datetime = msgspec.field(name="createdAt")
    revoked_at: datetime | None = msgspec.field(name="revokedAt")


class ApiKeyInfo(msgspec.Struct):
    """Metadata about an API key. Listing never includes the secret."""

    id: str
    label: str = msgspec.field(name="key")
    created_at: datetime = msgspec.field(name="createdAt")
    revoked_at: datetime | None = msgspec.field(name="revokedAt")


class ApiKeyInfoPage(msgspec.Struct):
    items: list[ApiKeyInfo]
    next_cursor: str | None = msgspec.field(name="nextCursor")


class Index(msgspec.Struct):
    """An index: a typed (`json` or `blob`) container for items.

    `key` is optional — it's a first-order tag, not an identifier the server imposes; a
    keyless index is `None`.
    """

    id: str
    key: str | None
    type: IndexType
    tags: dict[str, str]
    created_at: datetime = msgspec.field(name="createdAt")


class IndexPage(msgspec.Struct):
    items: list[Index]
    next_cursor: str | None = msgspec.field(name="nextCursor")


class CreateIndexRequest(msgspec.Struct):
    # `key` last and defaulted — msgspec.Struct requires defaulted fields after undefaulted
    # ones, same as a dataclass; field order has no effect on the wire (JSON objects, not
    # positional). `key=None` encodes as a literal `"key":null`, which the server accepts as
    # exactly equivalent to the field being absent — no special encoding treatment needed.
    type: IndexType
    tags: dict[str, str]
    key: str | None = None


class Item(msgspec.Struct):
    """Item metadata — never the item's own data. See `Items.get_json`/`get_blob`.

    `key` is optional, same as `Index.key` — a keyless item is `None`.
    """

    id: str
    key: str | None
    tags: dict[str, str]
    created_at: datetime = msgspec.field(name="createdAt")
    size_bytes: int = msgspec.field(name="sizeBytes")
    stored_bytes: int = msgspec.field(name="storedBytes")
    encoding: str | None


class ItemPage(msgspec.Struct):
    items: list[Item]
    next_cursor: str | None = msgspec.field(name="nextCursor")


class CreateJsonItemRequest(msgspec.Struct):
    # See CreateIndexRequest's comment — key=None encodes as literal null, which the server
    # accepts as "no key."
    tags: dict[str, str]
    data: JsonValue
    key: str | None = None


class ItemWithData(Item):
    """Item metadata plus its decompressed `data` — the shape returned by the bulk
    `Items.list_with_data` and by `Items.get_full` (JSON indexes only)."""

    data: JsonValue


class ItemWithDataWire(Item):
    """Wire-decode counterpart of `ItemWithData` — msgspec can't decode directly into
    `JsonValue`'s self-referential union (confirmed empirically: it only resolves a forward
    reference back to a real class, not a bare recursive type alias), so `data` is decoded as
    undecoded raw JSON bytes here first. `Items` converts this to the public `ItemWithData`
    with `data` decoded separately."""

    data: msgspec.Raw


class ItemWithDataPage(msgspec.Struct):
    """Response of the bulk items/data listing — not paginated, so no `next_cursor`."""

    items: list[ItemWithData]


class ItemWithDataPageWire(msgspec.Struct):
    items: list[ItemWithDataWire]


class SimpleItem(Item):
    """An item created via the simple `client.simple_items` interface — same as `Item`, plus
    which (implicit, per-principal) index it actually landed in. See `SimpleItems`."""

    index_id: str = msgspec.field(name="indexId")


class SimpleItemWithData(SimpleItem):
    data: JsonValue


class SimpleItemWithDataWire(SimpleItem):
    """See `ItemWithDataWire` — same reason, same fix."""

    data: msgspec.Raw


class SignRequest(msgspec.Struct):
    view: Literal["data", "full"] | None = None
    expires_in: int | None = msgspec.field(name="expiresIn", default=None)


class SignedUrl(msgspec.Struct):
    """A time-limited, header-free URL for one item, minted server-side by `Tagly.sign`."""

    url: str
    expires_at: datetime = msgspec.field(name="expiresAt")

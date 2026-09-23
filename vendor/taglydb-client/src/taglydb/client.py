"""The two top-level clients: `Tagly` (storage) and `TaglyAdmin` (principal management).

Both are built via a `build()` classmethod, mirroring lothc's own `SyncHTTPClient.build()`
idiom, rather than a plain constructor:

    with Tagly.build(base_url="https://taglydb.example.com/", api_key="sk-...") as client:
        index = client.indexes.create(key="events", type="json", tags={})
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal, Self

from lothc import SyncHTTPClient

from ._models import SignedUrl, SignRequest
from ._transport import Transport
from .admin import Principals
from .indexes import Indexes
from .items import Items
from .simple_items import SimpleItems

_DEFAULT_TIMEOUT = 30.0


@dataclass
class Tagly:
    """A storage client authenticated as one principal via its `sk-...` API key."""

    _transport: Transport
    indexes: Indexes = field(init=False)
    items: Items = field(init=False)
    simple_items: SimpleItems = field(init=False)

    def __post_init__(self) -> None:
        self.indexes = Indexes(self._transport)
        self.items = Items(self._transport)
        self.simple_items = SimpleItems(self._transport)

    def sign(
        self,
        item_id: str,
        *,
        view: Literal["data", "full"] | None = None,
        expires_in: int | None = None,
    ) -> SignedUrl:
        """Mint a time-limited, header-free URL for one item, server-side. Works for any item
        you own regardless of which interface created it (`indexes`/`items` or
        `simple_items`) — not `client`-specific, it's just here because it takes only an item
        id, no index.
        """
        body = SignRequest(view=view, expires_in=expires_in)
        return self._transport.post(f"items/{item_id}/sign", response_type=SignedUrl, json=body)

    @classmethod
    @contextmanager
    def build(
        cls, *, base_url: str, api_key: str, timeout: float = _DEFAULT_TIMEOUT
    ) -> Generator[Self]:
        with SyncHTTPClient.build(
            base_url=base_url, bearer_token=api_key, timeout=timeout
        ) as http_client:
            yield cls(Transport(http_client))


@dataclass
class TaglyAdmin:
    """An admin client authenticated with the single admin bearer secret."""

    _transport: Transport
    principals: Principals = field(init=False)

    def __post_init__(self) -> None:
        self.principals = Principals(self._transport)

    @classmethod
    @contextmanager
    def build(
        cls, *, base_url: str, admin_secret: str, timeout: float = _DEFAULT_TIMEOUT
    ) -> Generator[Self]:
        with SyncHTTPClient.build(
            base_url=base_url, bearer_token=admin_secret, timeout=timeout
        ) as http_client:
            yield cls(Transport(http_client))

"""Python client for taglydb, built on lothc."""

from lothc import HTTPConnectionError, HTTPTimeoutError, HTTPTransportError

from ._errors import (
    AuthenticationError,
    ConflictError,
    ErrorDetail,
    NotFoundError,
    PayloadTooLargeError,
    TaglyError,
    ValidationError,
)
from ._models import (
    ApiKeyInfo,
    ApiKeyInfoPage,
    CreatedPrincipal,
    Index,
    IndexPage,
    Item,
    ItemPage,
    ItemWithData,
    ItemWithDataPage,
    MintedApiKey,
    NewCredential,
    Principal,
    PrincipalPage,
    SignedUrl,
    SimpleItem,
    SimpleItemWithData,
)
from .client import Tagly, TaglyAdmin

__all__ = [
    "ApiKeyInfo",
    "ApiKeyInfoPage",
    "AuthenticationError",
    "ConflictError",
    "CreatedPrincipal",
    "ErrorDetail",
    "HTTPConnectionError",
    "HTTPTimeoutError",
    "HTTPTransportError",
    "Index",
    "IndexPage",
    "Item",
    "ItemPage",
    "ItemWithData",
    "ItemWithDataPage",
    "MintedApiKey",
    "NewCredential",
    "NotFoundError",
    "PayloadTooLargeError",
    "Principal",
    "PrincipalPage",
    "SignedUrl",
    "SimpleItem",
    "SimpleItemWithData",
    "Tagly",
    "TaglyAdmin",
    "TaglyError",
    "ValidationError",
]

"""Exception hierarchy for the taglydb client."""

import msgspec
from lothc import HTTPResponseError


class ErrorDetail(msgspec.Struct):
    """The `{code, message, requestId}` envelope every taglydb error response carries."""

    code: str
    message: str
    request_id: str = msgspec.field(name="requestId")


class ErrorEnvelope(msgspec.Struct):
    """Wire shape of every taglydb error body: `{"error": {...}}`.

    Not part of the public API — pass this as `error_type=` to a Transport call so lothc
    decodes it onto `HTTPResponseError.parsed_body`, then hand the exception to `map_http_error`.
    """

    error: ErrorDetail


class TaglyError(Exception):
    """Base exception for every error the taglydb API returns."""

    def __init__(self, detail: ErrorDetail, status: int) -> None:
        self.detail = detail
        self.status = status
        super().__init__(f"{detail.code} ({status}): {detail.message}")


class AuthenticationError(TaglyError):
    """Missing, malformed, or invalid credentials (401)."""


class NotFoundError(TaglyError):
    """The resource does not exist, or is not owned by the authenticated principal (404)."""


class ConflictError(TaglyError):
    """A resource with that key already exists (409)."""


class PayloadTooLargeError(TaglyError):
    """The item payload exceeds taglydb's stored-size limit (413)."""


class ValidationError(TaglyError):
    """The request was malformed or semantically invalid (400/415/422)."""


_STATUS_TO_ERROR: dict[int, type[TaglyError]] = {
    400: ValidationError,
    401: AuthenticationError,
    404: NotFoundError,
    409: ConflictError,
    413: PayloadTooLargeError,
    415: ValidationError,
    422: ValidationError,
}

_UNKNOWN_DETAIL = ErrorDetail(code="unknown_error", message="Request failed", request_id="")


def map_http_error(error: HTTPResponseError) -> TaglyError:
    """Translate a raw lothc `HTTPResponseError` (decoded with `error_type=ErrorEnvelope`) into
    the taglydb exception hierarchy."""
    parsed = error.parsed_body
    detail = parsed.error if isinstance(parsed, ErrorEnvelope) else _UNKNOWN_DETAIL
    error_cls = _STATUS_TO_ERROR.get(error.status, TaglyError)
    return error_cls(detail, error.status)

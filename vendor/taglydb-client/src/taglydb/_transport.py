"""The one place that talks to lothc's `SyncHTTPClient` and translates its errors."""

from collections.abc import Callable
from dataclasses import dataclass

from lothc import Data, Form, HTTPResponseError, JSONPayload, Params, SyncHTTPClient

from ._errors import ErrorEnvelope, map_http_error


@dataclass
class Transport:
    _client: SyncHTTPClient

    def _request[T](self, send: Callable[[], T]) -> T:
        try:
            return send()
        except HTTPResponseError as error:
            raise map_http_error(error) from error

    def get[T: Data](self, path: str, *, response_type: type[T], params: Params | None = None) -> T:
        return self._request(
            lambda: self._client.get(
                path, params=params, response_data_type=response_type, error_type=ErrorEnvelope
            )
        )

    def get_bytes(self, path: str) -> bytes:
        return self._request(lambda: self._client.get(path, error_type=ErrorEnvelope))

    def post[T: Data](self, path: str, *, response_type: type[T], json: JSONPayload) -> T:
        return self._request(
            lambda: self._client.post(
                path, json=json, response_data_type=response_type, error_type=ErrorEnvelope
            )
        )

    def post_form[T: Data](self, path: str, *, response_type: type[T], form: Form) -> T:
        return self._request(
            lambda: self._client.post(
                path, form=form, response_data_type=response_type, error_type=ErrorEnvelope
            )
        )

    def delete(self, path: str) -> None:
        self._request(lambda: self._client.delete(path, error_type=ErrorEnvelope))

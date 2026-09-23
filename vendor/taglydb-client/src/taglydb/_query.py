"""Shared query-string construction for taglydb's cursor-paginated list endpoints."""


def build_list_params(
    *,
    limit: int | None,
    cursor: str | None,
    tags: dict[str, str] | None,
    key: str | None,
) -> dict[str, str | list[str | int | float | bool]]:
    # `list[str | int | float | bool]`, not `list[str]`, to match lothc's `Params` value type
    # exactly — `list` is invariant, so a plain `list[str]` isn't assignable to it even though
    # every element here is always a `str`.
    params: dict[str, str | list[str | int | float | bool]] = {}
    if limit is not None:
        params["limit"] = str(limit)
    if cursor is not None:
        params["cursor"] = cursor
    if tags is not None:
        # The server takes a repeatable `?tag=key=value` (AND across distinct keys) rather than a
        # single JSON-blob query param — lothc's `Params` sends a list value as one occurrence of
        # the query key per element, so this is the whole translation needed.
        params["tag"] = [f"{tag_key}={tag_value}" for tag_key, tag_value in tags.items()]
    if key is not None:
        params["key"] = key
    return params

"""Django Bolt benchmark app — the same 4 tests every framework here
implements (see apps/jero_app.py for the canonical contract):

1. GET /info        - medium JSON + a custom x-response-id header.
2. POST /movies      - JWT-authenticated (Bearer header, decoded with PyJWT
                        like every other framework in this fleet — Bolt's
                        own JWTAuthentication ties into django.contrib.auth's
                        User model, which this benchmark's tokens don't map
                        to, so it would be doing different work than
                        everyone else).
3. GET /catalog      - proxies the authenticated `upstream` service.
4. GET /users/me     - JWT-authenticated; reads the shared `users` row.

Response models are msgspec Structs — Bolt's own recommended response type,
and the same serializer jero/Litestar use (see README "Equal work, per test").

Named `api.py` (not `bolt_api.py`): `manage.py runbolt` autodiscovers
BoltAPI instances by looking for that exact module name in each installed app.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Literal
from uuid import uuid4

import jwt
import msgspec
from django.http import HttpResponse
from django_bolt import BoltAPI
from pyreqwest.client import ClientBuilder
from settings import Settings

from .models import User as UserRow

_settings = Settings()

api = BoltAPI(enable_logging=False)


def _decode_bearer(header: str) -> dict | None:
    token = header.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, _settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return {"id": payload["sub"], "name": payload["name"]}


# --- Test 1: GET /info -------------------------------------------------------


class Nested(msgspec.Struct):
    level: int
    label: str


type InfoTag = Literal["alpha", "beta", "gamma"]


class Info(msgspec.Struct):
    id: str
    name: str
    count: int
    ratio: float
    active: bool
    tags: list[InfoTag]
    created_at: str
    nested: Nested


@api.get("/info")
async def info():
    payload = Info(
        id="info-1",
        name="Benchmark Info",
        count=42,
        ratio=3.14159,
        active=True,
        tags=["alpha", "beta", "gamma"],
        created_at="2026-01-01T00:00:00Z",
        nested=Nested(level=2, label="nested"),
    )
    response = HttpResponse(msgspec.json.encode(payload), content_type="application/json")
    response["x-response-id"] = str(uuid4())
    return response


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


class MovieIn(msgspec.Struct):
    title: str
    year: int
    director: str
    genre: str
    rating: float


class UserOut(msgspec.Struct):
    id: str
    name: str


class Movie(msgspec.Struct):
    id: str
    user: UserOut
    title: str
    year: int
    director: str
    genre: str
    rating: float


@api.post("/movies", response_model=Movie, status_code=201)
async def create_movie(request, payload: MovieIn):
    # `request.headers` must be accessed directly in each handler's own body —
    # django_bolt statically analyzes each handler's AST to decide whether to
    # populate headers at all, and doesn't trace into helper calls like
    # `_decode_bearer(request)` would require.
    user = _decode_bearer(request.headers.get("authorization", ""))
    if user is None:
        return HttpResponse(status=401)
    return Movie(
        id=str(uuid4()),
        user=UserOut(**user),
        title=payload.title,
        year=payload.year,
        director=payload.director,
        genre=payload.genre,
        rating=payload.rating,
    )


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


_client_lock = asyncio.Lock()
_client = None


async def _upstream_client():
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                built = (
                    ClientBuilder()
                    .base_url(_settings.upstream_url)
                    .default_headers({"authorization": f"Bearer {_settings.upstream_api_key}"})
                    .error_for_status()
                    .connect_timeout(timedelta(seconds=1))
                    .read_timeout(timedelta(seconds=5))
                    .timeout(timedelta(seconds=10))
                    .follow_redirects(False)
                    .no_proxy()
                    .build()
                )
                await built.__aenter__()
                _client = built
    return _client


@api.get("/catalog")
async def catalog():
    client = await _upstream_client()
    upstream_response = await client.get("/data").build().send()
    body = await upstream_response.bytes()
    return HttpResponse(body, content_type="application/json")


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


class Profile(msgspec.Struct):
    id: str
    name: str
    email: str
    address: str
    city: str
    country: str


@api.get("/users/me")
async def users_me(request):
    user = _decode_bearer(request.headers.get("authorization", ""))
    if user is None:
        return HttpResponse(status=401)
    row = await UserRow.objects.aget(id=user["id"])
    response = Profile(
        id=row.id,
        name=row.name,
        email=row.email,
        address=row.address,
        city=row.city,
        country=row.country,
    )
    return HttpResponse(msgspec.json.encode(response), content_type="application/json")

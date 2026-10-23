"""Django Bolt benchmark app — the same 4 tests every framework here
implements (see apps/jero_app.py for the canonical contract):

1. GET /info        - medium JSON + a custom x-response-id header.
2. POST /movies      - JWT-authenticated (Bearer header, decoded with ryjwt
                        like every other framework in this fleet — Bolt's
                        own JWTAuthentication ties into django.contrib.auth's
                        User model, which this benchmark's tokens don't map
                        to, so it would be doing different work than
                        everyone else).
3. GET /catalog      - proxies the authenticated `upstream` service.
4. GET /users/me     - JWT-authenticated; reads the shared `users` row.

Handlers return msgspec Structs — Bolt's own recommended response type, and
the same serializer jero/Litestar use (see README "Equal work, per test").

Named `api.py` (not `bolt_api.py`): `manage.py runbolt` autodiscovers
BoltAPI instances by looking for that exact module name in each installed app.
"""

from __future__ import annotations

import asyncio
from typing import Literal
from uuid import uuid4

import fastpg
import msgspec
import ryjwt
from django_bolt import BoltAPI
from django_bolt.exceptions import NotFound, Unauthorized
from django_bolt.responses import JSON
from lothc import HTTPClient
from settings import Settings

_settings = Settings()

api = BoltAPI(enable_logging=False)


# camelCase on the wire, like every other framework in this fleet.
class CamelStruct(msgspec.Struct, rename="camel"): ...


class User(CamelStruct):
    id: str
    name: str


class Claims(msgspec.Struct):
    sub: str
    name: str


def _decode_bearer(header: str) -> User:
    token = header.removeprefix("Bearer ").strip()
    try:
        claims = _settings.jwt_key.decode(token, into=Claims)
    except ryjwt.InvalidTokenError as exc:  # includes a token missing sub/name
        raise Unauthorized(detail="invalid token") from exc
    return User(id=claims.sub, name=claims.name)


# --- Test 1: GET /info -------------------------------------------------------


class Nested(CamelStruct):
    level: int
    label: str


type InfoTag = Literal["alpha", "beta", "gamma"]


class Info(CamelStruct):
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
    return JSON(payload, headers={"x-response-id": str(uuid4())})


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


class MovieIn(CamelStruct):
    title: str
    year: int
    director: str
    genre: str
    rating: float


class Movie(CamelStruct):
    id: str
    user: User
    title: str
    year: int
    director: str
    genre: str
    rating: float


@api.post("/movies", status_code=201)
async def create_movie(request, payload: MovieIn) -> Movie:
    # `request.headers` must be accessed directly in each handler's own body —
    # django_bolt statically analyzes each handler's AST to decide whether to
    # populate headers at all, and doesn't trace into helper calls.
    user = _decode_bearer(request.headers.get("authorization", ""))
    return Movie(
        id=str(uuid4()),
        user=user,
        title=payload.title,
        year=payload.year,
        director=payload.director,
        genre=payload.genre,
        rating=payload.rating,
    )


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


class Vendor(CamelStruct):
    id: str
    name: str


type Tag = Literal["electronics", "peripherals", "keyboard"]


class Product(CamelStruct):
    id: str
    title: str
    price: float
    in_stock: bool
    tags: list[Tag]
    rating: float
    description: str
    vendor: Vendor


# The lothc client is opened on the first request (the serving loop).
_client: HTTPClient | None = None
_client_lock = asyncio.Lock()


async def _upstream_client() -> HTTPClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = await HTTPClient(**_settings.upstream_client_options).__aenter__()
    return _client


@api.get("/catalog")
async def catalog() -> Product:
    client = await _upstream_client()
    # lothc decodes the upstream body straight into the Product Struct.
    response = await client.get("data", into=Product)
    return response.data


# --- Test 4: GET /users/me (Postgres) ----------------------------------------
#
# Raw fastpg, not Django's ORM -- same driver every other async framework in
# this fleet uses; routing this through Django's ORM would be measuring
# Django's data layer rather than the framework (see README "Equal work, per
# test").


class Profile(CamelStruct):
    id: str
    name: str
    email: str
    address: str
    city: str
    country: str


_GET_USER_SQL = "SELECT id, name, email, address, city, country FROM users WHERE id = $1"

# fastpg runs on the asyncio loop that created the pool, so build it lazily on
# the first request (the serving loop), not at import time.
_db_pool: fastpg.Pool | None = None
_db_pool_lock = asyncio.Lock()


async def _get_db_pool() -> fastpg.Pool:
    global _db_pool
    if _db_pool is None:
        async with _db_pool_lock:
            if _db_pool is None:
                _db_pool = await fastpg.create_pool(
                    _settings.db_dsn, max_size=_settings.db_pool_size
                )
    return _db_pool


@api.get("/users/me")
async def users_me(request) -> Profile:
    user = _decode_bearer(request.headers.get("authorization", ""))
    pool = await _get_db_pool()
    try:
        return await pool.select_one(_GET_USER_SQL, user.id, into=Profile)
    except fastpg.NoRowsError:
        raise NotFound(detail="user not found") from None

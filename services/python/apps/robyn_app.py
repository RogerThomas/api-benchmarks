"""Robyn benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me).

Robyn ships its own Rust server; run with: python robyn_app.py --processes 1 --workers 1

Settings and the JWT key are provided through Robyn's global dependency
injection (``app.inject_global``); handlers receive them via the
``global_dependencies`` argument. The lothc client and the fastpg pool are the exceptions: both are
opened on the loop that serves requests, so they're built lazily on first use.
"""

import asyncio
import os
import uuid
from typing import Literal

import fastpg
import ryjwt
from lothc import HTTPClient
from pydantic import BaseModel
from robyn import Request, Response, Robyn, jsonify
from settings import Settings

_JSON = {"Content-Type": "application/json"}


# Robyn has first-class Pydantic support: a handler param annotated with a model
# validates the request body natively, and returning a model serialises it.
class MovieIn(BaseModel):
    title: str
    year: int
    director: str
    genre: str
    rating: float


class User(BaseModel):
    id: str
    name: str


class Movie(MovieIn):
    id: str
    user: User


class Vendor(BaseModel):
    id: str
    name: str


type Tag = Literal["electronics", "peripherals", "keyboard"]


class Product(BaseModel):
    id: str
    title: str
    price: float
    inStock: bool
    tags: list[Tag]
    rating: float
    description: str
    vendor: Vendor


class Claims(BaseModel):
    sub: str
    name: str


class Profile(BaseModel):
    id: str
    name: str
    email: str
    address: str
    city: str
    country: str


def build_dependencies() -> dict:
    """Build the shared resources Robyn injects into every route."""
    settings = Settings()
    return {"settings": settings, "jwt_key": ryjwt.SecretKey(settings.jwt_secret, algorithms=[settings.jwt_algorithm])}


app = Robyn(__file__)
app.inject_global(**build_dependencies())


def authenticate(request: Request, key: ryjwt.SecretKey) -> dict | None:
    """Decode the bearer JWT; return the user dict, or None if it's invalid."""
    authorization = request.headers.get("authorization") or ""
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = key.decode(token, into=Claims)
    except ryjwt.InvalidTokenError:  # includes a token missing sub/name
        return None
    return {"id": claims.sub, "name": claims.name}


# --- Test 1: GET /info -------------------------------------------------------


@app.get("/info")
def get_info(request: Request) -> Response:
    body = {
        "id": "info-1",
        "name": "Benchmark Info",
        "count": 42,
        "ratio": 3.14159,
        "active": True,
        "tags": ["alpha", "beta", "gamma"],
        "createdAt": "2026-01-01T00:00:00Z",
        "nested": {"level": 2, "label": "nested"},
    }
    headers = {**_JSON, "x-response-id": str(uuid.uuid4())}
    return Response(status_code=200, headers=headers, description=jsonify(body))


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


@app.post("/movies")
def create_movie(request: Request, global_dependencies, movie: MovieIn) -> Response:
    # `movie: MovieIn` is validated natively by Robyn from the request body.
    user = authenticate(request, global_dependencies["jwt_key"])
    if user is None:
        return Response(
            status_code=401,
            headers=_JSON,
            description=jsonify({"error": "invalid token"}),
        )
    result = Movie(id=str(uuid.uuid4()), user=User(**user), **movie.model_dump())
    return Response(status_code=201, headers=_JSON, description=result.model_dump_json())


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


# A lothc client must be entered (`async with`) before use; do that lazily on
# the first request (the serving loop), like the fastpg pool below.
_client: HTTPClient | None = None
_client_lock = asyncio.Lock()


async def _get_client(settings: Settings) -> HTTPClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = await HTTPClient(**settings.upstream_client_options).__aenter__()
    return _client


@app.get("/catalog")
async def catalog(request: Request, global_dependencies) -> Product:
    client = await _get_client(global_dependencies["settings"])
    # Auth rides on the client's bearer_token (set once at build time); lothc
    # validates the upstream payload into the model, which serialises natively.
    resp = await client.get("data", into=Product)
    return resp.data


# --- Test 4: GET /users/me (Postgres) ----------------------------------------

# fastpg runs on the asyncio loop that created the pool, so build it lazily on
# the first request (the serving loop), not in build_dependencies().
_db_pool: fastpg.Pool | None = None
_db_pool_lock = asyncio.Lock()


async def _get_db_pool(settings: Settings) -> fastpg.Pool:
    global _db_pool
    if _db_pool is None:
        async with _db_pool_lock:
            if _db_pool is None:
                _db_pool = await fastpg.create_pool(settings.db_dsn, max_size=settings.db_pool_size)
    return _db_pool


@app.get("/users/me")
async def users_me(request: Request, global_dependencies) -> Response:
    settings: Settings = global_dependencies["settings"]
    user = authenticate(request, global_dependencies["jwt_key"])
    if user is None:
        return Response(
            status_code=401,
            headers=_JSON,
            description=jsonify({"error": "invalid token"}),
        )
    pool = await _get_db_pool(settings)
    try:
        profile = await pool.select_one(
            "SELECT id, name, email, address, city, country FROM users WHERE id = $1",
            user["id"],
            into=Profile,
        )
    except fastpg.NoRowsError:
        return Response(
            status_code=404,
            headers=_JSON,
            description=jsonify({"error": "user not found"}),
        )
    return profile


if __name__ == "__main__":
    app.start(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

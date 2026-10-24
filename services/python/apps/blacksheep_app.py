"""Blacksheep benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me).

Settings, the JWT key, the lothc HTTP client and the fastpg pool live in BlackSheep's DI
container (rodi) and are injected into handlers by type. The client and pool are
opened/closed with ``@app.lifespan`` — BlackSheep's documented pattern for
resources bound to the application lifecycle. Request and upstream bodies are
validated with pydantic, which BlackSheep's docs recommend for validation.
"""

import uuid
from typing import Literal

import fastpg
import ryjwt
from blacksheep import Application, FromHeader, FromJSON
from blacksheep.server.responses import json
from lothc import HTTPClient
from pydantic import BaseModel
from settings import Settings

app = Application()
settings = Settings()
app.services.register(Settings, instance=settings)
app.services.register(ryjwt.SecretKey, instance=ryjwt.SecretKey(settings.jwt_secret, algorithms=[settings.jwt_algorithm]))


@app.lifespan
async def configure_http_client(app: Application):
    settings = app.services.resolve(Settings)
    async with HTTPClient(**settings.upstream_client_options) as client:
        app.services.register(HTTPClient, instance=client)
        yield


@app.lifespan
async def configure_db_pool(app: Application):
    settings = app.services.resolve(Settings)
    async with await fastpg.create_pool(settings.db_dsn, max_size=settings.db_pool_size) as pool:
        app.services.register(fastpg.Pool, instance=pool)
        yield


# Optional, so a missing header is a 401 (like any bad token), not a 400.
class AuthHeader(FromHeader[str | None]):
    name = "Authorization"


class User(BaseModel):
    id: str
    name: str


class Claims(BaseModel):
    sub: str
    name: str


def authenticate(authorization: AuthHeader, key: ryjwt.SecretKey) -> User | None:
    """Decode the bearer JWT; return the user, or None if it's invalid."""
    token = (authorization.value or "").removeprefix("Bearer ").strip()
    try:
        claims = key.decode(token, into=Claims)
    except ryjwt.InvalidTokenError:  # includes a token missing sub/name
        return None
    return User(id=claims.sub, name=claims.name)


# --- Test 1: GET /info -------------------------------------------------------


@app.router.get("/info")
async def get_info():
    response = json({
        "id": "info-1",
        "name": "Benchmark Info",
        "count": 42,
        "ratio": 3.14159,
        "active": True,
        "tags": ["alpha", "beta", "gamma"],
        "createdAt": "2026-01-01T00:00:00Z",
        "nested": {"level": 2, "label": "nested"},
    })
    response.add_header(b"x-response-id", str(uuid.uuid4()).encode())
    return response


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


class MovieIn(BaseModel):
    title: str
    year: int
    director: str
    genre: str
    rating: float


class Movie(MovieIn):
    id: str
    user: User


@app.router.post("/movies")
async def create_movie(authorization: AuthHeader, data: FromJSON[MovieIn], jwt_key: ryjwt.SecretKey):
    user = authenticate(authorization, jwt_key)
    if user is None:
        return json({"error": "invalid token"}, status=401)
    movie = Movie(id=str(uuid.uuid4()), user=user, **data.value.model_dump())
    return json(movie, status=201)


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


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


@app.router.get("/catalog")
async def catalog(client: HTTPClient):
    # Auth rides on the client's bearer_token (set once at build time); lothc
    # validates the upstream body straight into the pydantic model.
    resp = await client.get("data", into=Product)
    return json(resp.data)


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


class Profile(BaseModel):
    id: str
    name: str
    email: str
    address: str
    city: str
    country: str


@app.router.get("/users/me")
async def users_me(authorization: AuthHeader, pool: fastpg.Pool, jwt_key: ryjwt.SecretKey):
    user = authenticate(authorization, jwt_key)
    if user is None:
        return json({"error": "invalid token"}, status=401)
    try:
        profile = await pool.select_one(
            "SELECT id, name, email, address, city, country FROM users WHERE id = $1",
            user.id,
            into=Profile,
        )
    except fastpg.NoRowsError:
        return json({"error": "user not found"}, status=404)
    return json(profile)

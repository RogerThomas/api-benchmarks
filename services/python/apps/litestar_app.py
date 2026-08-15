"""Litestar benchmark app — tests 1 (GET info) and 2 (authenticated POST movie)."""

import uuid
from contextlib import asynccontextmanager
from typing import Literal

import jwt
import msgspec
import psqlpy
from litestar import Litestar, Request, Response, get, post
from litestar.datastructures import State
from litestar.di import Provide
from litestar.exceptions import NotAuthorizedException, NotFoundException
from pyreqwest.client import Client, ClientBuilder
from settings import Settings

_GET_USER_SQL = "SELECT id, name, email, address, city, country FROM users WHERE id = $1"


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
    createdAt: str
    nested: Nested


@get("/info")
async def get_info() -> Response[Info]:
    info = Info(
        id="info-1",
        name="Benchmark Info",
        count=42,
        ratio=3.14159,
        active=True,
        tags=["alpha", "beta", "gamma"],
        createdAt="2026-01-01T00:00:00Z",
        nested=Nested(level=2, label="nested"),
    )
    return Response(info, headers={"x-response-id": str(uuid.uuid4())})


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


class MovieIn(msgspec.Struct):
    title: str
    year: int
    director: str
    genre: str
    rating: float


class User(msgspec.Struct):
    id: str
    name: str


class Movie(msgspec.Struct):
    id: str
    title: str
    year: int
    director: str
    genre: str
    rating: float
    user: User


async def provide_user(request: Request, state: State) -> User:
    authorization = request.headers.get("Authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, state.settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise NotAuthorizedException("invalid token") from exc
    return User(id=payload["sub"], name=payload["name"])


@post("/movies", dependencies={"user": Provide(provide_user)})
async def create_movie(data: MovieIn, user: User) -> Movie:
    return Movie(
        id=str(uuid.uuid4()),
        title=data.title,
        year=data.year,
        director=data.director,
        genre=data.genre,
        rating=data.rating,
        user=user,
    )


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


class Vendor(msgspec.Struct):
    id: str
    name: str


type Tag = Literal["electronics", "peripherals", "keyboard"]


class Product(msgspec.Struct):
    id: str
    title: str
    price: float
    inStock: bool
    tags: list[Tag]
    rating: float
    description: str
    vendor: Vendor


@get("/catalog")
async def catalog(state: State) -> Product:
    client: Client = state.client
    # Auth rides on the client's default headers (set once at build time);
    # msgspec decodes straight from the response buffer (no copy).
    resp = await client.get("/data").build().send()
    return msgspec.json.decode(await resp.bytes(), type=Product)


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


class Profile(msgspec.Struct):
    id: str
    name: str
    email: str
    address: str
    city: str
    country: str


@get("/users/me", dependencies={"user": Provide(provide_user)})
async def users_me(state: State, user: User) -> Profile:
    pool: psqlpy.ConnectionPool = state.pool
    async with pool.acquire() as connection:
        result = await connection.execute(_GET_USER_SQL, [user.id])
    rows = result.result(as_tuple=True)
    if not rows:
        raise NotFoundException("user not found")
    return Profile(*rows[0])


@asynccontextmanager
async def lifespan(app: Litestar):
    settings = Settings()
    app.state.settings = settings
    pool = psqlpy.ConnectionPool(
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        db_name=settings.db_name,
        max_db_pool_size=settings.db_pool_size,
    )
    async with (
        ClientBuilder()
        .base_url(settings.upstream_url)
        .default_headers({"authorization": f"Bearer {settings.upstream_api_key}"})
        .build()
    ) as client:
        app.state.client = client
        app.state.pool = pool
        yield
    pool.close()


app = Litestar(route_handlers=[get_info, create_movie, catalog, users_me], lifespan=[lifespan])

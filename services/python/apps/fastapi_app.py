"""FastAPI benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me)."""

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import jwt
import psqlpy
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel
from pyreqwest.client import Client, ClientBuilder
from settings import Settings

_GET_USER_SQL = "SELECT id, name, email, address, city, country FROM users WHERE id = $1"


@lru_cache
def _get_settings() -> Settings:
    """FastAPI's recommended settings pattern: a cached dependency."""
    return Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = _get_settings()
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
        app.state.auth = AuthService(settings.jwt_secret)
        app.state.user_service = UserService(pool)
        app.state.catalog_service = CatalogService(client)
        yield
    pool.close()


app = FastAPI(lifespan=lifespan)


# --- Test 1: GET /info -------------------------------------------------------


class Nested(BaseModel):
    level: int
    label: str


type InfoTag = Literal["alpha", "beta", "gamma"]


class Info(BaseModel):
    id: str
    name: str
    count: int
    ratio: float
    active: bool
    tags: list[InfoTag]
    createdAt: str
    nested: Nested


@app.get("/info")
async def get_info(response: Response) -> Info:
    response.headers["x-response-id"] = str(uuid.uuid4())
    return Info(
        id="info-1",
        name="Benchmark Info",
        count=42,
        ratio=3.14159,
        active=True,
        tags=["alpha", "beta", "gamma"],
        createdAt="2026-01-01T00:00:00Z",
        nested=Nested(level=2, label="nested"),
    )


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


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


@dataclass(slots=True)
class AuthService:
    """Verifies the bearer JWT. Built once in the lifespan, shared via app.state."""

    jwt_secret: str

    def authenticate(self, authorization: str) -> User:
        token = authorization.removeprefix("Bearer ").strip()
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="invalid token")
        return User(id=payload["sub"], name=payload["name"])


# Async dependency: runs on the event loop (no threadpool hop, unlike a sync
# dependency). Pulls the shared AuthService off app.state and verifies the header.
async def current_user(request: Request, authorization: str = Header()) -> User:
    auth: AuthService = request.app.state.auth
    return auth.authenticate(authorization)


@app.post("/movies", status_code=201)
async def create_movie(movie: MovieIn, user: User = Depends(current_user)) -> Movie:
    return Movie(id=str(uuid.uuid4()), user=user, **movie.model_dump())


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


@dataclass(slots=True)
class CatalogService:
    """Proxies the API-key-protected upstream. Built once in the lifespan and shared."""

    _client: Client

    async def fetch(self) -> Product:
        # Auth rides on the client's default headers (set once at build time).
        resp = await self._client.get("/data").build().send()
        # bytes(): the body is consume-once, and pydantic wants bytes, not a buffer.
        return Product.model_validate_json(bytes(await resp.bytes()))


async def _get_catalog_service(request: Request) -> CatalogService:
    return request.app.state.catalog_service


@app.get("/catalog")
async def catalog(
    catalog_service: CatalogService = Depends(_get_catalog_service),
) -> Product:
    return await catalog_service.fetch()


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


class Profile(BaseModel):
    id: str
    name: str
    email: str
    address: str
    city: str
    country: str


@dataclass(slots=True)
class UserService:
    """Reads user profiles from Postgres. Built once in the lifespan and shared."""

    _pool: psqlpy.ConnectionPool

    async def get_profile(self, user_id: str) -> Profile:
        async with self._pool.acquire() as connection:
            result = await connection.execute(_GET_USER_SQL, [user_id])
        rows = result.result(as_tuple=True)
        if not rows:
            raise HTTPException(status_code=404, detail="user not found")
        row = rows[0]
        return Profile(
            id=row[0],
            name=row[1],
            email=row[2],
            address=row[3],
            city=row[4],
            country=row[5],
        )


async def _get_user_service(request: Request) -> UserService:
    return request.app.state.user_service


@app.get("/users/me")
async def users_me(
    user: User = Depends(current_user),
    user_service: UserService = Depends(_get_user_service),
) -> Profile:
    return await user_service.get_profile(user.id)

"""FastAPI benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me)."""

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Literal

import fastpg
import ryjwt
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response
from lothc import HTTPClient
from pydantic import BaseModel
from settings import Settings

_GET_USER_SQL = "SELECT id, name, email, address, city, country FROM users WHERE id = $1"


@lru_cache
def _get_settings() -> Settings:
    """FastAPI's recommended settings pattern: a cached dependency."""
    return Settings()


# Routes are collected on a router and mounted at the bottom, once the services
# the lifespan builds are defined (FastAPI's "Bigger Applications" layout).
router = APIRouter()


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


@router.get("/info")
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


class Claims(BaseModel):
    sub: str
    name: str


@dataclass(slots=True)
class AuthService:
    """Verifies the bearer JWT. Built once in the lifespan, shared via app.state."""

    jwt_key: ryjwt.SecretKey

    def authenticate(self, authorization: str) -> User:
        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = self.jwt_key.decode(token, into=Claims)
        except ryjwt.InvalidTokenError:  # includes a token missing sub/name
            raise HTTPException(status_code=401, detail="invalid token")
        return User(id=claims.sub, name=claims.name)


# Async dependency: runs on the event loop (no threadpool hop, unlike a sync
# dependency). Pulls the shared AuthService off app.state and verifies the header
# (a missing header is "" here, so it's a 401 like any bad token, not a 422).
async def _get_current_user(request: Request, authorization: str = Header(default="")) -> User:
    auth: AuthService = request.app.state.auth
    return auth.authenticate(authorization)


type UserDep = Annotated[User, Depends(_get_current_user)]


@router.post("/movies", status_code=201)
async def create_movie(movie: MovieIn, user: UserDep) -> Movie:
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

    _client: HTTPClient

    async def fetch(self) -> Product:
        # Auth rides on the client's bearer_token (set once at build time); lothc
        # validates the body straight into the pydantic model.
        resp = await self._client.get("data", into=Product)
        return resp.data


async def _get_catalog_service(request: Request) -> CatalogService:
    return request.app.state.catalog_service


type CatalogServiceDep = Annotated[CatalogService, Depends(_get_catalog_service)]


@router.get("/catalog")
async def catalog(catalog_service: CatalogServiceDep) -> Product:
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

    _pool: fastpg.Pool

    async def get_profile(self, user_id: str) -> Profile:
        try:
            return await self._pool.select_one(_GET_USER_SQL, user_id, into=Profile)
        except fastpg.NoRowsError:
            raise HTTPException(status_code=404, detail="user not found") from None


async def _get_user_service(request: Request) -> UserService:
    return request.app.state.user_service


type UserServiceDep = Annotated[UserService, Depends(_get_user_service)]


@router.get("/users/me")
async def users_me(user: UserDep, user_service: UserServiceDep) -> Profile:
    return await user_service.get_profile(user.id)


# --- Wiring ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = _get_settings()
    async with (
        await fastpg.create_pool(settings.db_dsn, max_size=settings.db_pool_size) as pool,
        HTTPClient(**settings.upstream_client_options) as client,
    ):
        app.state.auth = AuthService(ryjwt.SecretKey(settings.jwt_secret, algorithms=[settings.jwt_algorithm]))
        app.state.user_service = UserService(pool)
        app.state.catalog_service = CatalogService(client)
        yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)

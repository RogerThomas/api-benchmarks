"""jero benchmark app — tests 1 (GET info), 2 (authenticated POST movie),
3 (proxy an API-key-protected upstream), 4 (GET /users/me from Postgres).
"""

from dataclasses import dataclass
from functools import cached_property
from typing import Literal
from uuid import UUID, uuid4

import fastpg
import ryjwt
from jero import (
    AuthenticationRequiredError,
    BaseApp,
    BaseFactory,
    Endpoint,
    JSONResponse,
    NotFoundError,
    Resource,
)
from lothc import HTTPClient
from msgspec import Struct
from settings import Settings


class CamelStruct(Struct, rename="camel"): ...


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


class InfoHeaders(Struct):
    x_response_id: UUID


class InfoEndpoint(Endpoint, path="/info"):
    async def get(self) -> JSONResponse[Info, InfoHeaders]:
        info = Info(
            id="info-1",
            name="Benchmark Info",
            count=42,
            ratio=3.14159,
            active=True,
            tags=["alpha", "beta", "gamma"],
            created_at="2026-01-01T00:00:00Z",
            nested=Nested(level=2, label="nested"),
        )
        return JSONResponse(json=info, headers=InfoHeaders(x_response_id=uuid4()))


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


class MovieIn(CamelStruct):
    title: str
    year: int
    director: str
    genre: str
    rating: float


class User(CamelStruct):
    id: str
    name: str


class Movie(MovieIn):
    id: UUID
    user: User


class Credentials(Struct):
    authorization: str


class Claims(Struct):
    sub: str
    name: str


@dataclass(frozen=True, slots=True)
class JWTAuth:
    _jwt_key: ryjwt.SecretKey

    def authenticate(self, headers: Credentials) -> User:
        token = headers.authorization.removeprefix("Bearer ").strip()
        try:
            claims = self._jwt_key.decode(token, into=Claims)
        except ryjwt.InvalidTokenError as exc:
            raise AuthenticationRequiredError() from exc
        return User(id=claims.sub, name=claims.name)


class MoviesResource(Resource, path="/movies"):
    async def create(self, json: MovieIn, user: User) -> Movie:
        return Movie(
            id=uuid4(),
            user=user,
            title=json.title,
            year=json.year,
            director=json.director,
            genre=json.genre,
            rating=json.rating,
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


@dataclass(slots=True)
class CatalogService:
    _client: HTTPClient

    async def fetch(self) -> Product:
        # lothc decodes the upstream body straight into the Product Struct.
        response = await self._client.get("data", into=Product)
        return response.data


@dataclass
class CatalogEndpoint(Endpoint, path="/catalog"):
    _service: CatalogService

    async def get(self) -> Product:
        return await self._service.fetch()


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


class Profile(CamelStruct):
    id: str
    name: str
    email: str
    address: str
    city: str
    country: str


@dataclass(slots=True)
class UserService:
    _pool: fastpg.Pool

    async def get_profile(self, user_id: str) -> Profile:
        try:
            return await self._pool.select_one(
                "SELECT id, name, email, address, city, country FROM users WHERE id = $1",
                user_id,
                into=Profile,
            )
        except fastpg.NoRowsError:
            raise NotFoundError() from None


@dataclass
class UsersMeEndpoint(Endpoint, path="/users/me"):
    _service: UserService

    async def get(self, user: User) -> Profile:
        return await self._service.get_profile(user.id)


# --- Wiring ------------------------------------------------------------------


class Factory(BaseFactory):
    @cached_property
    def _settings(self) -> Settings:
        return Settings()

    def create_auth(self) -> JWTAuth:
        return JWTAuth(self._settings.jwt_key)

    async def create_catalog_service(self) -> CatalogService:
        client = await self._aenter(HTTPClient(**self._settings.upstream_client_options))
        return CatalogService(client)

    async def create_user_service(self) -> UserService:
        pool = await self._aenter(
            await fastpg.create_pool(self._settings.db_dsn, max_size=self._settings.db_pool_size)
        )
        return UserService(pool)


class App(BaseApp[Factory]):
    async def wire(self) -> None:
        auth = self._factory.create_auth()
        catalog = await self._factory.create_catalog_service()
        users = await self._factory.create_user_service()
        self._include_endpoint(InfoEndpoint())
        self._include_endpoint(CatalogEndpoint(catalog))
        self._include_endpoint(UsersMeEndpoint(users), auth=auth)
        self._include_resource(MoviesResource(), auth=auth)


app = App()

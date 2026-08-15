"""jero benchmark app — tests 1 (GET info), 2 (authenticated POST movie),
3 (proxy an API-key-protected upstream), 4 (GET /users/me from Postgres).
"""

from dataclasses import dataclass, field
from datetime import timedelta
from functools import cached_property
from typing import Literal
from uuid import UUID, uuid4

import jwt
import msgspec
import psqlpy
from jero import BaseApp, BaseFactory, Endpoint, HTTPError, JSONResponse, Resource
from msgspec import Struct
from pyreqwest.client import Client, ClientBuilder
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


@dataclass(frozen=True, slots=True)
class JWTAuth:
    _jwt_secret: str

    def authenticate(self, headers: Credentials) -> User:
        token = headers.authorization.removeprefix("Bearer ").strip()
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise HTTPError() from exc
        return User(id=payload["sub"], name=payload["name"])


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


@dataclass
class UpstreamClient:
    _client: Client
    _product_decoder: msgspec.json.Decoder[Product] = field(
        default_factory=lambda: msgspec.json.Decoder(Product)
    )

    async def fetch_product(self) -> Product:
        response = await self._client.get("/data").build().send()
        # The body is consume-once (reqwest semantics): read bytes, decode from those.
        return self._product_decoder.decode(await response.bytes())


@dataclass(slots=True)
class CatalogService:
    _client: UpstreamClient

    async def fetch(self) -> Product:
        return await self._client.fetch_product()


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
    _pool: psqlpy.ConnectionPool

    async def get_profile(self, user_id: str) -> Profile:
        async with self._pool.acquire() as connection:
            result = await connection.execute(
                "SELECT id, name, email, address, city, country FROM users WHERE id = $1",
                [user_id],
            )
        rows = result.result(as_tuple=True)
        if not rows:
            raise HTTPError()
        db_profile = rows[0]
        return Profile(
            id=db_profile[0],
            name=db_profile[1],
            email=db_profile[2],
            address=db_profile[3],
            city=db_profile[4],
            country=db_profile[5],
        )


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
        return JWTAuth(self._settings.jwt_secret)

    async def create_catalog_service(self) -> CatalogService:
        upstream_client = UpstreamClient(
            await self._aenter(
                ClientBuilder()
                .base_url(self._settings.upstream_url)
                .default_headers({"authorization": f"Bearer {self._settings.upstream_api_key}"})
                .error_for_status()
                .connect_timeout(timedelta(seconds=1))
                .read_timeout(timedelta(seconds=5))
                .timeout(timedelta(seconds=10))
                .follow_redirects(False)
                .no_proxy()
                .build()
            ),
        )
        return CatalogService(upstream_client)

    def create_user_service(self) -> UserService:
        pool = self._enter(
            psqlpy.ConnectionPool(
                username=self._settings.db_user,
                password=self._settings.db_password,
                host=self._settings.db_host,
                port=self._settings.db_port,
                db_name=self._settings.db_name,
                max_db_pool_size=self._settings.db_pool_size,
            )
        )
        return UserService(pool)


class App(BaseApp[Factory]):
    async def wire(self) -> None:
        auth = self._factory.create_auth()
        catalog = await self._factory.create_catalog_service()
        users = self._factory.create_user_service()
        self._include_endpoint(InfoEndpoint())
        self._include_endpoint(CatalogEndpoint(catalog))
        self._include_endpoint(UsersMeEndpoint(users), auth=auth)
        self._include_resource(MoviesResource(), auth=auth)


app = App()

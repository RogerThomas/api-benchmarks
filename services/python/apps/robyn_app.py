"""Robyn benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me).

Robyn ships its own Rust server; run with: python robyn_app.py --processes 1 --workers 1

Settings, the pyreqwest client and the psqlpy pool are provided through Robyn's
global dependency injection (``app.inject_global``) rather than module-level
globals; handlers receive them via the ``global_dependencies`` argument.
"""

import json as jsonlib
import os
import uuid
from typing import Literal

import jwt
import psqlpy
from pydantic import BaseModel
from pyreqwest.client import Client, ClientBuilder
from robyn import Request, Response, Robyn
from settings import Settings

_GET_USER_SQL = "SELECT id, name, email, address, city, country FROM users WHERE id = $1"
_JSON = {"Content-Type": "application/json"}


# Robyn has first-class Pydantic support: a handler param annotated with a model
# validates the request body natively, and returning a model serialises it (orjson).
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
    return {
        "settings": settings,
        "client": (
            ClientBuilder()
            .base_url(settings.upstream_url)
            .default_headers({"authorization": f"Bearer {settings.upstream_api_key}"})
            .build()
        ),
        "pool": psqlpy.ConnectionPool(
            username=settings.db_user,
            password=settings.db_password,
            host=settings.db_host,
            port=settings.db_port,
            db_name=settings.db_name,
            max_db_pool_size=settings.db_pool_size,
        ),
    }


app = Robyn(__file__)
app.inject_global(**build_dependencies())


def authenticate(request: Request, secret: str) -> dict | None:
    """Decode the bearer JWT; return the user dict, or None if it's invalid."""
    authorization = request.headers.get("authorization") or ""
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return {"id": payload["sub"], "name": payload["name"]}


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
    return Response(status_code=200, headers=headers, description=jsonlib.dumps(body))


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


@app.post("/movies")
def create_movie(request: Request, global_dependencies, movie: MovieIn) -> Response:
    # `movie: MovieIn` is validated natively by Robyn from the request body.
    user = authenticate(request, global_dependencies["settings"].jwt_secret)
    if user is None:
        return Response(
            status_code=401,
            headers=_JSON,
            description=jsonlib.dumps({"error": "invalid token"}),
        )
    result = Movie(id=str(uuid.uuid4()), user=User(**user), **movie.model_dump())
    return Response(status_code=201, headers=_JSON, description=result.model_dump_json())


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


@app.get("/catalog")
async def catalog(request: Request, global_dependencies) -> Product:
    client: Client = global_dependencies["client"]
    # Auth rides on the client's default headers (set once at build time).
    resp = await client.get("/data").build().send()
    # Validate the upstream payload into a model; returning it serialises natively.
    # bytes(): pydantic wants str/bytes/bytearray — it rejects pyreqwest's buffer.
    return Product.model_validate_json(bytes(await resp.bytes()))


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


@app.get("/users/me")
async def users_me(request: Request, global_dependencies) -> Response:
    settings: Settings = global_dependencies["settings"]
    pool: psqlpy.ConnectionPool = global_dependencies["pool"]
    user = authenticate(request, settings.jwt_secret)
    if user is None:
        return Response(
            status_code=401,
            headers=_JSON,
            description=jsonlib.dumps({"error": "invalid token"}),
        )
    async with pool.acquire() as connection:
        result = await connection.execute(_GET_USER_SQL, [user["id"]])
    rows = result.result(as_tuple=True)
    if not rows:
        return Response(
            status_code=404,
            headers=_JSON,
            description=jsonlib.dumps({"error": "user not found"}),
        )
    row = rows[0]
    return Profile(
        id=row[0], name=row[1], email=row[2], address=row[3], city=row[4], country=row[5]
    )


if __name__ == "__main__":
    app.start(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

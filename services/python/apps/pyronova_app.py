"""Pyronova benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me).

Pyronova ships its own Rust server; run with: python pyronova_app.py

Pyronova's headline mode runs handlers in PEP 684 own-GIL sub-interpreters, but
the C extensions this fleet shares (pydantic-core, pyreqwest, psqlpy) don't load
there (pydantic raises, pyreqwest hangs — checked on 2.7.0). So it runs in
``mode="gil"``: every handler on the main interpreter, one worker, like Robyn with
``--processes 1``. Async handlers still run on its Rust-driven asyncio loop.
"""

import json as jsonlib
import os
import uuid
from typing import Literal

import jwt
import psqlpy
from pydantic import BaseModel
from pyreqwest.client import ClientBuilder
from pyronova import Pyronova, Request, Response
from settings import Settings

_GET_USER_SQL = "SELECT id, name, email, address, city, country FROM users WHERE id = $1"
_JSON = "application/json"


# Pyronova validates a pydantic body natively via the route's ``model=`` argument.
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


settings = Settings()
client = (
    ClientBuilder()
    .base_url(settings.upstream_url)
    .default_headers({"authorization": f"Bearer {settings.upstream_api_key}"})
    .build()
)
pool = psqlpy.ConnectionPool(
    username=settings.db_user,
    password=settings.db_password,
    host=settings.db_host,
    port=settings.db_port,
    db_name=settings.db_name,
    max_db_pool_size=settings.db_pool_size,
)

app = Pyronova()


def authenticate(request: Request) -> dict | None:
    """Decode the bearer JWT; return the user dict, or None if it's invalid."""
    authorization = request.headers.get("authorization") or ""
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return {"id": payload["sub"], "name": payload["name"]}


def _error(status_code: int, message: str) -> Response:
    return Response(
        body=jsonlib.dumps({"error": message}), status_code=status_code, content_type=_JSON
    )


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
    return Response(
        body=jsonlib.dumps(body),
        content_type=_JSON,
        headers={"x-response-id": str(uuid.uuid4())},
    )


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


@app.post("/movies", model=MovieIn)
def create_movie(request: Request, movie: MovieIn) -> Response:
    user = authenticate(request)
    if user is None:
        return _error(401, "invalid token")
    result = Movie(id=str(uuid.uuid4()), user=User(**user), **movie.model_dump())
    return Response(body=result.model_dump_json(), status_code=201, content_type=_JSON)


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


@app.get("/catalog")
async def catalog(request: Request) -> Response:
    # Auth rides on the client's default headers (set once at build time).
    resp = await client.get("/data").build().send()
    # bytes(): pydantic wants str/bytes/bytearray — it rejects pyreqwest's buffer.
    product = Product.model_validate_json(bytes(await resp.bytes()))
    return Response(body=product.model_dump_json(), content_type=_JSON)


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


@app.get("/users/me")
async def users_me(request: Request) -> Response:
    user = authenticate(request)
    if user is None:
        return _error(401, "invalid token")
    async with pool.acquire() as connection:
        result = await connection.execute(_GET_USER_SQL, [user["id"]])
    rows = result.result(as_tuple=True)
    if not rows:
        return _error(404, "user not found")
    row = rows[0]
    profile = Profile(
        id=row[0], name=row[1], email=row[2], address=row[3], city=row[4], country=row[5]
    )
    return Response(body=profile.model_dump_json(), content_type=_JSON)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        workers=int(os.environ.get("WORKERS", "1")),
        io_workers=1,
        mode="gil",
    )

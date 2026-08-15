"""Blacksheep benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me).

Settings, the pyreqwest HTTP client and the psqlpy pool live in BlackSheep's DI
container (rodi) and are injected into handlers by type. The client and pool are
opened/closed with ``@app.lifespan`` — BlackSheep's documented pattern for
resources bound to the application lifecycle.
"""

import uuid
from dataclasses import dataclass

import jwt
import psqlpy
from blacksheep import Application, FromHeader, FromJSON
from blacksheep.server.responses import json
from pyreqwest.client import Client, ClientBuilder
from settings import Settings

_GET_USER_SQL = "SELECT id, name, email, address, city, country FROM users WHERE id = $1"

app = Application()
app.services.register(Settings, instance=Settings())


@app.lifespan
async def configure_http_client(app: Application):
    settings = app.services.resolve(Settings)
    async with (
        ClientBuilder()
        .base_url(settings.upstream_url)
        .default_headers({"authorization": f"Bearer {settings.upstream_api_key}"})
        .build()
    ) as client:
        app.services.register(Client, instance=client)
        yield


@app.lifespan
async def configure_db_pool(app: Application):
    settings = app.services.resolve(Settings)
    pool = psqlpy.ConnectionPool(
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        db_name=settings.db_name,
        max_db_pool_size=settings.db_pool_size,
    )
    app.services.register(psqlpy.ConnectionPool, instance=pool)
    yield
    pool.close()


class AuthHeader(FromHeader[str]):
    name = "Authorization"


def authenticate(authorization: AuthHeader, secret: str) -> dict | None:
    """Decode the bearer JWT; return the user dict, or None if it's invalid."""
    token = authorization.value.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return {"id": payload["sub"], "name": payload["name"]}


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


@dataclass
class MovieIn:
    title: str
    year: int
    director: str
    genre: str
    rating: float


@app.router.post("/movies")
async def create_movie(authorization: AuthHeader, data: FromJSON[MovieIn], settings: Settings):
    user = authenticate(authorization, settings.jwt_secret)
    if user is None:
        return json({"error": "invalid token"}, status=401)
    movie = data.value
    return json(
        {
            "id": str(uuid.uuid4()),
            "title": movie.title,
            "year": movie.year,
            "director": movie.director,
            "genre": movie.genre,
            "rating": movie.rating,
            "user": user,
        },
        status=201,
    )


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


@app.router.get("/catalog")
async def catalog(client: Client):
    # Auth rides on the client's default headers (set once at build time).
    resp = await client.get("/data").build().send()
    return json(await resp.json())


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


@app.router.get("/users/me")
async def users_me(authorization: AuthHeader, pool: psqlpy.ConnectionPool, settings: Settings):
    user = authenticate(authorization, settings.jwt_secret)
    if user is None:
        return json({"error": "invalid token"}, status=401)
    async with pool.acquire() as connection:
        result = await connection.execute(_GET_USER_SQL, [user["id"]])
    rows = result.result(as_tuple=True)
    if not rows:
        return json({"error": "user not found"}, status=404)
    row = rows[0]
    return json({
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "address": row[3],
        "city": row[4],
        "country": row[5],
    })

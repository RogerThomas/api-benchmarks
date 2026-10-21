"""Wred benchmark app — info, validated movies, upstream proxy, and user profiles.

Wred handles HTTP scopes only. The lifespan wrapper keeps one pyreqwest client
and psqlpy pool per worker, with the same resource lifecycle as the other apps.
Body validation follows Wred's msgspec example; responses use Wred's orjson.
"""

import traceback
import uuid
from contextlib import asynccontextmanager

import jwt
import msgspec
import psqlpy
from pyreqwest.client import ClientBuilder
from settings import Settings
from wred import App, Request

_GET_USER_SQL = "SELECT id, name, email, address, city, country FROM users WHERE id = $1"
settings = Settings()
api = App()


class BenchmarkApp:
    @asynccontextmanager
    async def resources(self):
        self.pool = psqlpy.ConnectionPool(
            username=settings.db_user,
            password=settings.db_password,
            host=settings.db_host,
            port=settings.db_port,
            db_name=settings.db_name,
            max_db_pool_size=settings.db_pool_size,
        )
        try:
            async with (
                ClientBuilder()
                .base_url(settings.upstream_url)
                .default_headers({"authorization": f"Bearer {settings.upstream_api_key}"})
                .build()
            ) as self.client:
                yield
        finally:
            self.pool.close()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "lifespan":
            return await api(scope, receive, send)

        await receive()  # lifespan.startup
        started = False
        try:
            async with self.resources():
                await send({"type": "lifespan.startup.complete"})
                started = True
                await receive()  # lifespan.shutdown
        except Exception:  # ASGI requires reporting startup/shutdown failures to the server.
            phase = "shutdown" if started else "startup"
            await send({"type": f"lifespan.{phase}.failed", "message": traceback.format_exc()})
            return
        await send({"type": "lifespan.shutdown.complete"})


app = BenchmarkApp()


def authenticate(request: Request) -> dict | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if not isinstance(payload.get("sub"), str) or not isinstance(payload.get("name"), str):
        return None
    return {"id": payload["sub"], "name": payload["name"]}


# --- Test 1: GET /info -------------------------------------------------------

_INFO = {
    "id": "info-1",
    "name": "Benchmark Info",
    "count": 42,
    "ratio": 3.14159,
    "active": True,
    "tags": ["alpha", "beta", "gamma"],
    "createdAt": "2026-01-01T00:00:00Z",
    "nested": {"level": 2, "label": "nested"},
}


@api.route("/info")
async def get_info(request: Request):
    return (
        _INFO,
        "application/json",
        200,
        [("x-response-id", str(uuid.uuid4()))],
    )


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


class MovieIn(msgspec.Struct):
    title: str
    year: int
    director: str
    genre: str
    rating: float


_movie_decoder = msgspec.json.Decoder(MovieIn)


@api.route("/movies", methods=["POST"])
async def create_movie(request: Request):
    user = authenticate(request)
    if user is None:
        return {"error": "invalid token"}, "application/json", 401
    try:
        movie = _movie_decoder.decode(await request.body())
    except msgspec.DecodeError:
        return {"error": "invalid movie"}, "application/json", 422
    return (
        {
            "id": str(uuid.uuid4()),
            "title": movie.title,
            "year": movie.year,
            "director": movie.director,
            "genre": movie.genre,
            "rating": movie.rating,
            "user": user,
        },
        "application/json",
        201,
    )


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


@api.route("/catalog")
async def catalog(request: Request):
    response = await app.client.get("/data").build().send()
    return await response.json()


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


@api.route("/users/me")
async def users_me(request: Request):
    user = authenticate(request)
    if user is None:
        return {"error": "invalid token"}, "application/json", 401
    async with app.pool.acquire() as connection:
        result = await connection.execute(_GET_USER_SQL, [user["id"]])
    rows = result.result(as_tuple=True)
    if not rows:
        return {"error": "user not found"}, "application/json", 404
    row = rows[0]
    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "address": row[3],
        "city": row[4],
        "country": row[5],
    }

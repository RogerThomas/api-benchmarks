"""Flask benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me).

Flask is WSGI; served under granian's WSGI interface. Uses Flask's recommended
application-factory pattern: settings live in ``app.config``, and the shared
pyreqwest sync client + psycopg pool are attached to ``app.extensions``, reached
in handlers via ``current_app`` (no module-level globals).
"""

import functools
import uuid
from collections.abc import Callable
from typing import Literal

import jwt
from flask import Blueprint, Flask, current_app, g, jsonify, request
from psycopg_pool import ConnectionPool
from pydantic import BaseModel
from pyreqwest.client import SyncClient, SyncClientBuilder
from settings import Settings

_GET_USER_SQL = "SELECT id, name, email, address, city, country FROM users WHERE id = %s"

bp = Blueprint("bench", __name__)


# Flask ships no validation; pydantic is the idiomatic modern choice (matches
# FastAPI). Used to validate the movie body (test 2) and the upstream payload
# (test 3) so Flask does the same parse+validate work as the typed frameworks.
class MovieIn(BaseModel):
    title: str
    year: int
    director: str
    genre: str
    rating: float


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


def auth_required(view: Callable) -> Callable:
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        settings: Settings = current_app.config["SETTINGS"]
        authorization = request.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return jsonify({"error": "invalid token"}), 401
        g.user = {"id": payload["sub"], "name": payload["name"]}
        return view(*args, **kwargs)

    return wrapper


# --- Test 1: GET /info -------------------------------------------------------


@bp.get("/info")
def get_info():
    response = jsonify({
        "id": "info-1",
        "name": "Benchmark Info",
        "count": 42,
        "ratio": 3.14159,
        "active": True,
        "tags": ["alpha", "beta", "gamma"],
        "createdAt": "2026-01-01T00:00:00Z",
        "nested": {"level": 2, "label": "nested"},
    })
    response.headers["x-response-id"] = str(uuid.uuid4())
    return response


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


@bp.post("/movies")
@auth_required
def create_movie():
    movie_in = MovieIn.model_validate(request.get_json())
    return jsonify({"id": str(uuid.uuid4()), **movie_in.model_dump(), "user": g.user}), 201


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


@bp.get("/catalog")
def catalog():
    client: SyncClient = current_app.extensions["http_client"]
    # Auth rides on the client's default headers (set once at build time).
    resp = client.get("/data").build().send()
    # bytes(): pydantic wants str/bytes/bytearray — it rejects pyreqwest's buffer.
    product = Product.model_validate_json(bytes(resp.bytes()))
    return jsonify(product.model_dump())


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


@bp.get("/users/me")
@auth_required
def users_me():
    pool: ConnectionPool = current_app.extensions["db_pool"]
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(_GET_USER_SQL, (g.user["id"],))
        row = cur.fetchone()
    if row is None:
        return jsonify({"error": "user not found"}), 404
    return jsonify({
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "address": row[3],
        "city": row[4],
        "country": row[5],
    })


def create_app() -> Flask:
    """Application factory: build settings + the shared client/pool and attach
    them to the app, then register the routes."""
    app = Flask(__name__)
    settings = Settings()
    app.config["SETTINGS"] = settings
    # Flask is sync; one pyreqwest SyncClient (HTTP) and one psycopg pool (DB),
    # attached to the app rather than held as module-level globals.
    app.extensions["http_client"] = (
        SyncClientBuilder()
        .base_url(settings.upstream_url)
        .default_headers({"authorization": f"Bearer {settings.upstream_api_key}"})
        .build()
    )
    app.extensions["db_pool"] = ConnectionPool(
        conninfo=(
            f"host={settings.db_host} port={settings.db_port} "
            f"dbname={settings.db_name} user={settings.db_user} "
            f"password={settings.db_password}"
        ),
        min_size=1,
        max_size=settings.db_pool_size,
        open=True,
    )
    app.register_blueprint(bp)
    return app


app = create_app()

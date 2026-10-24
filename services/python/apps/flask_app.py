"""Flask benchmark app — tests 1 (info), 2 (movie), 3 (proxy), 4 (/users/me).

Flask is WSGI; served under peregrine (protocol auto-detected). Uses Flask's recommended
application-factory pattern: the JWT key, the shared lothc sync client and the
psycopg pool are attached to ``app.extensions``, reached in handlers via
``current_app`` (no module-level globals).
"""

import functools
import uuid
from collections.abc import Callable
from typing import Literal

import ryjwt
from flask import Blueprint, Flask, current_app, g, jsonify, request
from lothc import SyncHTTPClient
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ValidationError
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


class Claims(BaseModel):
    sub: str
    name: str


@bp.errorhandler(ValidationError)
def validation_failed(exc: ValidationError):
    """An invalid request body is the client's fault: 422, not a 500."""
    return jsonify({"error": "invalid body", "detail": exc.errors(include_url=False)}), 422


def auth_required(view: Callable) -> Callable:
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        jwt_key: ryjwt.SecretKey = current_app.extensions["jwt_key"]
        authorization = request.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = jwt_key.decode(token, into=Claims)
        except ryjwt.InvalidTokenError:  # includes a token missing sub/name
            return jsonify({"error": "invalid token"}), 401
        g.user = {"id": claims.sub, "name": claims.name}
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
    client: SyncHTTPClient = current_app.extensions["http_client"]
    # Auth rides on the client's bearer_token (set once at build time); lothc
    # validates the body straight into the pydantic model.
    resp = client.get("data", into=Product)
    return jsonify(resp.data.model_dump())


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
    app.extensions["jwt_key"] = ryjwt.SecretKey(settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    # Flask is sync; one lothc SyncHTTPClient (HTTP) and one psycopg pool (DB),
    # attached to the app rather than held as module-level globals. The client
    # is entered once here and lives as long as the process.
    app.extensions["http_client"] = SyncHTTPClient(
        **settings.upstream_client_options
    ).__enter__()
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

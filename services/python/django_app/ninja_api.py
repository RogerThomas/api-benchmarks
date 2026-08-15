"""Django Ninja benchmark app — the same 4 tests every framework here
implements (see apps/jero_app.py for the canonical contract):

1. GET /info        - medium JSON + a custom x-response-id header.
2. POST /movies      - JWT-authenticated (Bearer header, decoded with PyJWT
                        like every other framework in this fleet — Ninja's
                        own JWT integrations are cookie-oriented, which would
                        be doing different work than everyone else).
3. GET /catalog      - proxies the authenticated `upstream` service.
4. GET /users/me     - JWT-authenticated; reads the shared `users` row.

Field names are plain snake_case (pydantic's default) rather than the
camelCase jero/FastAPI/Litestar use — a visible, intended difference, not a
missing feature (see README "Equal work, per test").
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Literal
from uuid import uuid4

import jwt
from django.http import HttpResponse, JsonResponse
from ninja import NinjaAPI, Schema
from ninja.security import HttpBearer
from pyreqwest.client import ClientBuilder
from settings import Settings

from .models import User as UserRow

_settings = Settings()

api = NinjaAPI(urls_namespace="ninja")


# --- Auth: Bearer JWT, decoded by hand like the rest of the fleet -----------


class BearerAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            payload = jwt.decode(token, _settings.jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None
        return {"id": payload["sub"], "name": payload["name"]}


bearer_auth = BearerAuth()


# --- Test 1: GET /info -------------------------------------------------------


class Nested(Schema):
    level: int
    label: str


type InfoTag = Literal["alpha", "beta", "gamma"]


class Info(Schema):
    id: str
    name: str
    count: int
    ratio: float
    active: bool
    tags: list[InfoTag]
    created_at: str
    nested: Nested


@api.get("/info", response=Info)
def info(request):
    # Returning an HttpResponse/JsonResponse bypasses Ninja's own
    # serialization (it passes such responses through unchanged), which is
    # the simplest way to attach the custom header.
    payload = Info(
        id="info-1",
        name="Benchmark Info",
        count=42,
        ratio=3.14159,
        active=True,
        tags=["alpha", "beta", "gamma"],
        created_at="2026-01-01T00:00:00Z",
        nested=Nested(level=2, label="nested"),
    )
    response = JsonResponse(payload.model_dump())
    response["x-response-id"] = str(uuid4())
    return response


# --- Test 2: POST /movies (JWT-authenticated) --------------------------------


class MovieIn(Schema):
    title: str
    year: int
    director: str
    genre: str
    rating: float


class UserOut(Schema):
    id: str
    name: str


class Movie(MovieIn):
    id: str
    user: UserOut


@api.post("/movies", response={201: Movie}, auth=bearer_auth)
def create_movie(request, payload: MovieIn):
    movie = Movie(
        id=str(uuid4()),
        user=UserOut(**request.auth),
        title=payload.title,
        year=payload.year,
        director=payload.director,
        genre=payload.genre,
        rating=payload.rating,
    )
    return 201, movie


# --- Test 3: GET /catalog (proxy an authenticated upstream) ------------------


_client_lock = asyncio.Lock()
_client = None


async def _upstream_client():
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                built = (
                    ClientBuilder()
                    .base_url(_settings.upstream_url)
                    .default_headers({"authorization": f"Bearer {_settings.upstream_api_key}"})
                    .error_for_status()
                    .connect_timeout(timedelta(seconds=1))
                    .read_timeout(timedelta(seconds=5))
                    .timeout(timedelta(seconds=10))
                    .follow_redirects(False)
                    .no_proxy()
                    .build()
                )
                await built.__aenter__()
                _client = built
    return _client


@api.get("/catalog")
async def catalog(request):
    # Pass the upstream's JSON straight through as raw bytes (same
    # `HttpResponse` bypass as /info) — no reason to decode-then-re-encode
    # a payload we're returning unmodified.
    client = await _upstream_client()
    upstream_response = await client.get("/data").build().send()
    body = await upstream_response.bytes()
    return HttpResponse(body, content_type="application/json")


# --- Test 4: GET /users/me (Postgres) ----------------------------------------


class Profile(Schema):
    id: str
    name: str
    email: str
    address: str
    city: str
    country: str


@api.get("/users/me", response=Profile, auth=bearer_auth)
async def users_me(request):
    row = await UserRow.objects.aget(id=request.auth["id"])
    return Profile(
        id=row.id,
        name=row.name,
        email=row.email,
        address=row.address,
        city=row.city,
        country=row.country,
    )

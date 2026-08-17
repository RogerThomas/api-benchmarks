# Multi-stage build: one stage per Python framework. Each stage syncs only its
# own uv dependency group into a fresh, isolated venv so deps never interfere.
# Build a single framework with:  docker build --target jero .

FROM python:3.13.14-slim-trixie AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
COPY settings.py ./settings.py
COPY serve.sh ./serve.sh

# ASGI frameworks (jero/fastapi/litestar/blacksheep) launch via serve.sh, which
# selects granian or uvicorn from $PYTHON_SERVER. Flask is WSGI (granian, pinned
# to one blocking thread for 1-core parity); Robyn ships its own server.

# --- jero --------------------------------------------------------------------
FROM base AS jero
RUN uv sync --locked --no-default-groups --group jero
COPY apps/jero_app.py ./jero_app.py
EXPOSE 8000
CMD ["sh", "serve.sh", "jero_app:app", "0.0.0.0", "8000"]

# --- fastapi -----------------------------------------------------------------
FROM base AS fastapi
RUN uv sync --locked --no-default-groups --group fastapi
COPY apps/fastapi_app.py ./fastapi_app.py
EXPOSE 8000
CMD ["sh", "serve.sh", "fastapi_app:app", "0.0.0.0", "8000"]

# --- litestar ----------------------------------------------------------------
FROM base AS litestar
RUN uv sync --locked --no-default-groups --group litestar
COPY apps/litestar_app.py ./litestar_app.py
EXPOSE 8000
CMD ["sh", "serve.sh", "litestar_app:app", "0.0.0.0", "8000"]

# --- flask (WSGI) ------------------------------------------------------------
FROM base AS flask
RUN uv sync --locked --no-default-groups --group flask
COPY apps/flask_app.py ./flask_app.py
EXPOSE 8000
CMD ["sh", "-c", "granian --interface wsgi --host 0.0.0.0 --port 8000 --workers ${WORKERS:-1} --blocking-threads 1 flask_app:app"]

# --- blacksheep --------------------------------------------------------------
FROM base AS blacksheep
RUN uv sync --locked --no-default-groups --group blacksheep
COPY apps/blacksheep_app.py ./blacksheep_app.py
EXPOSE 8000
CMD ["sh", "serve.sh", "blacksheep_app:app", "0.0.0.0", "8000"]

# --- robyn (own server) ------------------------------------------------------
FROM base AS robyn
RUN uv sync --locked --no-default-groups --group robyn
COPY apps/robyn_app.py ./robyn_app.py
EXPOSE 8000
CMD ["sh", "-c", "python robyn_app.py --processes 1 --workers ${WORKERS:-1}"]

# --- django-ninja (ASGI, via serve.sh) ---------------------------------------
FROM base AS django-ninja
RUN uv sync --locked --no-default-groups --group django-ninja
COPY manage.py ./manage.py
COPY django_app ./django_app
ENV DJANGO_SETTINGS_MODULE=django_app.settings_ninja
EXPOSE 8000
CMD ["sh", "serve.sh", "django_app.asgi:application", "0.0.0.0", "8000"]

# --- django-bolt (own server: manage.py runbolt) -----------------------------
FROM base AS django-bolt
RUN uv sync --locked --no-default-groups --group django-bolt
COPY manage.py ./manage.py
COPY django_app ./django_app
ENV DJANGO_SETTINGS_MODULE=django_app.settings_bolt
EXPOSE 8000
CMD ["sh", "-c", "python manage.py runbolt --host 0.0.0.0 --port 8000 --processes ${WORKERS:-1}"]

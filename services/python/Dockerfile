# Multi-stage build: one stage per Python framework. Each framework syncs only
# its own uv dependency group into a fresh, isolated venv (so deps never
# interfere) in a throwaway `<fw>-build` stage. The shipped image is distroless:
# glibc, the interpreter, that venv and the app -- no shell, no package
# manager, no uv.
# Build a single framework with:  docker build --target jero .
#
# The interpreter is uv's standalone CPython (python-build-standalone),
# installed under /python and copied into the runtime at the same path, so the
# venv's interpreter symlinks resolve unchanged. (Distroless's own python image
# is Debian's 3.13; fastpg needs t-strings, i.e. >= 3.14.3.)

FROM debian:trixie-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_PYTHON=3.14.9 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN uv python install 3.14.9
# A runtime copy without what no app here uses (pip, IDLE, Tcl/Tk, headers);
# the build stages keep the full install, headers included, for compiling.
RUN cp -a /python /python-runtime \
    && cd /python-runtime/cpython-3.14.9-* \
    && rm -rf include share lib/tcl* lib/tk* lib/itcl* lib/thread* lib/libtcl* lib/libtk* \
        lib/python3.14/site-packages/pip* lib/python3.14/ensurepip \
        lib/python3.14/idlelib lib/python3.14/tkinter lib/python3.14/turtledemo \
        lib/python3.14/lib-dynload/_tkinter*
WORKDIR /app
COPY pyproject.toml uv.lock ./
# uv sync --locked reads every path source in the lock, even ones this group doesn't use.
COPY vendor ./vendor

# Rust toolchain + C compiler, for the frameworks uv has to build from source.
FROM build AS build-rust
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY --from=rust:1.99-slim-trixie /usr/local/cargo /usr/local/cargo
COPY --from=rust:1.99-slim-trixie /usr/local/rustup /usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup \
    PATH="/usr/local/cargo/bin:$PATH"

# What every framework image starts from: distroless (glibc + libgcc/libstdc++),
# pinned by digest, plus the interpreter.
FROM gcr.io/distroless/cc-debian13@sha256:d74d144baa124dd9defd01d71872bb56c49d4441dba6153ccf790364f97e64b1 AS runtime
COPY --from=build /python-runtime /python
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
COPY settings.py serve.py ./
EXPOSE 8000

# ASGI frameworks (jero/fastapi/litestar/blacksheep) and Flask (WSGI) all
# launch under peregrine via serve.py. Flask runs its views inline on the
# worker (peregrine's default, no --wsgi-threads pool) for 1-core parity.
# Robyn and Django Bolt ship their own servers.
#
# The uv cache lives in a BuildKit cache mount: it speeds up rebuilds here and
# never lands in an image layer.

# --- jero --------------------------------------------------------------------
FROM build AS jero-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-default-groups --group jero

FROM runtime AS jero
COPY --from=jero-build /app/.venv /app/.venv
COPY apps/jero_app.py ./jero_app.py
CMD ["python", "serve.py", "peregrine", "jero_app:app"]

# --- fastapi -----------------------------------------------------------------
FROM build AS fastapi-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-default-groups --group fastapi

FROM runtime AS fastapi
COPY --from=fastapi-build /app/.venv /app/.venv
COPY apps/fastapi_app.py ./fastapi_app.py
CMD ["python", "serve.py", "peregrine", "fastapi_app:app"]

# --- litestar ----------------------------------------------------------------
FROM build AS litestar-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-default-groups --group litestar

FROM runtime AS litestar
COPY --from=litestar-build /app/.venv /app/.venv
COPY apps/litestar_app.py ./litestar_app.py
CMD ["python", "serve.py", "peregrine", "litestar_app:app"]

# --- flask (WSGI) ------------------------------------------------------------
FROM build AS flask-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-default-groups --group flask

FROM runtime AS flask
COPY --from=flask-build /app/.venv /app/.venv
COPY apps/flask_app.py ./flask_app.py
CMD ["python", "serve.py", "peregrine", "flask_app:app"]

# --- blacksheep --------------------------------------------------------------
FROM build AS blacksheep-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-default-groups --group blacksheep

FROM runtime AS blacksheep
COPY --from=blacksheep-build /app/.venv /app/.venv
COPY apps/blacksheep_app.py ./blacksheep_app.py
CMD ["python", "serve.py", "peregrine", "blacksheep_app:app"]

# --- robyn (own server) ------------------------------------------------------
# No cp314 wheels on PyPI: uv builds it from the release tarball (Rust + C).
FROM build-rust AS robyn-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-default-groups --group robyn

FROM runtime AS robyn
COPY --from=robyn-build /app/.venv /app/.venv
COPY apps/robyn_app.py ./robyn_app.py
CMD ["python", "serve.py", "robyn"]

# --- django-bolt (own server: manage.py runbolt) -----------------------------
FROM build AS django-bolt-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-default-groups --group django-bolt

FROM runtime AS django-bolt
COPY --from=django-bolt-build /app/.venv /app/.venv
COPY manage.py ./manage.py
COPY django_app ./django_app
ENV DJANGO_SETTINGS_MODULE=django_app.settings
CMD ["python", "serve.py", "django-bolt"]

# Build context is the repo root (see compose.base.yml's `runner.build`), not
# this directory — loadtest/pyproject.toml's taglydb path dependency points at
# ../vendor/taglydb-client, so the image mirrors that same repo-root-relative
# layout (/app/vendor + /app/loadtest) rather than flattening loadtest/ into
# /app.
FROM grafana/k6:latest
USER root
# python3 drives the orchestration; docker-cli is for `docker stats`/`docker
# ps` on the framework's own container (read-only socket mount, see
# compose.base.yml).
RUN apk add --no-cache python3 docker-cli
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY vendor ./vendor
WORKDIR /app/loadtest
ENV UV_PROJECT_ENVIRONMENT=/app/loadtest/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/loadtest/.venv/bin:$PATH"
COPY loadtest/pyproject.toml loadtest/uv.lock ./
RUN uv sync --locked
COPY loadtest/run.py ./run.py
COPY loadtest/scenarios /scenarios
COPY loadtest/lib /lib
ENTRYPOINT ["uv", "run", "yeet", "./run.py"]

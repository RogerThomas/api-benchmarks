# Build context is the repo root (see compose.base.yml's `runner.build`), not
# this directory — loadtest/pyproject.toml's taglydb path dependency points at
# ../vendor/taglydb-client, so the build mirrors that same repo-root-relative
# layout (/app/vendor + /app/loadtest).
FROM alpine:3.24 AS build
RUN apk add --no-cache python3
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
WORKDIR /app
COPY vendor ./vendor
WORKDIR /app/loadtest
ENV UV_PROJECT_ENVIRONMENT=/app/loadtest/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY loadtest/pyproject.toml loadtest/uv.lock ./
# --no-editable: the venv must not point back at /app/vendor, which only
# exists in this build stage. The uv cache stays in a BuildKit cache mount.
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-editable

# Runtime: python3 runs the orchestration; docker-cli is for `docker stats`/
# `docker ps` on the framework's own container (read-only socket mount, see
# compose.base.yml); wrk and oha are the two load generators (LOADGEN).
FROM alpine:3.24
RUN apk add --no-cache python3 docker-cli wrk
# oha's release binary is static, so it runs on Alpine as-is. arm64 only, like
# the rest of this fleet (Apple Silicon locally, Graviton on EC2).
ADD --chmod=755 \
    --checksum=sha256:99a790eb8c3e0feaca974bd6b32f0f8d4426a0c5b289f39e833e5b2c7529cd39 \
    https://github.com/hatoo/oha/releases/download/v1.16.0/oha-linux-arm64 /usr/local/bin/oha
WORKDIR /app/loadtest
ENV PATH="/app/loadtest/.venv/bin:$PATH"
COPY --from=build /app/loadtest/.venv /app/loadtest/.venv
COPY loadtest/run.py ./run.py
ENTRYPOINT ["yeet", "./run.py"]

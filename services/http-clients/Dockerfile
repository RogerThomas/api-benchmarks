# Outbound HTTP client shootout. Same base image / uv setup as the framework
# stages so the interpreter is identical (Python 3.13.14). Runs once against the
# upstream, prints the tables, then exits.
FROM python:3.13.14-slim-trixie AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml ./
RUN uv sync
COPY bench.py ./bench.py

# DURATION (s per client) / CONCURRENCY are read at run time; UPSTREAM_API_KEY
# comes from the env (bench.py's --upstream-api-key opt binds it). Positional arg
# is the upstream base URL on the bench network.
CMD ["sh", "-c", "yeet bench.py http://upstream:8000 -d ${DURATION:-10} -c ${CONCURRENCY:-64}"]

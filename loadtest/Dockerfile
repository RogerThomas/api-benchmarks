FROM grafana/k6:latest
USER root
# python3 + sqlite (stdlib's sqlite3 module needs the shared lib, which
# peewee's SqliteDatabase sits on top of) drive the orchestration; docker-cli
# is for `docker stats`/`docker ps` on the framework's own container
# (read-only socket mount, see compose.base.yml).
RUN apk add --no-cache python3 sqlite docker-cli
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN uv sync --locked
COPY run.py ./run.py
COPY scenarios /scenarios
COPY lib /lib
ENTRYPOINT ["uv", "run", "yeet", "./run.py"]

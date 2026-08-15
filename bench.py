#!yeet
"""Benchmark orchestrator.

Loops over FRAMEWORKS one at a time: for each, brings up compose.base.yml
(postgres + upstream + runner) plus that framework's own compose.<fw>.yml,
lets the runner drive every test, then tears the pair back down before
moving to the next framework — so no two frameworks ever share a core or
contend for host resources (see README "Fairness").

Every framework in one invocation shares a single RUN_ID (the kickoff
timestamp); loadtest/run.py tags every row it writes into results/bench.db
with it, which is what ties a run together across frameworks. At the end,
this hands off to export_results.py to print the comparison tables.

    uv run yeet ./bench.py --frameworks "jero fastapi"
    uv run yeet ./bench.py --duration 30s --vus 200
    # backfill django-bolt into a past run:
    uv run yeet ./bench.py --frameworks django-bolt --run-id 20260814T065228
"""

import os
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, get_args

from plumbum import local
from pydantic_settings import BaseSettings, SettingsConfigDict
from yeetr import Opt


class ResultsBackendSettings(BaseSettings):
    """Read from .env, then forwarded into the runner container's env (see
    compose.base.yml) — this is how loadtest/run.py and export_results.py end
    up pointed at the same backend: Postgres (e.g. Neon) if PG_HOST is set,
    else SQLite at SQLITE_PATH, else the local default."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    pg_host: str | None = None
    pg_port: int = 5432
    pg_db: str | None = None
    pg_user: str | None = None
    pg_password: str | None = None
    pg_sslmode: str = "require"
    pg_channel_binding: str = "require"
    sqlite_path: str | None = None


type PythonServer = Literal["granian", "uvicorn"]
type Framework = Literal[
    "jero",
    "fastapi",
    "litestar",
    "flask",
    "blacksheep",
    "robyn",
    "gin",
    "elysia",
    "spring-boot",
    "django-ninja",
    "django-bolt",
]


def main(
    *,
    frameworks: Annotated[str, Opt(help="Space-separated framework names")] = " ".join(
        get_args(Framework.__value__)
    ),
    tests: Annotated[str, Opt(help="Space-separated test names")] = "test1 test2 test3 test4",
    duration: Annotated[str, Opt(help="k6 duration per attempt")] = "10s",
    vus: Annotated[int, Opt(help="k6 virtual users")] = 100,
    runs: Annotated[int, Opt(help="Attempts per (framework, test); best wins")] = 3,
    workers: Annotated[int, Opt(help="Server workers/processes per framework")] = 1,
    python_server: Annotated[PythonServer, Opt(help="ASGI server")] = "granian",
    run_id: Annotated[
        str,
        Opt(help="Reuse an existing RUN_ID (e.g. to backfill a framework into a past run)"),
    ] = "",
) -> None:
    fw_list = frameworks.split()
    unknown = [fw for fw in fw_list if fw not in get_args(Framework.__value__)]
    if unknown:
        print(f"unknown framework(s): {' '.join(unknown)}", file=sys.stderr)
        print(f"choose from: {' '.join(get_args(Framework.__value__))}", file=sys.stderr)
        raise SystemExit(1)
    if not fw_list:
        print("--frameworks is empty — nothing to bench.", file=sys.stderr)
        raise SystemExit(1)

    now = datetime.now(UTC)
    run_id = run_id or now.strftime("%Y%m%dT%H%M%S")
    backend = ResultsBackendSettings()
    env = {
        **os.environ,
        "RUN_ID": run_id,
        # Real timestamp for Run.created_at (a DateTimeField) — separate from
        # RUN_ID, which is just a readable/typeable string identifier. Only
        # used the first time this run_id is created; ignored on backfill
        # into an existing run (see Run.get_or_create in loadtest/run.py).
        "RUN_CREATED_AT": now.isoformat(),
        "TESTS": tests,
        "DURATION": duration,
        "VUS": str(vus),
        "RUNS": str(runs),
        "WORKERS": str(workers),
        "PYTHON_SERVER": python_server,
        "BENCH_HOSTNAME": socket.gethostname(),
        "PG_HOST": backend.pg_host or "",
        "PG_PORT": str(backend.pg_port),
        "PG_DB": backend.pg_db or "",
        "PG_USER": backend.pg_user or "",
        "PG_PASSWORD": backend.pg_password or "",
        "PG_SSLMODE": backend.pg_sslmode,
        "PG_CHANNEL_BINDING": backend.pg_channel_binding,
        "SQLITE_PATH": backend.sqlite_path or "",
    }

    print(f"==> run {run_id} · frameworks: {' '.join(fw_list)}")
    root = Path(__file__).resolve().parent
    base_file = root / "compose.base.yml"
    failures = []
    for fw in fw_list:
        fw_file = root / f"compose.{fw}.yml"
        if not fw_file.exists():
            print(f"==> skipping {fw}: no {fw_file.name}", file=sys.stderr)
            failures.append(fw)
            continue

        print(f"\n==> {fw}: base + {fw}")
        compose = local["docker"]["compose", "-f", str(base_file), "-f", str(fw_file)].with_env(
            **env
        )
        try:
            up_rc, _, _ = compose[
                "up", "--build", "--abort-on-container-exit", "--exit-code-from", "runner"
            ].run(retcode=None, stdout=None, stderr=None)
            if up_rc != 0:
                print(f"==> {fw}: FAILED (exit {up_rc})", file=sys.stderr)
                failures.append(fw)
        finally:
            compose["down", "-v"].run(retcode=None)

    print(f"\n==> exporting results for run {run_id}")
    local["uv"]["run", "yeet", str(root / "export_results.py"), run_id].run(
        retcode=None, stdout=None, stderr=None, cwd=str(root)
    )

    if failures:
        print(f"\n==> run {run_id} had failures: {' '.join(failures)}", file=sys.stderr)
        raise SystemExit(1)

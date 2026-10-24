#!yeet
"""Benchmark orchestrator.

Loops over FRAMEWORKS one at a time: for each, brings up compose.base.yml
(postgres + upstream + runner) plus that framework's own compose.<fw>.yml,
lets the runner drive every test, then tears the pair back down before
moving to the next framework — so no two frameworks ever share a core or
contend for host resources (see README "Fairness").

Every framework in one invocation shares a single RUN_ID (the kickoff
timestamp); loadtest/run.py tags every item it writes into TaglyDB with
it, which is what ties a run together across frameworks. At the end,
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
    up pointed at the same TaglyDB principal. Only the API key is
    secret/configurable; the base URL is fixed and inlined at every call site."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    taglydb_api_key: str


type LoadGen = Literal["oha", "wrk"]
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
    "django-bolt",
    # Temporary: the peregrine-vs-granian A/B (compose.<fw>-granian.yml).
    "jero-granian",
    "fastapi-granian",
    "flask-granian",
]


def build_images(base_file: Path, fw_files: list[Path], env: dict[str, str]) -> None:
    """Build every image this run needs in one go, before benching anything.

    Compose hands the merged project to bake, which builds all targets in
    parallel (sharing the Python `base` stage) instead of one per framework
    just ahead of its bench — and a broken image aborts the run here rather
    than after every framework ahead of it has already been benched.
    """
    print(f"\n==> building images for {len(fw_files)} framework(s)")
    args = ["compose", "-f", str(base_file)]
    for f in fw_files:
        args += ["-f", str(f)]
    rc, _, _ = (
        local["docker"][(*args, "build")]
        .with_env(**env)
        .run(retcode=None, stdout=None, stderr=None)
    )
    if rc != 0:
        print(f"==> image build FAILED (exit {rc}) — nothing benched", file=sys.stderr)
        raise SystemExit(1)


def main(
    *,
    frameworks: Annotated[str, Opt(help="Space-separated framework names")] = " ".join(
        get_args(Framework.__value__)
    ),
    tests: Annotated[str, Opt(help="Space-separated test names")] = "test1 test2 test3 test4",
    duration: Annotated[str, Opt(help="Duration per attempt")] = "10s",
    vus: Annotated[int, Opt(help="Concurrent connections (closed loop)")] = 100,
    runs: Annotated[int, Opt(help="Attempts per (framework, test); best wins")] = 3,
    workers: Annotated[int, Opt(help="Server workers/processes per framework")] = 1,
    loadgen: Annotated[LoadGen, Opt(help="Load generator")] = "wrk",
    run_id: Annotated[
        str,
        Opt(help="Reuse an existing RUN_ID (e.g. to backfill a framework into a past run)"),
    ] = "",
    ec2_ami_id: Annotated[
        str, Opt(help="EC2 AMI id this ran on (informational, set by ec2_launch.py)")
    ] = "",
    ec2_instance_type: Annotated[
        str, Opt(help="EC2 instance type this ran on (informational)")
    ] = "",
    aws_region: Annotated[str, Opt(help="AWS region this ran in (informational)")] = "",
    images: Annotated[
        str, Opt(help="Exact ECR image tags this ran on (informational, set by ec2_launch.py)")
    ] = "",
    no_build: Annotated[
        bool, Opt(help="Use the images already present (e.g. pulled from ECR) instead of building")
    ] = False,
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
    backend = ResultsBackendSettings()  # pyright: ignore[reportCallIssue] -- fields come from .env, not the constructor
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
        "LOADGEN": loadgen,
        "BENCH_HOSTNAME": socket.gethostname(),
        "EC2_AMI_ID": ec2_ami_id,
        "EC2_INSTANCE_TYPE": ec2_instance_type,
        "AWS_REGION": aws_region,
        "IMAGES": images,
        "TAGLYDB_API_KEY": backend.taglydb_api_key,
    }

    print(f"==> run {run_id} · {len(fw_list)} framework(s): {' '.join(fw_list)}")
    root = Path(__file__).resolve().parent
    base_file = root / "compose.base.yml"
    fw_files = [root / f"compose.{fw}.yml" for fw in fw_list]
    if not no_build:
        build_images(base_file, [f for f in fw_files if f.exists()], env)

    failures = []
    for fw, fw_file in zip(fw_list, fw_files, strict=True):
        if not fw_file.exists():
            print(f"==> skipping {fw}: no {fw_file.name}", file=sys.stderr)
            failures.append(fw)
            continue

        print(f"\n==> {fw}: base + {fw_file.name}")
        compose = local["docker"]["compose", "-f", str(base_file), "-f", str(fw_file)].with_env(
            **env
        )
        try:
            up_rc, _, _ = compose[
                "up", "--no-build", "--abort-on-container-exit", "--exit-code-from", "runner"
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

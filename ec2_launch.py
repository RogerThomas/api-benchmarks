#!yeet
"""Launch a fire-and-forget EC2 benchmark run: a c9g.2xlarge in eu-central-1,
built from the pre-warmed AMI (see the ec2-fire-and-forget-setup memory),
runs `task bench`, uploads results to Neon and its log to S3, then
self-terminates. No SSH babysitting needed -- ./ec2_tail_logs.py watches it
live, ./export_results.py reads the results back out once it's done.

    uv run yeet ./ec2_launch.py
    uv run yeet ./ec2_launch.py --duration 60s --vus 128 --frameworks "jero fastapi"
    # backfill django-bolt into a run an earlier launch already started:
    uv run yeet ./ec2_launch.py --frameworks django-bolt --run-id 20260815T070512
"""

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from plumbum import FG, local
from pydantic_settings import BaseSettings, SettingsConfigDict


class EC2Settings(BaseSettings):
    """Fire-and-forget EC2 runner infra -- standing resources, not secrets;
    overridable via .env if the account/region/AMI ever changes. PG_*/
    upstream_api_key ARE secrets, read from .env same as everywhere else."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "eu-central-1"
    ec2_ami_id: str = "ami-0f7d895aa37851cb2"
    ec2_instance_type: str = "c9g.2xlarge"
    ec2_key_name: str = "jero-benchmarks-ec2"
    ec2_security_group_id: str = "sg-03642d1f5a22358d3"
    ec2_subnet_id: str = "subnet-07e2c8dbae2268429"
    ec2_iam_instance_profile: str = "jero-benchmarks-ec2-profile"
    ec2_s3_bucket: str = "jero-benchmarks-751884348953"
    ec2_s3_bucket_region: str = "eu-west-2"

    pg_host: str | None = None
    pg_db: str | None = None
    pg_user: str | None = None
    pg_password: str | None = None
    upstream_api_key: str = "upk_bench_9f8e7d6c5b4a32100fedcba987654321"


def _sync_code(settings: EC2Settings) -> None:
    """Tar up the current working tree (not `git archive` -- uncommitted
    edits must ship too) and push it to S3, so every launch runs whatever's
    on disk right now instead of a stale, manually-uploaded tarball."""
    repo_root = Path(__file__).resolve().parent
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tarball_file:
        tarball_path = Path(tarball_file.name)
    try:
        _ = (
            local["tar"][
                "czf",
                str(tarball_path),
                "--exclude=.git",
                "--exclude=.env",
                "--exclude=.venv",
                "--exclude=__pycache__",
                "--exclude=target",
                "--exclude=node_modules",
                "--exclude=results",
                "-C",
                str(repo_root.parent),
                repo_root.name,
            ]
            & FG
        )
        _ = (
            local["aws"][
                "s3",
                "cp",
                str(tarball_path),
                f"s3://{settings.ec2_s3_bucket}/code/jero-benchmarks.tar.gz",
                "--region",
                settings.ec2_s3_bucket_region,
            ]
            & FG
        )
    finally:
        tarball_path.unlink(missing_ok=True)


def _render_user_data(settings: EC2Settings, *, bench_args: str) -> str:
    template_path = Path(__file__).resolve().parent / "ec2" / "user-data.sh.template"
    template = template_path.read_text()
    return (
        template
        .replace("__S3_BUCKET__", settings.ec2_s3_bucket)
        .replace("__PG_USER__", settings.pg_user or "")
        .replace("__PG_PASSWORD__", settings.pg_password or "")
        .replace("__PG_HOST__", settings.pg_host or "")
        .replace("__PG_DB__", settings.pg_db or "")
        .replace("__UPSTREAM_API_KEY__", settings.upstream_api_key)
        .replace("__BENCH_ARGS__", bench_args)
    )


def main(*, duration: str = "60s", vus: int = 128, frameworks: str = "", run_id: str = "") -> None:
    settings = EC2Settings()
    if not (settings.pg_host and settings.pg_user and settings.pg_password and settings.pg_db):
        print(
            "PG_HOST/PG_USER/PG_PASSWORD/PG_DB must all be set in .env -- "
            "an EC2 run needs a shared results backend, not local SQLite.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    bench_args = f"--duration {duration} --vus {vus} --run-id {run_id}"
    if frameworks:
        bench_args += f' --frameworks "{frameworks}"'

    print(f"==> syncing code to s3://{settings.ec2_s3_bucket}/code/jero-benchmarks.tar.gz")
    _sync_code(settings)

    user_data = _render_user_data(settings, bench_args=bench_args)
    with tempfile.NamedTemporaryFile(
        "w", prefix="jero-user-data-", suffix=".sh", delete=False
    ) as user_data_file:
        user_data_file.write(user_data)
    user_data_path = Path(user_data_file.name)

    try:
        instance_id = local["aws"][
            "ec2",
            "run-instances",
            "--region",
            settings.aws_region,
            "--image-id",
            settings.ec2_ami_id,
            "--instance-type",
            settings.ec2_instance_type,
            "--key-name",
            settings.ec2_key_name,
            "--security-group-ids",
            settings.ec2_security_group_id,
            "--subnet-id",
            settings.ec2_subnet_id,
            "--iam-instance-profile",
            f"Name={settings.ec2_iam_instance_profile}",
            "--instance-initiated-shutdown-behavior",
            "terminate",
            "--user-data",
            f"file://{user_data_path}",
            "--tag-specifications",
            f"ResourceType=instance,Tags=[{{Key=Name,Value={run_id}}}]",
            "--query",
            "Instances[0].InstanceId",
            "--output",
            "text",
        ]().strip()
    finally:
        user_data_path.unlink(missing_ok=True)

    print(f"launched {instance_id} (run {run_id}) in {settings.aws_region} -- {bench_args}")
    print(f"uv run yeet ./ec2_tail_logs.py {instance_id}")

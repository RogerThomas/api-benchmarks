#!yeet
"""Launch a fire-and-forget EC2 benchmark run: a c9g.2xlarge in eu-central-1,
built from the pre-warmed AMI (see the ec2-fire-and-forget-setup memory),
runs bench.py, uploads results to TaglyDB and its log to S3, then
self-terminates. No SSH babysitting needed -- ./ec2_tail_logs.py watches it
live, ./export_results.py reads the results back out once it's done.

Images are built here and pushed to ECR (one repo), so instances pull
ready-made images instead of compiling. Every image is versioned on its own,
CalVer-style: `<service>-YYYY.MM.DD.NN`, e.g. `jero-2026.10.23.01` (NN counts
up within the UTC day). A build only pushes a new version of an image that
actually changed -- edit jero and only jero gets a new tag. Tags are immutable,
and every result records the exact image tags it ran on.

The code comes from GitHub, not from this machine: each instance downloads the
tarball of the current commit, so the working tree must be clean (the images
are built from it) and HEAD pushed. Every result records that commit.

    uv run yeet ./ec2_launch.py                       # everything, one instance
    uv run yeet ./ec2_launch.py --parallel            # one instance per framework
    uv run yeet ./ec2_launch.py --parallel --max-instances 4  # ...at most 4 at once
    uv run yeet ./ec2_launch.py --frameworks jero     # rebuild jero if changed, bench it
    uv run yeet ./ec2_launch.py --frameworks jero --tag 2026.10.23.01  # exact image, no build
    uv run yeet ./ec2_launch.py:push --frameworks jero  # build + version changed images, no launch
    # backfill django-bolt into a run an earlier launch already started:
    uv run yeet ./ec2_launch.py --frameworks django-bolt --run-id 20260815T070512
"""

import json
import re
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

from plumbum import FG, ProcessExecutionError, local
from pydantic_settings import BaseSettings, SettingsConfigDict

from bench import Framework


class EC2Settings(BaseSettings):
    """Fire-and-forget EC2 runner infra -- standing resources, not secrets;
    overridable via .env if the account/region/AMI ever changes.
    taglydb_api_key/upstream_api_key ARE secrets, read from .env same as
    everywhere else."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "eu-central-1"
    ec2_ami_id: str = "ami-0f7d895aa37851cb2"
    ec2_instance_type: str = "c9g.2xlarge"
    ec2_key_name: str = "jero-benchmarks-ec2"
    ec2_security_group_id: str = "sg-03642d1f5a22358d3"
    ec2_subnet_id: str = "subnet-07e2c8dbae2268429"
    ec2_iam_instance_profile: str = "jero-benchmarks-ec2-profile"
    ec2_s3_bucket: str = "jero-benchmarks-751884348953"  # logs only
    ec2_ecr_repo: str = "751884348953.dkr.ecr.eu-central-1.amazonaws.com/jero-benchmarks"

    github_repo: str = "RogerThomas/api-benchmarks"  # public: no token needed

    taglydb_api_key: str | None = None
    upstream_api_key: str = "upk_bench_9f8e7d6c5b4a32100fedcba987654321"


def _pushed_commit() -> str:
    """HEAD's sha, after checking instances can fetch exactly the code the
    images are about to be built from: no uncommitted changes, HEAD pushed."""
    git = local["git"]["-C", str(Path(__file__).resolve().parent)]
    if git["status", "--porcelain"]().strip():
        print("uncommitted changes -- commit and push first, instances run HEAD", file=sys.stderr)
        raise SystemExit(1)
    _ = git["fetch", "-q", "origin"]()
    if not git["branch", "-r", "--contains", "HEAD"]().strip():
        print("HEAD isn't pushed -- push first, instances download it from GitHub", file=sys.stderr)
        raise SystemExit(1)
    return git["rev-parse", "HEAD"]().strip()


# Harness images every instance needs alongside its framework(s).
_SHARED_IMAGES = ["postgres", "upstream", "runner"]
_TAG_RE = re.compile(r"(?P<service>.+)-(?P<version>\d{4}\.\d{2}\.\d{2}\.\d{2})")


def _local_image(service: str) -> str:
    return "postgres:18-alpine" if service == "postgres" else f"jero-benchmarks-{service}"


def _ecr_versions(settings: EC2Settings) -> dict[str, dict[str, str]]:
    """service -> {version: manifest digest}, for every versioned tag in ECR."""
    out = local["aws"][
        "ecr",
        "describe-images",
        "--region",
        settings.aws_region,
        "--repository-name",
        settings.ec2_ecr_repo.split("/", 1)[1],
        "--query",
        "imageDetails[].{tags: imageTags, digest: imageDigest}",
        "--output",
        "json",
    ]()
    versions: dict[str, dict[str, str]] = {}
    for image in json.loads(out):
        for tag in image["tags"] or []:
            if m := _TAG_RE.fullmatch(tag):
                versions.setdefault(m["service"], {})[m["version"]] = image["digest"]
    return versions


def _image_digest(settings: EC2Settings, tag: str) -> str:
    """Digest of the arm64 image manifest behind `tag`. Not the tag's own digest:
    BuildKit wraps each build in an index with a fresh provenance attestation,
    so the index digest changes on every rebuild even when the image doesn't."""
    out = local["aws"][
        "ecr",
        "batch-get-image",
        "--region",
        settings.aws_region,
        "--repository-name",
        settings.ec2_ecr_repo.split("/", 1)[1],
        "--image-ids",
        f"imageTag={tag}",
        "--query",
        "images[0].[imageId.imageDigest, imageManifest]",
        "--output",
        "json",
    ]()
    digest, manifest = json.loads(out)
    for entry in json.loads(manifest).get("manifests", []):
        if entry.get("platform", {}).get("architecture") == "arm64":
            return entry["digest"]
    return digest  # a plain single-platform manifest


def _latest(versions: dict[str, dict[str, str]], service: str) -> str | None:
    known = versions.get(service, {})
    return max(known, key=lambda v: tuple(map(int, v.split(".")))) if known else None


def _next_version(versions: dict[str, dict[str, str]], service: str) -> str:
    today = datetime.now(UTC).strftime("%Y.%m.%d")
    taken = [int(v.rsplit(".", 1)[1]) for v in versions.get(service, {}) if v.startswith(today)]
    return f"{today}.{max(taken, default=0) + 1:02d}"


def _push_changed(settings: EC2Settings, frameworks: list[str]) -> dict[str, str]:
    """Build the images these frameworks need, then push a new version of each
    one that differs from its latest version in ECR; return service -> version
    for everything the run will use (new or reused)."""
    repo_root = Path(__file__).resolve().parent
    compose_args = ["compose", "-f", "compose.base.yml"]
    for fw in frameworks:
        compose_args += ["-f", f"compose.{fw}.yml"]
    docker = local["docker"]
    with local.cwd(repo_root), local.env(RUN_ID="build"):
        _ = docker[(*compose_args, "build")] & FG
    _ = docker["pull", "-q", "postgres:18-alpine"]()
    password = local["aws"]["ecr", "get-login-password", "--region", settings.aws_region]()
    registry = settings.ec2_ecr_repo.split("/")[0]
    _ = (docker["login", "--username", "AWS", "--password-stdin", registry] << password)()

    versions = _ecr_versions(settings)
    chosen: dict[str, str] = {}
    for service in [*_SHARED_IMAGES, *frameworks]:
        local_digest = docker[
            "image",
            "inspect",
            "--platform",
            "linux/arm64",
            "--format",
            "{{.Descriptor.digest}}",
            _local_image(service),
        ]().strip()
        latest = _latest(versions, service)
        if latest and _image_digest(settings, f"{service}-{latest}") == local_digest:
            chosen[service] = latest
            print(f"  {service}-{latest} (unchanged)")
            continue
        version = _next_version(versions, service)
        ref = f"{settings.ec2_ecr_repo}:{service}-{version}"
        _ = docker["tag", _local_image(service), ref]()
        print(f"  pushing {service}-{version}")
        _ = docker["push", "-q", ref]()
        chosen[service] = version
    return chosen


def _existing(settings: EC2Settings, frameworks: list[str], tag: str) -> dict[str, str]:
    """No build: `tag` for every framework, the latest version of each shared image."""
    versions = _ecr_versions(settings)
    chosen = {}
    for service in _SHARED_IMAGES:
        if (latest := _latest(versions, service)) is None:
            print(f"no {service} image in ECR yet -- run once without --tag", file=sys.stderr)
            raise SystemExit(1)
        chosen[service] = latest
    for fw in frameworks:
        if tag not in versions.get(fw, {}):
            known = ", ".join(sorted(versions.get(fw, {}))) or "none"
            print(f"no {fw}-{tag} in ECR (known {fw} versions: {known})", file=sys.stderr)
            raise SystemExit(1)
        chosen[fw] = tag
    return chosen


def _render_user_data(
    settings: EC2Settings, *, commit: str, bench_args: str, images: dict[str, str]
) -> str:
    template_path = Path(__file__).resolve().parent / "ec2" / "user-data.sh.template"
    template = template_path.read_text()
    return (
        template
        .replace("__S3_BUCKET__", settings.ec2_s3_bucket)
        .replace("__GITHUB_REPO__", settings.github_repo)
        .replace("__COMMIT__", commit)
        .replace("__TAGLYDB_API_KEY__", settings.taglydb_api_key or "")
        .replace("__UPSTREAM_API_KEY__", settings.upstream_api_key)
        .replace("__BENCH_ARGS__", bench_args)
        .replace("__ECR_REPO__", settings.ec2_ecr_repo)
        .replace("__AWS_REGION__", settings.aws_region)
        .replace("__IMAGES__", " ".join(f"{svc}={ver}" for svc, ver in images.items()))
    )


def _launch(
    settings: EC2Settings,
    *,
    run_id: str,
    commit: str,
    bench_args: str,
    frameworks: list[str],
    versions: dict[str, str],
) -> str:
    """Start one spot instance that benches `frameworks`; return its instance id."""
    images = {svc: versions[svc] for svc in [*_SHARED_IMAGES, *frameworks]}
    tags = " ".join(f"{svc}-{ver}" for svc, ver in images.items())
    user_data = _render_user_data(
        settings,
        commit=commit,
        bench_args=f'{bench_args} --frameworks "{" ".join(frameworks)}" --images "{tags}"',
        images=images,
    )
    with tempfile.NamedTemporaryFile(
        "w", prefix="jero-user-data-", suffix=".sh", delete=False
    ) as user_data_file:
        user_data_file.write(user_data)
    user_data_path = Path(user_data_file.name)

    run_instances_args = [
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
        f"ResourceType=instance,Tags=[{{Key=Name,Value={run_id}-{'-'.join(frameworks)[:200]}}}]",
        "--query",
        "Instances[0].InstanceId",
        "--output",
        "text",
        # Always spot. One-time (not persistent) -- matches the fire-and-forget
        # lifecycle: no auto-relaunch if AWS reclaims the capacity mid-run.
        # Capped at the on-demand price implicitly (no MaxPrice override).
        "--instance-market-options",
        (
            '{"MarketType":"spot","SpotOptions":{"SpotInstanceType":"one-time",'
            '"InstanceInterruptionBehavior":"terminate"}}'
        ),
    ]
    try:
        return local["aws"][run_instances_args]().strip()
    finally:
        user_data_path.unlink(missing_ok=True)


def push(*, frameworks: str = "") -> None:
    """Build and push a new version of every changed image; launch nothing."""
    fw_list = frameworks.split() or list(get_args(Framework.__value__))
    versions = _push_changed(EC2Settings(), fw_list)
    print(" ".join(f"{svc}-{ver}" for svc, ver in versions.items()))


def _running(settings: EC2Settings, run_id: str) -> int:
    """How many of this run's instances still hold spot capacity. Counted by the
    run-id name tag, so a second launcher for the same run sees the first one's
    instances too; "shutting-down" still counts against the spot quota."""
    out = local["aws"][
        "ec2",
        "describe-instances",
        "--region",
        settings.aws_region,
        "--filters",
        f"Name=tag:Name,Values={run_id}-*",
        "Name=instance-state-name,Values=pending,running,shutting-down,stopping",
        "--query",
        "length(Reservations[].Instances[])",
        "--output",
        "text",
    ]()
    return int(out.strip())


def _launch_when_free(
    settings: EC2Settings,
    *,
    run_id: str,
    commit: str,
    bench_args: str,
    frameworks: list[str],
    versions: dict[str, str],
    max_instances: int,
) -> str | None:
    """Launch once fewer than `max_instances` of this run hold capacity (no cap
    if 0), retrying while AWS reports the spot quota full. Returns the instance
    id, or None if the launch failed for any other reason."""
    while True:
        while max_instances and _running(settings, run_id) >= max_instances:
            time.sleep(30)
        try:
            return _launch(
                settings,
                run_id=run_id,
                commit=commit,
                bench_args=bench_args,
                frameworks=frameworks,
                versions=versions,
            )
        except ProcessExecutionError as exc:
            if max_instances and "MaxSpotInstanceCountExceeded" in exc.stderr:
                time.sleep(30)  # capacity frees up as an instance finishes terminating
                continue
            print(
                f"  NOT launched {' '.join(frameworks)}: {exc.stderr.strip()[-200:]}",
                file=sys.stderr,
            )
            return None


def main(
    *,
    duration: str = "60s",
    vus: int = 128,
    runs: int = 3,
    frameworks: str = "",
    tests: str = "",
    run_id: str = "",
    loadgen: str = "wrk",
    parallel: bool = False,
    max_instances: int = 0,
    tag: str = "",
) -> None:
    """Launch the bench on EC2 spot -- one instance for everything, or with
    --parallel one instance per framework (same run id, so one report).
    --max-instances N keeps at most N running, launching the next as one
    finishes (each instance self-terminates when its bench is done). With
    --tag, run that exact image version of each framework instead of building."""
    settings = EC2Settings()
    if not settings.taglydb_api_key:
        print(
            "TAGLYDB_API_KEY must be set in .env -- an EC2 run needs a shared results backend.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    commit = _pushed_commit()
    fw_list = frameworks.split() or list(get_args(Framework.__value__))
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    bench_args = (
        f"--duration {duration} --vus {vus} --runs {runs} --run-id {run_id} --commit {commit} "
        f"--loadgen {loadgen} "
        f"--ec2-ami-id {settings.ec2_ami_id} --ec2-instance-type {settings.ec2_instance_type} "
        f"--aws-region {settings.aws_region}"
    )
    if tests:
        bench_args += f' --tests "{tests}"'

    if tag:
        versions = _existing(settings, fw_list, tag)
    else:
        print(f"==> building, pushing changed images to {settings.ec2_ecr_repo}")
        versions = _push_changed(settings, fw_list)
    print(f"==> instances run commit {commit[:12]} from github.com/{settings.github_repo}")

    groups = [[fw] for fw in fw_list] if parallel else [fw_list]
    not_launched: list[str] = []
    for group in groups:
        instance_id = _launch_when_free(
            settings,
            run_id=run_id,
            commit=commit,
            bench_args=bench_args,
            frameworks=group,
            versions=versions,
            max_instances=max_instances,
        )
        if instance_id is None:
            not_launched += group
            continue
        tags = " ".join(f"{fw}-{versions[fw]}" for fw in group)
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        print(f"[{stamp}] launched {instance_id} (spot, run {run_id}): {tags}", flush=True)
        print(f"  uv run yeet ./ec2_tail_logs.py {instance_id}")
    if not_launched:
        print(
            f"\nrelaunch the rest later: uv run yeet ./ec2_launch.py --parallel "
            f'--run-id {run_id} --frameworks "{" ".join(not_launched)}" ...',
            file=sys.stderr,
        )

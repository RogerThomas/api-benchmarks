#!yeet
"""Launch a fire-and-forget EC2 benchmark run: a c9g.2xlarge in eu-central-1,
built from the pre-warmed AMI (see the ec2-fire-and-forget-setup memory),
runs bench.py, uploads results to TaglyDB and its log to S3, then
self-terminates. No SSH babysitting needed -- ./ec2_tail_logs.py watches it
live, ./export_results.py reads the results back out once it's done.

Images are built here and pushed to ECR (one repo), so instances pull
ready-made images instead of compiling. Every image is versioned on its own,
CalVer-style: `<service>-YYYY.MM.DD.NN`, e.g. `jero-2026.10.23.01` (NN counts
up within the UTC day). Each version also carries a source tag,
`<service>-src-<hash>`, hashing the git files its image is built from: a
service whose files already have a version in ECR isn't rebuilt at all -- edit
jero and only jero gets a new version. That's deterministic, so a fresh CI
runner reuses images exactly like this laptop does. Tags are immutable, and
every result records the exact image tags it ran on.

The code comes from GitHub, not from this machine: each instance downloads the
tarball of the current commit, so the working tree must be clean (the images
are built from it) and HEAD pushed. Every result records that commit.

    uv run yeet ./ec2_launch.py                       # everything, one instance
    uv run yeet ./ec2_launch.py --parallel            # one instance per framework
    uv run yeet ./ec2_launch.py --parallel --max-instances 4  # ...at most 4 at once
    uv run yeet ./ec2_launch.py --frameworks jero     # rebuild jero if changed, bench it
    uv run yeet ./ec2_launch.py --frameworks jero --tag 2026.10.23.01  # exact image, no build
    uv run yeet ./ec2_launch.py:push --frameworks jero  # build + version new images, no launch
    # backfill django-bolt into a run an earlier launch already started:
    uv run yeet ./ec2_launch.py --frameworks django-bolt --run-id 20260815T070512
"""

import base64
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, cast, get_args

import boto3
from botocore.exceptions import ClientError
from plumbum import FG, local
from pydantic_settings import BaseSettings, SettingsConfigDict

from bench import Framework

if TYPE_CHECKING:
    from types_boto3_ec2 import EC2Client
    from types_boto3_ec2.literals import InstanceTypeType
    from types_boto3_ec2.type_defs import InstanceTypeDef
    from types_boto3_ecr import ECRClient


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


@cache
def _ec2(region: str) -> "EC2Client":
    return boto3.client("ec2", region_name=region)


@cache
def _ecr(region: str) -> "ECRClient":
    return boto3.client("ecr", region_name=region)


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
_SRC_TAG_RE = re.compile(r"(?P<service>.+)-src-(?P<key>[0-9a-f]{12})")
_POSTGRES = "postgres:18-alpine"
# The Python frameworks share one build context (services/python); each image
# COPYs only its own app files on top of the shared ones (see its Dockerfile).
_PYTHON_OWN_FILES = {
    "jero": ["apps/jero_app.py"],
    "fastapi": ["apps/fastapi_app.py"],
    "litestar": ["apps/litestar_app.py"],
    "flask": ["apps/flask_app.py"],
    "blacksheep": ["apps/blacksheep_app.py"],
    "robyn": ["apps/robyn_app.py"],
    "django-bolt": ["manage.py", "django_app"],
}


def _local_image(service: str) -> str:
    return _POSTGRES if service == "postgres" else f"jero-benchmarks-{service}"


def _git_files(*pathspecs: str) -> str:
    """`git ls-tree` of HEAD's files under `pathspecs`: one path + blob hash per line."""
    repo_root = Path(__file__).resolve().parent
    return local["git"][
        "-C", str(repo_root), "ls-tree", "-r", "--full-tree", "HEAD", "--", *pathspecs
    ]()


def _postgres_digest() -> str:
    """Digest of postgres:18-alpine's current arm64 image on Docker Hub."""
    index = json.loads(local["docker"]["buildx", "imagetools", "inspect", "--raw", _POSTGRES]())
    for entry in index["manifests"]:
        platform = entry.get("platform", {})
        if (platform.get("os"), platform.get("architecture")) == ("linux", "arm64"):
            return entry["digest"]
    print(f"no linux/arm64 image in {_POSTGRES}", file=sys.stderr)
    raise SystemExit(1)


def _source_key(service: str) -> str:
    """Hash of exactly what `service`'s image is built from: its build context's
    files at HEAD (only the ones its Dockerfile COPYs, for the shared contexts),
    or for postgres the upstream image digest."""
    if service == "postgres":
        source = _postgres_digest()
    elif service == "runner":  # repo-root context, but loadtest/Dockerfile COPYs only these
        source = _git_files("loadtest", "vendor")
    elif service in _PYTHON_OWN_FILES:  # all of services/python but the others' own files
        others = tuple(
            f"services/python/{f}"
            for fw, files in _PYTHON_OWN_FILES.items()
            if fw != service
            for f in files
        )
        lines = _git_files("services/python").splitlines(keepends=True)
        source = "".join(line for line in lines if not line.split("\t", 1)[1].startswith(others))
    else:
        source = _git_files(f"services/{service}")
    return hashlib.sha256(source.encode()).hexdigest()[:12]


def _ecr_versions(settings: EC2Settings) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Every versioned image in ECR: service -> its versions, and source tag ->
    the version built from that source."""
    pages = (
        _ecr(settings.aws_region)
        .get_paginator("describe_images")
        .paginate(repositoryName=settings.ec2_ecr_repo.split("/", 1)[1])
    )
    versions: dict[str, set[str]] = {}
    by_source: dict[str, str] = {}
    for page in pages:
        for image in page["imageDetails"]:
            tags = image.get("imageTags", [])
            version_tags = [m for tag in tags if (m := _TAG_RE.fullmatch(tag))]
            for m in version_tags:
                versions.setdefault(m["service"], set()).add(m["version"])
            for tag in tags:
                if _SRC_TAG_RE.fullmatch(tag) and version_tags:
                    by_source[tag] = version_tags[0]["version"]
    return versions, by_source


def _latest(versions: dict[str, set[str]], service: str) -> str | None:
    known = versions.get(service, set())
    return max(known, key=lambda v: tuple(map(int, v.split(".")))) if known else None


def _next_version(versions: dict[str, set[str]], service: str) -> str:
    today = datetime.now(UTC).strftime("%Y.%m.%d")
    taken = [int(v.rsplit(".", 1)[1]) for v in versions.get(service, set()) if v.startswith(today)]
    return f"{today}.{max(taken, default=0) + 1:02d}"


def _push_changed(settings: EC2Settings, frameworks: list[str]) -> dict[str, str]:
    """Reuse the ECR version of every image these frameworks need whose source
    is unchanged; build and push a new version of the rest. Returns service ->
    version for everything the run will use."""
    versions, by_source = _ecr_versions(settings)
    chosen: dict[str, str] = {}
    new: dict[str, str] = {}  # service -> source tag
    for service in [*_SHARED_IMAGES, *frameworks]:
        src_tag = f"{service}-src-{_source_key(service)}"
        if src_tag in by_source:
            chosen[service] = by_source[src_tag]
            print(f"  {service}-{chosen[service]} (unchanged, {src_tag})")
        else:
            new[service] = src_tag
    if not new:
        return chosen

    repo_root = Path(__file__).resolve().parent
    docker = local["docker"]
    to_build = [svc for svc in new if svc != "postgres"]
    if to_build:
        compose_args = ["compose", "-f", "compose.base.yml"]
        for fw in frameworks:
            compose_args += ["-f", f"compose.{fw}.yml"]
        # The project name sets the image names (jero-benchmarks-<service>); pinned
        # because it otherwise comes from the checkout's directory name.
        with (
            local.cwd(repo_root),
            local.env(RUN_ID="build", COMPOSE_PROJECT_NAME="jero-benchmarks"),
        ):
            _ = docker[(*compose_args, "build", *to_build)] & FG
    if "postgres" in new:
        digest = _postgres_digest()
        _ = docker["pull", "-q", "--platform", "linux/arm64", f"postgres@{digest}"]()
        _ = docker["tag", f"postgres@{digest}", _POSTGRES]()

    auth = _ecr(settings.aws_region).get_authorization_token()["authorizationData"][0]
    _, password = base64.b64decode(auth.get("authorizationToken", "")).decode().split(":", 1)
    registry = settings.ec2_ecr_repo.split("/")[0]
    _ = (docker["login", "--username", "AWS", "--password-stdin", registry] << password)()
    for service, src_tag in new.items():
        version = _next_version(versions, service)
        print(f"  pushing {service}-{version} ({src_tag})")
        for tag in (f"{service}-{version}", src_tag):
            ref = f"{settings.ec2_ecr_repo}:{tag}"
            _ = docker["tag", _local_image(service), ref]()
            _ = docker["push", "-q", ref]()
        chosen[service] = version
    return chosen


def _existing(settings: EC2Settings, frameworks: list[str], tag: str) -> dict[str, str]:
    """No build: `tag` for every framework, the latest version of each shared image."""
    versions, _ = _ecr_versions(settings)
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
    response = _ec2(
        settings.aws_region
    ).run_instances(
        ImageId=settings.ec2_ami_id,
        InstanceType=cast("InstanceTypeType", settings.ec2_instance_type),
        KeyName=settings.ec2_key_name,
        SecurityGroupIds=[settings.ec2_security_group_id],
        SubnetId=settings.ec2_subnet_id,
        IamInstanceProfile={"Name": settings.ec2_iam_instance_profile},
        InstanceInitiatedShutdownBehavior="terminate",
        UserData=user_data,  # boto3 base64-encodes it
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": f"{run_id}-{'-'.join(frameworks)[:200]}"}],
            }
        ],
        # Always spot. One-time (not persistent) -- matches the fire-and-forget
        # lifecycle: no auto-relaunch if AWS reclaims the capacity mid-run.
        # Capped at the on-demand price implicitly (no MaxPrice override).
        InstanceMarketOptions={
            "MarketType": "spot",
            "SpotOptions": {
                "SpotInstanceType": "one-time",
                "InstanceInterruptionBehavior": "terminate",
            },
        },
        MinCount=1,
        MaxCount=1,
    )
    return response.get("Instances", [{}])[0].get("InstanceId", "")


def push(*, frameworks: str = "") -> None:
    """Build and push a new version of every changed image; launch nothing."""
    _ = _pushed_commit()  # source tags hash HEAD, so the build must be HEAD too
    fw_list = frameworks.split() or list(get_args(Framework.__value__))
    versions = _push_changed(EC2Settings(), fw_list)
    print(" ".join(f"{svc}-{ver}" for svc, ver in versions.items()))


def _running(settings: EC2Settings, run_id: str) -> int:
    """How many of this run's instances still hold spot capacity. Counted by the
    run-id name tag, so a second launcher for the same run sees the first one's
    instances too; "shutting-down" still counts against the spot quota."""
    pages = (
        _ec2(settings.aws_region)
        .get_paginator("describe_instances")
        .paginate(
            Filters=[
                {"Name": "tag:Name", "Values": [f"{run_id}-*"]},
                {
                    "Name": "instance-state-name",
                    "Values": ["pending", "running", "shutting-down", "stopping"],
                },
            ]
        )
    )
    return sum(len(r.get("Instances", [])) for page in pages for r in page["Reservations"])


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
        except ClientError as exc:
            if max_instances and exc.response.get("Error", {}).get("Code") == (
                "MaxSpotInstanceCountExceeded"
            ):
                time.sleep(30)  # capacity frees up as an instance finishes terminating
                continue
            print(f"  NOT launched {' '.join(frameworks)}: {exc}", file=sys.stderr)
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
        raise SystemExit(1)


@dataclass(frozen=True, slots=True)
class _Instance:
    id: str
    name: str
    state: str
    launched: datetime
    zone: str
    type: str
    ami: str

    @classmethod
    def of(cls, inst: "InstanceTypeDef") -> "_Instance":
        tags = {t.get("Key"): t.get("Value", "") for t in inst.get("Tags", [])}
        return cls(
            id=inst.get("InstanceId", ""),
            name=tags.get("Name", ""),
            state=inst.get("State", {}).get("Name", ""),
            launched=inst.get("LaunchTime", datetime.now(UTC)),
            zone=inst.get("Placement", {}).get("AvailabilityZone", ""),
            type=str(inst.get("InstanceType", "")),
            ami=inst.get("ImageId", ""),
        )


def _describe(settings: EC2Settings, instance_ids: list[str]) -> list[_Instance]:
    pages = (
        _ec2(settings.aws_region)
        .get_paginator("describe_instances")
        .paginate(InstanceIds=instance_ids)
    )
    return [
        _Instance.of(inst)
        for page in pages
        for reservation in page["Reservations"]
        for inst in reservation.get("Instances", [])
    ]


def _spot_price(settings: EC2Settings, instance: _Instance) -> float | None:
    """The spot $/hour in effect in the instance's zone when it launched."""
    try:
        history = _ec2(settings.aws_region).describe_spot_price_history(
            InstanceTypes=[cast("InstanceTypeType", instance.type)],
            ProductDescriptions=["Linux/UNIX"],
            AvailabilityZone=instance.zone,
            StartTime=instance.launched,
            EndTime=instance.launched,
        )["SpotPriceHistory"]
    except ClientError as exc:
        print(f"no spot price: {exc}", file=sys.stderr)
        return None
    return float(history[0].get("SpotPrice", "nan")) if history else None


def _fmt_duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{secs:02d}s"


def wait(*, run_id: str, instances: str, build_seconds: int = 0, job_started: int = 0) -> None:
    """Wait for these instances to finish (each self-terminates after its bench),
    then print a markdown summary: what each ran on, for how long, at what cost.
    Termination time is when a poll first sees the instance shutting down, so
    each runtime is accurate to the 15s poll interval."""
    settings = EC2Settings()
    ids = instances.split()
    ended: dict[str, datetime] = {}
    while True:
        described = _describe(settings, ids)
        now = datetime.now(UTC)
        for inst in described:
            if inst.state in ("shutting-down", "terminated") and inst.id not in ended:
                ended[inst.id] = now
                ran = (now - inst.launched).total_seconds()
                name = inst.name.removeprefix(f"{run_id}-")
                print(f"[{now:%H:%M:%S}] {name} done after {_fmt_duration(ran)}", file=sys.stderr)
        if len(ended) == len(ids):
            break
        time.sleep(15)

    rows = []
    total_cost: float | None = 0.0
    instance_seconds = 0.0
    for inst in sorted(described, key=lambda i: i.name):
        ran = (ended[inst.id] - inst.launched).total_seconds()
        instance_seconds += ran
        price = _spot_price(settings, inst)
        cost = None if price is None else price * ran / 3600
        total_cost = None if cost is None or total_cost is None else total_cost + cost
        rows.append(
            f"| {inst.name.removeprefix(f'{run_id}-')} | `{inst.id}` | {inst.zone} "
            f"| {_fmt_duration(ran)} "
            f"| {'n/a' if price is None else f'${price:.4f}'} "
            f"| {'n/a' if cost is None else f'${cost:.3f}'} |"
        )
    first_launch = min(i.launched for i in described)
    bench_wall = (max(ended.values()) - first_launch).total_seconds()
    types = sorted({i.type for i in described})
    amis = sorted({i.ami for i in described})

    total = f"{_fmt_duration(time.time() - job_started)} total · " if job_started else ""
    build = f"build {_fmt_duration(build_seconds)} · " if build_seconds else ""
    print("## Time and cost\n")
    bench = _fmt_duration(bench_wall)
    print(f"**{total}{build}bench {bench}** (first launch to last instance done)\n")
    print(
        f"**{'n/a' if total_cost is None else f'${total_cost:.2f}'}** for "
        f"{len(described)} x {', '.join(types)} spot ({_fmt_duration(instance_seconds)} of "
        f"instance time) · {settings.aws_region} · AMI {', '.join(f'`{a}`' for a in amis)}\n"
    )
    print("| Framework | Instance | Zone | Ran | Spot $/h | Cost |")
    print("| --- | --- | --- | --- | --- | --- |")
    print("\n".join(rows))

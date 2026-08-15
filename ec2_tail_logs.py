#!yeet
"""Tail the live benchmark log on a fire-and-forget EC2 runner (see bench.py's
docstring and the README for what that setup is).

No instance given: lists running jero-benchmarks instances (by security
group) with hex labels and prompts for a pick, same UX as
export_results.py's no-run-id case.

    uv run yeet ./ec2_tail_logs.py
    uv run yeet ./ec2_tail_logs.py i-0ad03be5e40c996d1
"""

import contextlib
import json
import sys
from functools import cache
from pathlib import Path

from plumbum import local
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.table import Table


class EC2Settings(BaseSettings):
    """Fire-and-forget EC2 runner infra — standing resources, not secrets;
    overridable via .env if the account/region/key ever changes."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "eu-central-1"
    ec2_security_group_id: str = "sg-03642d1f5a22358d3"
    ec2_ssh_key_path: str = "~/.ssh/jero-benchmarks-ec2-eu-central-1.pem"
    ec2_ssh_user: str = "ec2-user"


@cache
def _get_settings() -> EC2Settings:
    return EC2Settings()


def _describe_instances(settings: EC2Settings, *, instance_id: str = "") -> list[dict[str, str]]:
    args = [
        "ec2",
        "describe-instances",
        "--region",
        settings.aws_region,
        "--filters",
        f"Name=instance.group-id,Values={settings.ec2_security_group_id}",
        "--query",
        (
            "Reservations[].Instances[].{Id:InstanceId,Name:Tags[?Key=='Name']|[0].Value,"
            "State:State.Name,Launch:LaunchTime,IP:PublicIpAddress}"
        ),
        "--output",
        "json",
    ]
    if instance_id:
        args += ["--instance-ids", instance_id]
    out = local["aws"][args]()
    instances = json.loads(out)
    if not instance_id:
        instances = [i for i in instances if i["State"] == "running"]
    return instances


def _pick_instance(instances: list[dict[str, str]]) -> dict[str, str]:
    table = Table(title="running jero-benchmarks instances")
    table.add_column("#", style="bold cyan", justify="center")
    table.add_column("instance", style="bold")
    table.add_column("name")
    table.add_column("launched")
    table.add_column("ip")
    for label, inst in zip("0123456789abcdef", instances, strict=False):
        table.add_row(
            label,
            inst["Id"],
            inst.get("Name") or "unnamed",
            inst.get("Launch", ""),
            inst.get("IP") or "-",
        )
    Console().print(table)

    choice = input("pick an instance: ").strip().lower()
    index = "0123456789abcdef".find(choice)
    if index < 0 or index >= len(instances):
        print(f"invalid pick: {choice!r}", file=sys.stderr)
        raise SystemExit(1)
    return instances[index]


def main(instance_id: str = "") -> None:
    settings = _get_settings()
    instances = _describe_instances(settings, instance_id=instance_id)
    if not instances:
        print(
            f"no running jero-benchmarks instance found ({instance_id or 'any'})",
            file=sys.stderr,
        )
        raise SystemExit(1)

    target = instances[0] if instance_id else _pick_instance(instances)
    ip = target.get("IP")
    if not ip:
        print(f"instance {target['Id']} has no public IP (yet?)", file=sys.stderr)
        raise SystemExit(1)

    key_path = Path(settings.ec2_ssh_key_path).expanduser()
    log_path = "/var/log/jero-bench.log"
    print(
        f"tailing {log_path} on {target['Id']} ({target.get('Name') or 'unnamed'}) "
        f"@ {ip} -- Ctrl-C to stop"
    )
    with contextlib.suppress(KeyboardInterrupt):
        local["ssh"][
            "-i",
            str(key_path),
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{settings.ec2_ssh_user}@{ip}",
            "tail",
            "-f",
            log_path,
        ].run(retcode=None, stdout=None, stderr=None)

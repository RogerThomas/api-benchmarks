#!yeet
"""One-framework benchmark runner (container entrypoint).

Each `docker compose -f compose.base.yml -f compose.<fw>.yml up` cycle starts
exactly one framework; this script benches *that* framework only (env
FRAMEWORK), looping TESTS x RUNS attempts through k6, keeping the best
attempt per test, and writing every attempt into TaglyDB under the RUN_ID
the host-side bench.py orchestrator generated at kickoff — that's what ties
every framework's slice of a `task bench` invocation back together.

"Best" = highest composite score, equally weighting throughput and latency,
each metric normalized against the best of that test's attempts:
    score = reqsPerSec/maxReqs + minMean/mean + minP99/p99
(higher reqs/s better; lower mean & p99 better - so each term is in (0, 1]).
"""

import json
import os
import shutil
import tempfile
import threading
from contextlib import suppress
from datetime import datetime
from functools import cache
from pathlib import Path

from plumbum import FG, local
from pydantic_settings import BaseSettings, SettingsConfigDict
from taglydb import ConflictError, Tagly


class Settings(BaseSettings):
    """Runner config, read from the process env docker compose injects (see
    compose.base.yml's `runner.environment`) — never read raw os.environ.

    Results backend: TaglyDB, at a fixed base URL inlined in main() below --
    only the API key is secret/configurable, same as export_results.py and
    bench.py's own Settings classes.
    """

    model_config = SettingsConfigDict(extra="ignore")

    framework: str = "jero"
    tests: str = "test1 test2 test3 test4"
    runs: int = 3
    duration: str = "10s"
    vus: str = "50"
    workers: int = 1
    python_server: str = "granian"
    loop: str = "uvloop"
    result_label: str | None = None
    run_id: str
    run_created_at: datetime
    results_dir: Path = Path("/results")
    bench_hostname: str | None = None
    ec2_ami_id: str | None = None
    ec2_instance_type: str | None = None
    aws_region: str | None = None

    taglydb_api_key: str


@cache
def _get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- fields come from the process env, not the constructor


# TaglyDB indexes are permanent, principal-scoped containers -- created
# once, then reused by every run. "Runs" holds one JSON item per RUN_ID;
# "results" holds one JSON item per (run, framework, test, attempt).
_RUNS_INDEX_KEY = "runs"
_RESULTS_INDEX_KEY = "results"


def _ensure_index(client: Tagly, key: str) -> str:
    existing = client.indexes.list(key=key).items
    if existing:
        return existing[0].id
    try:
        return client.indexes.create(key=key, type="json", tags={}).id
    except ConflictError:
        # Lost a race with another framework's runner container -- fine,
        # whichever created it first wins, both point at the same key.
        return client.indexes.list(key=key).items[0].id


def _write_run(client: Tagly, runs_index_id: str, settings: Settings) -> None:
    """One item per RUN_ID, shared by every framework that run looped over --
    the TaglyDB item-key uniqueness (and 409 on a duplicate key) makes this
    idempotent across frameworks/backfills, matching the old Run.get_or_create."""
    if client.items.list(runs_index_id, key=settings.run_id).items:
        return
    data = {
        "run_id": settings.run_id,
        "created_at": settings.run_created_at.isoformat(),
        "duration": settings.duration,
        "vus": int(settings.vus),
        "best_of": settings.runs,
        "workers": settings.workers,
        "python_server": settings.python_server,
        "loop": settings.loop,
        "hostname": settings.bench_hostname,
        "ec2_ami_id": settings.ec2_ami_id,
        "ec2_instance_type": settings.ec2_instance_type,
        "aws_region": settings.aws_region,
    }
    with suppress(ConflictError):  # another framework in this run just beat us to it
        client.items.create_json(
            runs_index_id,
            key=settings.run_id,
            tags={"hostname": settings.bench_hostname or ""},
            data=data,
        )


def _container_id(service: str) -> str | None:
    # Matched by compose's service label, not name, so it works regardless of
    # the generated container name.
    docker_ps = local["docker"]["ps", "-q", "-f", f"label=com.docker.compose.service={service}"]
    _, out, _ = docker_ps.run(retcode=None)
    out = out.strip()
    return out.splitlines()[0] if out else None


def _parse_mem_mb(s: str) -> float:
    s = s.strip()
    for unit, factor in (("GiB", 1024.0), ("MiB", 1.0), ("KiB", 1 / 1024.0)):
        if s.endswith(unit):
            return float(s[: -len(unit)]) * factor
    return float(s.rstrip("B")) / (1024.0 * 1024.0)


def _sparkline(values: list[float], width: int = 16) -> str:
    """Bucket `values` into `width` buckets and render as a 0-to-peak-scaled
    unicode sparkline, so short and long runs render the same visual width."""
    if not values:
        return ""
    n = len(values)
    buckets = []
    for i in range(width):
        lo = i * n // width
        hi = max(lo + 1, (i + 1) * n // width)
        chunk = values[lo:hi]
        buckets.append(sum(chunk) / len(chunk))
    peak = max(buckets) or 1.0
    spark_chars = "▁▂▃▄▅▆▇█"
    return "".join(
        spark_chars[min(len(spark_chars) - 1, int(v / peak * (len(spark_chars) - 1)))]
        for v in buckets
    )


class _StatsPoller:
    """Polls `docker stats --no-stream` (cgroup CPU/mem) every 0.5s in a
    background thread for the duration of one k6 attempt.

    `--no-stream` matters: streaming mode reports 0.00% CPU when piped to a
    non-TTY, which is useless here — each --no-stream call computes a real
    daemon-side CPU delta instead.
    """

    def __init__(self, cid: str | None) -> None:
        self._cid = cid
        self._samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "_StatsPoller":
        if self._cid:
            self._thread = threading.Thread(target=self._run, args=(self._cid,), daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self, cid: str) -> None:
        docker_stats = local["docker"][
            "stats", "--no-stream", "--format", "{{.CPUPerc}}\t{{.MemUsage}}", cid
        ]
        while not self._stop.is_set():
            try:
                _, out, _ = docker_stats.run(retcode=None, timeout=3)
                out = out.strip()
                if out:
                    cpu_s, mem_s = out.split("\t")
                    self._samples.append((
                        float(cpu_s.rstrip("%")),
                        _parse_mem_mb(mem_s.split("/")[0]),
                    ))
            except Exception:  # noqa: BLE001, S110 -- a transient docker-stats hiccup
                # (container mid-restart, daemon busy) should just cost this one
                # sample, not abort the benchmark attempt in progress.
                pass
            self._stop.wait(0.5)

    def reduce(self) -> dict:
        if not self._samples:
            return {}
        cpus = [c for c, _ in self._samples]
        mems = [m for _, m in self._samples]
        return {
            "avg_cpu_pct": sum(cpus) / len(cpus),
            "peak_cpu_pct": max(cpus),
            "avg_rss_mb": sum(mems) / len(mems),
            "peak_rss_mb": max(mems),
            "cpu_spark": _sparkline(cpus),
            "mem_spark": _sparkline(mems),
        }


def _run_attempt(test: str, attempt: int, work_dir: Path) -> dict:
    framework = _get_settings().framework
    cid = _container_id(framework)
    if cid is None:
        print(f"  (no container for {framework} — resource columns will be blank)")
    env = {
        **os.environ,
        "TEST": test,
        "ATTEMPT": str(attempt),
        "BASE_URL": f"http://{framework}:8000",
        "RESULTS_DIR": str(work_dir),
    }
    with _StatsPoller(cid) as poller:
        _ = local["k6"]["run", "--quiet", f"/scenarios/{test}.js"].with_env(**env) & FG
    attempt_file = work_dir / f"attempt-{framework}-{test}-{attempt}.json"
    data = json.loads(attempt_file.read_text())
    data.update(poller.reduce())
    return data


def _bench_test(test: str, work_dir: Path) -> list[dict]:
    settings = _get_settings()
    display = settings.result_label or settings.framework
    print(f"==> {display} / {test} (best of {settings.runs})")
    attempts = [_run_attempt(test, i, work_dir) for i in range(1, settings.runs + 1)]
    for a in attempts:
        print(
            f"  {display}/{test} attempt {a['attempt']}: {a['reqsPerSec']:.0f} req/s, "
            f"mean {a['latencyMs']['avg']:.2f}ms, p99 {a['latencyMs']['p99']:.2f}ms"
        )
    best = max(a["reqsPerSec"] for a in attempts)
    for a in attempts:
        a["is_best"] = a["reqsPerSec"] == best
    return attempts


def _insert_results(client: Tagly, results_index_id: str, test: str, attempts: list[dict]) -> None:
    settings = _get_settings()
    framework = settings.result_label or settings.framework
    for a in attempts:
        # No key -- TaglyDB items don't require one, and a natural
        # (run, framework, test, attempt) key would just make a rerun of the
        # exact same attempt 409 instead of writing a normal new item.
        # export_results.py resolves reruns of the same attempt by taking
        # the newest createdAt per (framework, test, attempt) group.
        data = {
            "run_id": settings.run_id,
            "framework": framework,
            "test": test,
            "attempt": a["attempt"],
            "reqs_per_sec": a["reqsPerSec"],
            "latency_avg_ms": a["latencyMs"]["avg"],
            "latency_p50_ms": a["latencyMs"]["p50"],
            "latency_p75_ms": a["latencyMs"]["p75"],
            "latency_p90_ms": a["latencyMs"]["p90"],
            "latency_p99_ms": a["latencyMs"]["p99"],
            "failed_rate": a["failedRate"],
            "total_requests": a["totalRequests"],
            "is_best": a["is_best"],
            "peak_rss_mb": a.get("peak_rss_mb"),
            "avg_rss_mb": a.get("avg_rss_mb"),
            "avg_cpu_pct": a.get("avg_cpu_pct"),
            "peak_cpu_pct": a.get("peak_cpu_pct"),
            "cpu_spark": a.get("cpu_spark"),
            "mem_spark": a.get("mem_spark"),
        }
        tags = {
            "run_id": settings.run_id,
            "framework": framework,
            "test": test,
            "is_best": "true" if a["is_best"] else "false",
        }
        client.items.create_json(results_index_id, tags=tags, data=data)


def main() -> None:
    settings = _get_settings()
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    display = settings.result_label or settings.framework
    print(
        f"==> {display} · py:{settings.python_server}/{settings.loop} · "
        f"{settings.vus} VUs · {settings.duration}/test · best-of-{settings.runs} · "
        f"{settings.workers} worker(s) · run {settings.run_id} · results -> TaglyDB"
    )

    with Tagly.build(
        base_url="https://api.taglydb.com", api_key=settings.taglydb_api_key
    ) as client:
        runs_index_id = _ensure_index(client, _RUNS_INDEX_KEY)
        results_index_id = _ensure_index(client, _RESULTS_INDEX_KEY)
        _write_run(client, runs_index_id, settings)

        work_dir = Path(tempfile.mkdtemp(prefix="bench-"))
        try:
            for test in settings.tests.split():
                _insert_results(client, results_index_id, test, _bench_test(test, work_dir))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    print(f"\n==> wrote {display} results to TaglyDB under run {settings.run_id}")

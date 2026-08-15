#!yeet
"""One-framework benchmark runner (container entrypoint).

Each `docker compose -f compose.base.yml -f compose.<fw>.yml up` cycle starts
exactly one framework; this script benches *that* framework only (env
FRAMEWORK), looping TESTS x RUNS attempts through k6, keeping the best
attempt per test, and writing every attempt into results/bench.db under the
RUN_ID the host-side bench.py orchestrator generated at kickoff — that's what
ties every framework's slice of a `task bench` invocation back together.

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
from datetime import datetime
from functools import cache
from pathlib import Path

import peewee
from plumbum import FG, local
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runner config, read from the process env docker compose injects (see
    compose.base.yml's `runner.environment`) — never read raw os.environ.

    Results backend: Postgres (e.g. Neon) if PG_HOST is set, else SQLite at
    SQLITE_PATH, else the local default under RESULTS_DIR. This is the same
    "Postgres if configured, else local SQLite" rule export_results.py and
    bench.py use — see their own Settings classes.
    """

    model_config = SettingsConfigDict(extra="ignore")

    framework: str = "jero"
    tests: str = "test1 test2 test3 test4"
    runs: int = 3
    duration: str = "10s"
    vus: str = "50"
    workers: int = 1
    python_server: str = "granian"
    run_id: str
    run_created_at: datetime
    results_dir: Path = Path("/results")
    bench_hostname: str | None = None

    pg_host: str | None = None
    pg_port: int = 5432
    pg_db: str | None = None
    pg_user: str | None = None
    pg_password: str | None = None
    pg_sslmode: str = "require"
    pg_channel_binding: str = "require"
    sqlite_path: str | None = None


@cache
def _get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- fields come from the process env, not the constructor


def _build_db(settings: Settings) -> peewee.Database:
    if settings.pg_host:
        return peewee.PostgresqlDatabase(
            settings.pg_db,
            host=settings.pg_host,
            port=settings.pg_port,
            user=settings.pg_user,
            password=settings.pg_password,
            sslmode=settings.pg_sslmode,
            channel_binding=settings.pg_channel_binding,
        )  # pyright: ignore[reportArgumentType] -- pg_db/user/password are only unset when pg_host is also unset
    return peewee.SqliteDatabase(
        settings.sqlite_path or str(settings.results_dir / "bench.db"),
        pragmas={"busy_timeout": 30000},
    )


@cache
def _get_db() -> peewee.DatabaseProxy:
    # A proxy, not a real connection: the actual backend (Postgres or
    # SQLite) isn't known until Settings is read, but Model.Meta.database
    # needs *something* bound at class-definition time — db.initialize()
    # swaps in the real Database once main() has read the settings.
    return peewee.DatabaseProxy()


class BaseModel(peewee.Model):
    class Meta:
        database = _get_db()


class Run(BaseModel):
    """One `task bench` invocation — shared by every framework it looped over."""

    run_id = peewee.CharField(primary_key=True)
    created_at = peewee.DateTimeField()
    duration = peewee.CharField()
    vus = peewee.IntegerField()
    best_of = peewee.IntegerField()
    workers = peewee.IntegerField()
    python_server = peewee.CharField()
    hostname = peewee.CharField(null=True)

    class Meta:
        table_name = "runs"


class Result(BaseModel):
    """One k6 attempt for (run, framework, test) — `is_best` marks the
    highest-scoring attempt per (run, framework, test), the one export_results.py
    compares across frameworks."""

    run = peewee.ForeignKeyField(Run, backref="results", field="run_id", column_name="run_id")
    framework = peewee.CharField()
    test = peewee.CharField()
    attempt = peewee.IntegerField()
    reqs_per_sec = peewee.FloatField()
    latency_avg_ms = peewee.FloatField()
    latency_p50_ms = peewee.FloatField()
    latency_p75_ms = peewee.FloatField()
    latency_p90_ms = peewee.FloatField()
    latency_p99_ms = peewee.FloatField()
    failed_rate = peewee.FloatField()
    total_requests = peewee.IntegerField()
    score = peewee.FloatField()
    is_best = peewee.BooleanField()
    peak_rss_mb = peewee.FloatField(null=True)
    avg_rss_mb = peewee.FloatField(null=True)
    avg_cpu_pct = peewee.FloatField(null=True)
    peak_cpu_pct = peewee.FloatField(null=True)
    cpu_spark = peewee.CharField(null=True)
    mem_spark = peewee.CharField(null=True)

    class Meta:
        table_name = "results"
        indexes = ((("run", "framework", "test", "attempt"), True),)


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


def _score(attempt: dict, max_reqs: float, min_mean: float, min_p99: float) -> float:
    return (
        attempt["reqsPerSec"] / max_reqs
        + min_mean / attempt["latencyMs"]["avg"]
        + min_p99 / attempt["latencyMs"]["p99"]
    )


def _bench_test(test: str, work_dir: Path) -> list[dict]:
    settings = _get_settings()
    print(f"==> {settings.framework} / {test} (best of {settings.runs})")
    attempts = [_run_attempt(test, i, work_dir) for i in range(1, settings.runs + 1)]
    for a in attempts:
        print(
            f"  {settings.framework}/{test} attempt {a['attempt']}: {a['reqsPerSec']:.0f} req/s, "
            f"mean {a['latencyMs']['avg']:.2f}ms, p99 {a['latencyMs']['p99']:.2f}ms"
        )
    max_reqs = max(a["reqsPerSec"] for a in attempts)
    min_mean = min(a["latencyMs"]["avg"] for a in attempts)
    min_p99 = min(a["latencyMs"]["p99"] for a in attempts)
    for a in attempts:
        a["score"] = _score(a, max_reqs, min_mean, min_p99)
    best = max(a["score"] for a in attempts)
    for a in attempts:
        a["is_best"] = a["score"] == best
    return attempts


def _insert_results(test: str, attempts: list[dict]) -> None:
    settings = _get_settings()
    for a in attempts:
        # insert().on_conflict(conflict_target=..., preserve=...) — the
        # portable upsert across SQLite and Postgres. peewee's .replace()
        # shortcut only works on SQLite/MySQL (INSERT OR REPLACE has no
        # Postgres equivalent); this compiles to ON CONFLICT ... DO UPDATE
        # on both. The unique index on (run, framework, test, attempt)
        # makes reruns idempotent either way.
        Result.insert(
            run=settings.run_id,
            framework=settings.framework,
            test=test,
            attempt=a["attempt"],
            reqs_per_sec=a["reqsPerSec"],
            latency_avg_ms=a["latencyMs"]["avg"],
            latency_p50_ms=a["latencyMs"]["p50"],
            latency_p75_ms=a["latencyMs"]["p75"],
            latency_p90_ms=a["latencyMs"]["p90"],
            latency_p99_ms=a["latencyMs"]["p99"],
            failed_rate=a["failedRate"],
            total_requests=a["totalRequests"],
            score=a["score"],
            is_best=a["is_best"],
            peak_rss_mb=a.get("peak_rss_mb"),
            avg_rss_mb=a.get("avg_rss_mb"),
            avg_cpu_pct=a.get("avg_cpu_pct"),
            peak_cpu_pct=a.get("peak_cpu_pct"),
            cpu_spark=a.get("cpu_spark"),
            mem_spark=a.get("mem_spark"),
        ).on_conflict(
            conflict_target=[Result.run, Result.framework, Result.test, Result.attempt],
            preserve=[
                Result.reqs_per_sec,
                Result.latency_avg_ms,
                Result.latency_p50_ms,
                Result.latency_p75_ms,
                Result.latency_p90_ms,
                Result.latency_p99_ms,
                Result.failed_rate,
                Result.total_requests,
                Result.score,
                Result.is_best,
                Result.peak_rss_mb,
                Result.avg_rss_mb,
                Result.avg_cpu_pct,
                Result.peak_cpu_pct,
                Result.cpu_spark,
                Result.mem_spark,
            ],
        ).execute()


def main() -> None:
    settings = _get_settings()
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    destination = (
        f"postgres://{settings.pg_host}/{settings.pg_db}"
        if settings.pg_host
        else settings.sqlite_path or str(settings.results_dir / "bench.db")
    )
    print(
        f"==> {settings.framework} · py:{settings.python_server} · {settings.vus} VUs · "
        f"{settings.duration}/test · best-of-{settings.runs} · {settings.workers} worker(s) · "
        f"run {settings.run_id} · results -> {destination}"
    )

    db = _get_db()
    db.initialize(_build_db(settings))
    db.connect()
    db.create_tables([Run, Result])
    Run.get_or_create(
        run_id=settings.run_id,
        defaults={
            "created_at": settings.run_created_at,
            "duration": settings.duration,
            "vus": int(settings.vus),
            "best_of": settings.runs,
            "workers": settings.workers,
            "python_server": settings.python_server,
            "hostname": settings.bench_hostname,
        },
    )

    work_dir = Path(tempfile.mkdtemp(prefix="bench-"))
    try:
        for test in settings.tests.split():
            _insert_results(test, _bench_test(test, work_dir))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        db.close()

    print(f"\n==> wrote {settings.framework} results to {destination} under run {settings.run_id}")

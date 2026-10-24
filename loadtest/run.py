#!yeet
"""One-framework benchmark runner (container entrypoint).

Each `docker compose -f compose.base.yml -f compose.<fw>.yml up` cycle starts
exactly one framework; this script benches *that* framework only (env
FRAMEWORK), looping TESTS x RUNS attempts through the load generator
(LOADGEN: oha or wrk), keeping the best attempt per test, and writing every
attempt into TaglyDB under the RUN_ID the host-side bench.py orchestrator
generated at kickoff — that's what ties every framework's slice of a
`task bench` invocation back together.

Per test: a correctness pass (sequential requests whose status AND body are
checked), an untimed warm-up (so lazily-built clients/pools and JIT warm-up
never land in a measured attempt), then RUNS measured attempts; "best" is the
attempt with the highest req/s. Correctness is checked here rather than inside
the load generator, so checking never slows the tool doing the measuring.
"""

import base64
import hashlib
import hmac
import json
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from email.message import Message
from functools import cache
from pathlib import Path
from typing import Any

from plumbum import local
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
    loadgen: str = "wrk"
    jwt_secret: str
    run_id: str
    run_created_at: datetime
    bench_hostname: str | None = None
    ec2_ami_id: str | None = None
    ec2_instance_type: str | None = None
    aws_region: str | None = None
    images: str | None = None  # exact ECR tags, e.g. "jero-2026.10.23.01 runner-..."
    commit: str | None = None  # git sha the run's code came from ("-dirty" if uncommitted)

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
        "loadgen": settings.loadgen,
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
    background thread for the duration of one load-generator attempt.

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


# --- What each test sends, and what a correct answer looks like ---------------


@dataclass(frozen=True)
class Scenario:
    method: str
    path: str
    expected_status: int
    # Given the response headers and parsed JSON body: is this the right answer?
    is_correct: Callable[[Message, Any], bool]
    body: str | None = None
    authenticated: bool = False


_MOVIE = json.dumps({
    "title": "Blade Runner 2049",
    "year": 2017,
    "director": "Denis Villeneuve",
    "genre": "Sci-Fi",
    "rating": 8.0,
})

SCENARIOS = {
    "test1": Scenario(
        "GET",
        "/info",
        200,
        lambda h, b: (
            bool(h.get("x-response-id"))
            and b["id"] == "info-1"
            and b["createdAt"] == "2026-01-01T00:00:00Z"
            and b["nested"]["level"] == 2
        ),
    ),
    "test2": Scenario(
        "POST",
        "/movies",
        201,
        lambda _, b: (
            bool(b["id"])
            and b["title"] == "Blade Runner 2049"
            and b["year"] == 2017
            and b["user"]["id"] == "user-123"
            and b["user"]["name"] == "Ada Lovelace"
        ),
        body=_MOVIE,
        authenticated=True,
    ),
    "test3": Scenario(
        "GET",
        "/catalog",
        200,
        lambda _, b: b["id"] == "prod-1" and b["inStock"] is True and bool(b["vendor"]["name"]),
    ),
    "test4": Scenario(
        "GET",
        "/users/me",
        200,
        lambda _, b: (
            b["id"] == "user-123" and b["email"] == "ada@example.com" and b["city"] == "London"
        ),
        authenticated=True,
    ),
}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@cache
def _token() -> str:
    """HS256 JWT for the seeded user (services/db/init.sql), minted in-process."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    claims = {"sub": "user-123", "name": "Ada Lovelace", "iat": 1735689600}
    signing_input = f"{header}.{_b64url(json.dumps(claims).encode())}"
    secret = _get_settings().jwt_secret.encode()
    signature = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def _headers(scenario: Scenario) -> dict[str, str]:
    headers = {}
    if scenario.body is not None:
        headers["content-type"] = "application/json"
    if scenario.authenticated:
        headers["authorization"] = f"Bearer {_token()}"
    return headers


def _url(scenario: Scenario) -> str:
    return f"http://{_get_settings().framework}:8000{scenario.path}"


# --- Correctness pass ----------------------------------------------------------

_VERIFY_REQUESTS = 100


def _wrong_fraction(scenario: Scenario) -> float:
    """Send _VERIFY_REQUESTS sequential requests; return the share that came back
    wrong (bad status, unparseable body, or a body that fails `is_correct`)."""
    wrong = 0
    for _ in range(_VERIFY_REQUESTS):
        request = urllib.request.Request(  # noqa: S310 -- fixed http:// URL on the bench network
            _url(scenario),
            data=scenario.body.encode() if scenario.body else None,
            headers=_headers(scenario),
            method=scenario.method,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
                ok = response.status == scenario.expected_status and scenario.is_correct(
                    response.headers, json.loads(response.read())
                )
        except Exception:  # noqa: BLE001 -- any failure (HTTP error, bad JSON, missing key) = wrong
            ok = False
        wrong += not ok
    return wrong / _VERIFY_REQUESTS


# --- Load generators -----------------------------------------------------------
#
# Both are closed-loop: `vus` connections, each sending its next request as soon
# as the previous response arrives, for `duration`. Each returns the same shape:
# req/s, latency in ms, total requests, and the share that failed (wrong status
# or a transport error).


def _run_oha(scenario: Scenario, duration: str) -> dict:
    settings = _get_settings()
    # -w: let requests in flight at the deadline finish (oha otherwise counts
    # them as "aborted due to deadline" errors, which aren't the framework's).
    args = ["-z", duration, "-c", settings.vus, "-w", "--no-tui", "--output-format", "json"]
    args += ["-m", scenario.method]
    for name, value in _headers(scenario).items():
        args += ["-H", f"{name}: {value}"]
    if scenario.body is not None:
        args += ["-d", scenario.body]
    out = json.loads(local["oha"][(*args, _url(scenario))]())
    summary, pct = out["summary"], out["latencyPercentiles"]
    statuses = {int(code): n for code, n in out["statusCodeDistribution"].items()}
    total = sum(statuses.values()) + sum(out["errorDistribution"].values())
    return {
        "reqsPerSec": summary["requestsPerSec"],
        "totalRequests": total,
        "failedRate": 1 - statuses.get(scenario.expected_status, 0) / total if total else 1.0,
        "latencyMs": {
            "avg": summary["average"] * 1000,
            "min": summary["fastest"] * 1000,
            "max": summary["slowest"] * 1000,
            **{k: pct[k] * 1000 for k in ("p50", "p75", "p90", "p99")},
        },
    }


# wrk takes the method/body/headers from a Lua script, and its `done` hook (run
# once, after the test) prints the summary as one JSON line.
_WRK_DONE = """
done = function(summary, latency, requests)
  local e = summary.errors
  io.write(string.format(
    '{"requests":%d,"duration_us":%d,"failed":%d,"mean_us":%f,"min_us":%d,"max_us":%d,'
      .. '"p50_us":%d,"p75_us":%d,"p90_us":%d,"p99_us":%d}\\n',
    summary.requests, summary.duration, e.connect + e.read + e.write + e.status + e.timeout,
    latency.mean, latency.min, latency.max, latency:percentile(50), latency:percentile(75),
    latency:percentile(90), latency:percentile(99)))
end
"""


def _run_wrk(scenario: Scenario, duration: str, work_dir: Path) -> dict:
    settings = _get_settings()
    lua = [f"wrk.method = {json.dumps(scenario.method)}"]
    if scenario.body is not None:
        lua.append(f"wrk.body = {json.dumps(scenario.body)}")
    lua += [
        f"wrk.headers[{json.dumps(k)}] = {json.dumps(v)}" for k, v in _headers(scenario).items()
    ]
    script = work_dir / "wrk.lua"
    script.write_text("\n".join(lua) + _WRK_DONE)
    # -t2: one thread per core of the runner's 2-core cpuset (compose.base.yml).
    args = ["-t2", "-c", settings.vus, "-d", duration, "-s", str(script), _url(scenario)]
    last_line = local["wrk"][args]().strip().splitlines()[-1]
    out = json.loads(last_line)
    total = out["requests"]
    return {
        "reqsPerSec": total / (out["duration_us"] / 1e6),
        "totalRequests": total,
        "failedRate": out["failed"] / total if total else 1.0,
        "latencyMs": {
            "avg": out["mean_us"] / 1000,
            "min": out["min_us"] / 1000,
            "max": out["max_us"] / 1000,
            **{k: out[f"{k}_us"] / 1000 for k in ("p50", "p75", "p90", "p99")},
        },
    }


def _run_load(scenario: Scenario, duration: str, work_dir: Path) -> dict:
    if _get_settings().loadgen == "oha":
        return _run_oha(scenario, duration)
    return _run_wrk(scenario, duration, work_dir)


# Untimed pass before each test's measured attempts; its result is discarded.
_WARMUP_DURATION = "3s"


def _run_attempt(test: str, attempt: int, work_dir: Path) -> dict:
    settings = _get_settings()
    cid = _container_id(settings.framework)
    if cid is None:
        print(f"  (no container for {settings.framework} — resource columns will be blank)")
    with _StatsPoller(cid) as poller:
        data = _run_load(SCENARIOS[test], settings.duration, work_dir)
    data.update(attempt=attempt, durationSec=int(settings.duration.rstrip("s")), **poller.reduce())
    return data


def _bench_test(test: str, work_dir: Path) -> list[dict]:
    settings = _get_settings()
    display = settings.framework
    scenario = SCENARIOS[test]
    wrong = _wrong_fraction(scenario)
    if wrong:
        print(f"  !! {display}/{test}: {wrong:.0%} of correctness-pass responses were wrong")
    print(f"==> {display} / {test} (warm-up {_WARMUP_DURATION}, then best of {settings.runs})")
    _run_load(scenario, _WARMUP_DURATION, work_dir)
    attempts = [_run_attempt(test, i, work_dir) for i in range(1, settings.runs + 1)]
    for a in attempts:
        # A wrong answer in the correctness pass fails the whole test: fast-but-
        # wrong must never show up as a success.
        if wrong:
            a["failedRate"] = 1.0
        print(
            f"  {display}/{test} attempt {a['attempt']}: {a['reqsPerSec']:.0f} req/s, "
            f"mean {a['latencyMs']['avg']:.2f}ms, p99 {a['latencyMs']['p99']:.2f}ms, "
            f"failed {a['failedRate']:.2%}"
        )
    best = max(a["reqsPerSec"] for a in attempts)
    for a in attempts:
        a["is_best"] = a["reqsPerSec"] == best
    return attempts


def _insert_results(client: Tagly, results_index_id: str, test: str, attempts: list[dict]) -> None:
    settings = _get_settings()
    framework = settings.framework
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
            "images": settings.images,
            "commit": settings.commit,
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
    display = settings.framework
    print(
        f"==> {settings.framework} · "
        f"{settings.loadgen} · {settings.vus} connections · {settings.duration}/test · "
        f"best-of-{settings.runs} · "
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

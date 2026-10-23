#!yeet
"""Prints the comparison tables for one `task bench` run: one box table per
test, the best-of-N winner for each framework (Result.is_best), sorted by
req/s descending, with "vs" columns normalized against jero (the fleet's
baseline) — same shape the old table.awk produced, now reading TaglyDB
instead of a report-<ts>.json file.

Also writes a full markdown report (comparison tables + a chart SVG + the
methodology and exact run config a future agent would need to reproduce or
extend these numbers), the chart SVG, and the raw underlying results as JSON,
to reports/<run_id>/{report.md,chart.svg,results.json}.

    task export-results -- 20260813T120000
    uv run yeet ./export_results.py 20260813T120000
    task export-results                     # no run-id: pick from the 36 most recent
"""

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import msgspec
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.table import Table
from taglydb import Item, Tagly

ROOT = Path(__file__).resolve().parent

_RUNS_INDEX_KEY = "runs"
_RESULTS_INDEX_KEY = "results"


class Settings(BaseSettings):
    """Results backend: TaglyDB, at a fixed base URL inlined in main()
    below -- only the API key is secret/configurable. Same rule
    loadtest/run.py's Settings uses to pick a backend."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    taglydb_api_key: str


@cache
def _get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- fields come from .env, not the constructor


@dataclass
class Run:
    """One `task bench` invocation — shared by every framework it looped over."""

    run_id: str
    created_at: datetime
    duration: str
    vus: int
    best_of: int
    workers: int
    python_server: str | None = None  # only on old runs; peregrine since
    loop: str | None = None  # only set on old runs, from when --loop existed
    loadgen: str | None = None
    hostname: str | None = None
    ec2_ami_id: str | None = None
    ec2_instance_type: str | None = None
    aws_region: str | None = None


@dataclass
class Result:
    """One load-generator attempt for (run, framework, test) — `is_best` marks the
    highest-scoring attempt per (run, framework, test), the one this script
    compares across frameworks."""

    framework: str
    test: str
    attempt: int
    reqs_per_sec: float
    latency_avg_ms: float
    latency_p50_ms: float
    latency_p75_ms: float
    latency_p90_ms: float
    latency_p99_ms: float
    failed_rate: float
    total_requests: int
    is_best: bool
    peak_rss_mb: float | None = None
    avg_rss_mb: float | None = None
    avg_cpu_pct: float | None = None
    peak_cpu_pct: float | None = None
    cpu_spark: str | None = None
    mem_spark: str | None = None
    images: str | None = None


def _find_index(client: Tagly, key: str) -> str | None:
    items = client.indexes.list(key=key).items
    return items[0].id if items else None


def _list_all_items(
    client: Tagly, index_id: str, *, tags: dict[str, str] | None = None
) -> list[Item]:
    items: list[Item] = []
    cursor: str | None = None
    while True:
        page = client.items.list(index_id, limit=250, cursor=cursor, tags=tags)
        items += page.items
        if not page.next_cursor:
            return items
        cursor = page.next_cursor


def _fetch_run(client: Tagly, runs_index_id: str, run_id: str) -> Run | None:
    matches = client.items.list_with_data(runs_index_id, key=run_id).items
    if not matches:
        return None
    return msgspec.convert(matches[0].data, Run)


def _fetch_results(client: Tagly, results_index_id: str, run_id: str) -> list[Result]:
    """Every attempt is written under a random item key (not a deterministic
    (run, framework, test, attempt) composite), so a rerun of the same
    attempt lands as a second item rather than a 409 -- resolve that here by
    keeping only the newest (by the item's own createdAt) per
    (framework, test, attempt) group, rather than every item verbatim."""
    items = client.items.list_with_data(results_index_id, tags={"run_id": run_id}).items
    newest: dict[tuple[str, str, int], tuple[datetime, Result]] = {}
    for item in items:
        result = msgspec.convert(item.data, Result)
        group = (result.framework, result.test, result.attempt)
        current = newest.get(group)
        if current is None or item.created_at > current[0]:
            newest[group] = (item.created_at, result)
    return [result for _, result in newest.values()]


TEST_LABELS = {
    "test1": "1 - GET /info",
    "test2": "2 - POST /movies (JWT)",
    "test3": "3 - GET proxy (upstream)",
    "test4": "4 - GET /users/me (DB)",
}

COLUMNS = [
    "Framework",
    "req/s",
    "vs",
    "mean",
    "vs",
    "p99",
    "vs",
    "succ%",
    "memPk",
    "memAv",
    "cpuAv",
    "cpuPk",
    "cpu ~",
    "mem ~",
]
SPARK_COLUMNS = {12, 13}
SPARK_WIDTH = 16

H, V = "─", "│"
TL, TM, TR = "┌", "┬", "┐"
ML, MM, MR = "├", "┼", "┤"
BL, BM, BR = "└", "┴", "┘"


def _fmt_rps(v: float) -> str:
    return f"~{v / 1000:.1f}k" if v >= 1000 else f"{v:.0f}"


def _rule(left: str, mid: str, right: str, widths: list[int]) -> str:
    return left + mid.join(H * (w + 2) for w in widths) + right


def _row(cells: list[str], widths: list[int]) -> str:
    return V + V.join(f" {c:<{w}} " for c, w in zip(cells, widths, strict=True)) + V


def _result_cells(r: Result, jero: Result | None) -> list[str]:
    """One row's cells, matching COLUMNS — shared by the terminal ASCII table
    and the markdown report table so the vs-jero math lives in one place."""
    vs_rps = f"x{r.reqs_per_sec / jero.reqs_per_sec:.2f}" if jero and jero.reqs_per_sec else "-"
    vs_mean = f"x{jero.latency_avg_ms / r.latency_avg_ms:.2f}" if jero and r.latency_avg_ms else "-"
    vs_p99 = f"x{jero.latency_p99_ms / r.latency_p99_ms:.2f}" if jero and r.latency_p99_ms else "-"
    return [
        r.framework,
        _fmt_rps(r.reqs_per_sec),
        vs_rps,
        f"{r.latency_avg_ms:.2f}ms",
        vs_mean,
        f"{r.latency_p99_ms:.2f}ms",
        vs_p99,
        f"{(1 - r.failed_rate) * 100:.2f}",
        f"{r.peak_rss_mb or 0:.0f}M",
        f"{r.avg_rss_mb or 0:.0f}M",
        f"{r.avg_cpu_pct or 0:.0f}%",
        f"{r.peak_cpu_pct or 0:.0f}%",
        r.cpu_spark or "",
        r.mem_spark or "",
    ]


def _render_table(test: str, results: list[Result]) -> list[str]:
    jero = next((r for r in results if r.framework == "jero"), None)
    grid = [COLUMNS, *(_result_cells(r, jero) for r in results)]

    widths = []
    for c in range(len(COLUMNS)):
        widths.append(
            SPARK_WIDTH if c in SPARK_COLUMNS else max(len(grid_row[c]) for grid_row in grid)
        )

    lines = [_rule(TL, TM, TR, widths), _row(grid[0], widths), _rule(ML, MM, MR, widths)]
    body = grid[1:]
    for i, grid_row in enumerate(body):
        lines.append(_row(grid_row, widths))
        if i < len(body) - 1:
            lines.append(_rule(ML, MM, MR, widths))
    lines.append(_rule(BL, BM, BR, widths))

    return [TEST_LABELS.get(test, test), *lines]


def _render_markdown_table(test: str, results: list[Result]) -> list[str]:
    """Same cells and vs-jero math as _render_table, wrapped as a GFM table
    instead of box-drawing art."""
    jero = next((r for r in results if r.framework == "jero"), None)
    header = f"| {' | '.join(COLUMNS)} |"
    separator = f"| {' | '.join('---' for _ in COLUMNS)} |"
    rows = [f"| {' | '.join(_result_cells(r, jero))} |" for r in results]
    return [f"### {TEST_LABELS.get(test, test)}", "", header, separator, *rows]


# Per-test chart headline + a short "what this measures" caption, matching
# the visual language of jero's own bench-grid.svg.
TEST_HEADLINES: dict[str, tuple[str, str]] = {
    "test1": ("JSON — GET /info", "the pure framework path"),
    "test2": ("JWT — POST /movies", "validates the body, decodes a bearer token"),
    "test3": ("Proxy — GET /catalog", "one outbound hop to the upstream service"),
    "test4": ("Database — GET /users/me", "bound by the DB driver"),
}

# Static reference facts (from README "Frameworks & servers" / "Equal work,
# per test") -- used to render a per-report table filtered to just the
# frameworks that were actually part of this run.
FRAMEWORK_FACTS: dict[str, dict[str, str]] = {
    "jero": {
        "language": "Python 3.14",
        "server": "peregrine ASGI",
        "http_client": "lothc",
        "db_driver": "fastpg",
        "validates_body": "msgspec Struct",
        "parses_upstream": "typed (msgspec)",
        "serializer": "msgspec",
    },
    "fastapi": {
        "language": "Python 3.14",
        "server": "peregrine ASGI",
        "http_client": "lothc",
        "db_driver": "fastpg",
        "validates_body": "pydantic",
        "parses_upstream": "typed (pydantic) + response-model re-validate",
        "serializer": "pydantic",
    },
    "litestar": {
        "language": "Python 3.14",
        "server": "peregrine ASGI",
        "http_client": "lothc",
        "db_driver": "fastpg",
        "validates_body": "msgspec Struct",
        "parses_upstream": "typed (msgspec)",
        "serializer": "msgspec",
    },
    "blacksheep": {
        "language": "Python 3.14",
        "server": "peregrine ASGI",
        "http_client": "lothc",
        "db_driver": "fastpg",
        "validates_body": "pydantic (FromJSON)",
        "parses_upstream": "typed (pydantic)",
        "serializer": "stdlib json (BlackSheep default)",
    },
    "robyn": {
        "language": "Python 3.14",
        "server": "built-in Rust server",
        "http_client": "lothc",
        "db_driver": "fastpg",
        "validates_body": "pydantic (native param)",
        "parses_upstream": "typed (pydantic)",
        "serializer": "orjson (dicts) / pydantic",
    },
    "flask": {
        "language": "Python 3.14",
        "server": "peregrine WSGI",
        "http_client": "lothc (sync)",
        "db_driver": "psycopg",
        "validates_body": "pydantic",
        "parses_upstream": "typed (pydantic)",
        "serializer": "stdlib json",
    },
    "django-bolt": {
        "language": "Python 3.14",
        "server": "built-in Rust server",
        "http_client": "lothc",
        "db_driver": "fastpg",
        "validates_body": "msgspec Struct",
        "parses_upstream": "typed (msgspec) + response re-validate",
        "serializer": "msgspec",
    },
    "gin": {
        "language": "Go",
        "server": "net/http (GOMAXPROCS=1)",
        "http_client": "net/http",
        "db_driver": "pgx",
        "validates_body": "ShouldBindJSON struct",
        "parses_upstream": "typed struct",
        "serializer": "encoding/json",
    },
    "elysia": {
        "language": "Bun / TS",
        "server": "Bun native",
        "http_client": "fetch",
        "db_driver": "Bun SQL",
        "validates_body": "typebox schema",
        "parses_upstream": "passthrough object",
        "serializer": "Bun native",
    },
    "spring-boot": {
        "language": "Java 25",
        "server": "embedded Tomcat, virtual threads",
        "http_client": "RestClient (Apache HttpClient5)",
        "db_driver": "JdbcTemplate (HikariCP)",
        "validates_body": "jakarta bean validation (record)",
        "parses_upstream": "typed (Jackson)",
        "serializer": "Jackson",
    },
}


def _build_chart_svg(
    tests: list[str], results_by_test: dict[str, list[Result]], svg_path: Path
) -> None:
    """2x2 grid, one horizontal-bar panel per test, each panel scaled to its
    own fastest result -- jero highlighted in blue, everyone else in muted
    gray, matching jero's own bench-grid.svg."""
    import matplotlib as mpl

    mpl.use("svg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    bg, ink, subink, faint = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
    hilite, other = "#2a78d6", "#a8adb3"

    mpl.rcParams["font.family"] = "sans-serif"
    mpl.rcParams["font.sans-serif"] = [
        "Helvetica Neue",
        "Helvetica",
        "Arial",
        "DejaVu Sans",
        "sans-serif",
    ]
    mpl.rcParams["axes.unicode_minus"] = False

    # Fixed-size header (title + caption + legend) in inches, independent of
    # the panel-grid height below it -- keeping these in points/inches (never
    # axes-fraction) is what keeps the header a constant size as the number
    # of framework rows -- and therefore the figure height -- changes.
    header_in = 0.92
    footer_in = 0.16
    max_rows = max((len(v) for v in results_by_test.values()), default=1)
    fig_width = 12.6
    fig_height = header_in + footer_in + 1.05 * max_rows + 1.15
    fig, axes = plt.subplots(2, 2, figsize=(fig_width, fig_height), facecolor=bg)

    fig.text(
        0.026,
        0.988,
        "jero-benchmarks",
        fontsize=18,
        fontweight="bold",
        color=ink,
        ha="left",
        va="top",
    )
    fig.text(
        0.026,
        0.988 - 24 / (fig_height * 72),
        "Throughput (reqs/sec) · each panel ranked and scaled to its own fastest result",
        fontsize=10.5,
        color=subink,
        ha="left",
        va="top",
    )
    legend = fig.legend(
        handles=[
            Patch(facecolor=hilite, edgecolor="none", label="jero"),
            Patch(facecolor=other, edgecolor="none", label="others"),
        ],
        loc="upper right",
        bbox_to_anchor=(0.978, 0.985),
        frameon=False,
        ncol=2,
        handlelength=1.0,
        handleheight=1.0,
        handletextpad=0.5,
        columnspacing=1.4,
        fontsize=10.5,
    )
    for text, is_jero in zip(legend.get_texts(), (True, False), strict=True):
        text.set_color(ink if is_jero else subink)
        if is_jero:
            text.set_fontweight("bold")

    for ax, test in zip(axes.flat, tests[:4], strict=False):
        results = sorted(results_by_test.get(test, []), key=lambda r: r.reqs_per_sec, reverse=True)
        ax.set_facecolor(bg)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        if not results:
            ax.axis("off")
            continue

        max_val = results[0].reqs_per_sec or 1.0
        n = len(results)
        for i, r in enumerate(results):
            y = n - 1 - i
            is_jero = r.framework == "jero"
            color = hilite if is_jero else other
            weight = "bold" if is_jero else "normal"
            text_color = ink if is_jero else subink
            ax.plot([0, r.reqs_per_sec], [y, y], linewidth=12, solid_capstyle="round", color=color)
            ax.text(
                -max_val * 0.035,
                y,
                r.framework,
                ha="right",
                va="center",
                fontsize=10.5,
                color=text_color,
                fontweight=weight,
            )
            ax.text(
                r.reqs_per_sec + max_val * 0.035,
                y,
                _fmt_rps(r.reqs_per_sec),
                ha="left",
                va="center",
                fontsize=10,
                color=text_color,
                fontweight=weight,
            )
        ax.set_xlim(-max_val * 0.55, max_val * 1.3)
        ax.set_ylim(-0.75, n - 0.25)

        title, subtitle = TEST_HEADLINES.get(test, (test, ""))
        # Offsets in points (not axes-fraction) so the title/subtitle sit a
        # fixed distance above each panel regardless of that panel's height.
        ax.annotate(
            title,
            xy=(0.0, 1.0),
            xycoords="axes fraction",
            xytext=(0, 10),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=13,
            fontweight="bold",
            color=ink,
            annotation_clip=False,
        )
        ax.annotate(
            subtitle,
            xy=(1.0, 1.0),
            xycoords="axes fraction",
            xytext=(0, 13),
            textcoords="offset points",
            ha="right",
            va="bottom",
            fontsize=10,
            color=faint,
            annotation_clip=False,
        )

    top = 1 - header_in / fig_height
    bottom = footer_in / fig_height
    fig.tight_layout(rect=(0.018, bottom, 0.99, top), h_pad=3.2, w_pad=2.4)
    fig.savefig(svg_path, format="svg", facecolor=bg)
    plt.close(fig)


def _render_methodology(frameworks: list[str]) -> str:
    fact_cols = [
        ("Language", "language"),
        ("Server", "server"),
        ("HTTP client", "http_client"),
        ("DB driver", "db_driver"),
        ("Validates body (test 2)", "validates_body"),
        ("Parses upstream (test 3)", "parses_upstream"),
        ("JSON serializer", "serializer"),
    ]
    present = [fw for fw in frameworks if fw in FRAMEWORK_FACTS]
    fact_table_lines = []
    if present:
        fact_table_lines.append(f"| Framework | {' | '.join(c[0] for c in fact_cols)} |")
        fact_table_lines.append(f"| --- | {' | '.join('---' for _ in fact_cols)} |")
        for fw in present:
            facts = FRAMEWORK_FACTS[fw]
            fact_table_lines.append(
                f"| {fw} | {' | '.join(facts.get(key, '-') for _, key in fact_cols)} |"
            )
    fact_table = "\n".join(fact_table_lines)

    return f"""## How these results were made

**Isolation.** Exactly one framework container is ever alive at a time, alongside
the shared Postgres/upstream/load-generator infra -- brought up via `compose.base.yml`
plus that framework's own `compose.<fw>.yml`, torn down before the next framework
starts. No two frameworks ever share a core or contend for host resources.

**One worker, one core.** Every service runs exactly 1 worker (peregrine
`--workers 1`, Gin `GOMAXPROCS=1`, Bun's single JS thread, Bolt `--processes 1`),
pinned to one dedicated CPU core via `cpuset` affinity -- not a CFS quota, which
throttles a saturated container every 100ms scheduler period and adds
tail-latency stalls; affinity confines all of a framework's threads (including
GIL-releasing extensions like `msgspec`/`fastpg`) to one core with no such stalls.

**Equal resource budgets.** DB pool and outbound-HTTP pool are capped at **64**
connections for every framework/language.

**Load generator.** wrk (C) or oha (Rust), on two dedicated cores -- fast
enough that the framework, not the load generator, is what saturates.

**Best of N.** Each (framework, test) pair starts with an untimed 3s warm-up,
then runs multiple attempts; the attempt with the highest req/s is kept.

**Success %** is the share of requests that got the expected status. Before
the load, a correctness pass also checks the *body* of 100 responses (key
fields per test); if any is wrong, the whole test is reported as 0% success,
so a fast-but-wrong response can never pass as a success.

**Resource-use columns.** `memPk`/`memAv` = peak/average resident memory (MB);
`cpuAv`/`cpuPk` = average/peak CPU as % of one core (pinned via `cpuset`, so
these sit ≤100%); `cpu ~`/`mem ~` = a 0-to-max-scaled sparkline of the CPU/memory
time series during the attempt. Only the framework's own container is measured
-- Postgres and the upstream are excluded.

**Equal work, per test** -- every framework does the same task; only the
*native* tool differs:

{fact_table}

**One deliberate exception to per-framework idiom:** Django Bolt
reaches Postgres through raw fastpg -- the same driver the rest of the async
Python fleet uses -- rather than Django's ORM, whose sync-driver-behind-an-async-facade
design would make test 4 a measurement of Django's data layer instead of the
framework. For the same reason, every JWT endpoint hand-decodes the bearer
token with ryjwt rather than using each framework's own auth integration.

**Known, intended differences** (each framework's real idiomatic behaviour, kept
rather than normalised away): the JSON serializer column (stdlib `json` is
slower than msgspec/orjson/native); FastAPI and Django Bolt additionally
re-validate the *response* against its declared model (both frameworks'
default); Elysia returns the upstream payload parsed but unvalidated;
Spring Boot's Jackson binding coerces a numeric field given
as a JSON string rather than rejecting it like pydantic/msgspec do. These are
visible here so a number is never mistaken for pure framework speed."""


def _images_cell(results_by_test: dict[str, list[Result]]) -> str:
    """Every exact ECR image tag this run's results were produced on."""
    tags = {
        tag
        for results in results_by_test.values()
        for r in results
        for tag in (r.images or "").split()
    }
    return ", ".join(f"`{t}`" for t in sorted(tags)) or "-- (built on the host)"


def _render_report(
    run: Run,
    tests: list[str],
    results_by_test: dict[str, list[Result]],
    destination: str,
    svg_filename: str,
) -> str:
    frameworks = sorted({r.framework for results in results_by_test.values() for r in results})
    lines = [
        f"# jero-benchmarks — run `{run.run_id}`",
        "",
        f"_Generated {datetime.now(UTC).isoformat(timespec='seconds')}_",
        "",
        "## Run configuration",
        "",
        "| | |",
        "| --- | --- |",
        f"| **Run ID** | `{run.run_id}` |",
        f"| **Created** | {run.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')} |",
        f"| **Host** | {run.hostname or 'unknown'} |",
        f"| **AWS region** | {run.aws_region or '-- (not run on EC2)'} |",
        f"| **EC2 instance type** | {run.ec2_instance_type or '--'} |",
        f"| **EC2 AMI** | {f'`{run.ec2_ami_id}`' if run.ec2_ami_id else '--'} |",
        f"| **Images** | {_images_cell(results_by_test)} |",
        f"| **Load generator** | {run.loadgen or 'k6 (pre-dates this column)'} |",
        f"| **Connections** | {run.vus} |",
        f"| **Duration per attempt** | {run.duration} |",
        f"| **Best of** | {run.best_of} |",
        f"| **Server workers** | {run.workers} |",
        f"| **Python server** | {run.python_server or 'peregrine'} |",
        f"| **Event loop** | {run.loop or 'uvloop'} |",
        f"| **Frameworks** | {', '.join(frameworks)} |",
        f"| **Results backend** | {destination} |",
        "",
        "## Results",
        "",
        f"![jero-benchmarks results grid]({svg_filename})",
        "",
    ]
    for test in tests:
        results = results_by_test.get(test)
        if not results:
            continue
        lines += _render_markdown_table(test, results)
        lines.append("")

    lines.append(_render_methodology(frameworks))
    lines += [
        "",
        "## Disclosure",
        "",
        (
            "The author of this benchmark suite is also the author of "
            "[jero](https://pypi.org/project/jero/), one of the frameworks benchmarked "
            "here. Every measure above -- equal resource budgets, idiomatic code per "
            "framework, isolated single-framework runs, documented intended "
            "differences -- applies identically to jero and everyone else; nothing "
            "here is tuned in its favor."
        ),
        "",
        "---",
        f"_Generated by `export_results.py` from `results.is_best` rows in {destination}._",
    ]
    return "\n".join(lines)


def _run_to_dict(run: Run) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "created_at": run.created_at.isoformat(),
        "hostname": run.hostname,
        "vus": run.vus,
        "duration": run.duration,
        "best_of": run.best_of,
        "workers": run.workers,
        "python_server": run.python_server,
        "loadgen": run.loadgen,
        "ec2_ami_id": run.ec2_ami_id,
        "ec2_instance_type": run.ec2_instance_type,
        "aws_region": run.aws_region,
    }


def _result_to_dict(r: Result) -> dict[str, object]:
    return {
        "framework": r.framework,
        "test": r.test,
        "attempt": r.attempt,
        "reqs_per_sec": r.reqs_per_sec,
        "latency_avg_ms": r.latency_avg_ms,
        "latency_p50_ms": r.latency_p50_ms,
        "latency_p75_ms": r.latency_p75_ms,
        "latency_p90_ms": r.latency_p90_ms,
        "latency_p99_ms": r.latency_p99_ms,
        "failed_rate": r.failed_rate,
        "total_requests": r.total_requests,
        "is_best": r.is_best,
        "peak_rss_mb": r.peak_rss_mb,
        "avg_rss_mb": r.avg_rss_mb,
        "avg_cpu_pct": r.avg_cpu_pct,
        "peak_cpu_pct": r.peak_cpu_pct,
        "cpu_spark": r.cpu_spark,
        "mem_spark": r.mem_spark,
        "images": r.images,
    }


def _write_results_json(run: Run, all_results: list[Result], json_path: Path) -> None:
    """The raw data backing the report: every attempt of every (framework,
    test) pair in this run -- not just the is_best winners the markdown
    tables show -- so the best-of-N selection can be reprocessed or verified
    independently."""
    payload = {
        "run": _run_to_dict(run),
        "results": [_result_to_dict(r) for r in all_results],
    }
    json_path.write_text(json.dumps(payload, indent=2))


def _write_report(
    run: Run,
    tests: list[str],
    results_by_test: dict[str, list[Result]],
    all_results: list[Result],
    destination: str,
) -> Path:
    run_dir = ROOT / "reports" / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    svg_path = run_dir / "chart.svg"
    md_path = run_dir / "report.md"
    json_path = run_dir / "results.json"

    _build_chart_svg(tests, results_by_test, svg_path)
    md_path.write_text(_render_report(run, tests, results_by_test, destination, svg_path.name))
    _write_results_json(run, all_results, json_path)
    return md_path


def _pick_run(client: Tagly, runs_index_id: str, destination: str) -> str:
    """No run_id given: list the most recent runs with a single base36
    character label each (0-9, a-z — 36 max, so one keypress always
    identifies one) and prompt for a pick.

    Uses each run item's own TaglyDB metadata (id/createdAt/hostname tag)
    rather than fetching every run's full JSON data -- TaglyDB orders item
    listing by id ascending (creation order), which is what createdAt sorts
    by here too, so this needs one paginated metadata-only listing.
    """
    items = _list_all_items(client, runs_index_id)
    if not items:
        print(f"no runs found in {destination}", file=sys.stderr)
        raise SystemExit(1)
    items.sort(key=lambda it: it.created_at, reverse=True)
    recent = items[:36]
    recent.sort(key=lambda it: it.created_at)

    table = Table(title=f"runs in {destination}")
    table.add_column("#", style="bold cyan", justify="center")
    table.add_column("run_id", style="bold")
    table.add_column("host")
    table.add_column("created_at")
    for label, item in zip("0123456789abcdefghijklmnopqrstuvwxyz", recent, strict=False):
        table.add_row(
            label,
            item.key,
            item.tags.get("hostname") or "unknown host",
            item.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
    Console().print(table)

    choice = input("pick a run: ").strip().lower()
    index = "0123456789abcdefghijklmnopqrstuvwxyz".find(choice)
    if index < 0 or index >= len(recent):
        print(f"invalid pick: {choice!r}", file=sys.stderr)
        raise SystemExit(1)
    picked_key = recent[index].key
    assert picked_key is not None, "every runs-index item is always written with key=run_id"
    return picked_key


def main(run_id: str = "") -> None:
    settings = _get_settings()
    destination = "TaglyDB"

    with Tagly.build(
        base_url="https://api.taglydb.com", api_key=settings.taglydb_api_key
    ) as client:
        runs_index_id = _find_index(client, _RUNS_INDEX_KEY)
        if runs_index_id is None:
            print(f"no runs recorded yet in {destination}", file=sys.stderr)
            raise SystemExit(1)

        if not run_id:
            run_id = _pick_run(client, runs_index_id, destination)

        run = _fetch_run(client, runs_index_id, run_id)
        if run is None:
            print(f"no run {run_id!r} in {destination}", file=sys.stderr)
            recent = sorted(
                _list_all_items(client, runs_index_id), key=lambda it: it.created_at, reverse=True
            )[:10]
            if recent:
                print("most recent runs:", file=sys.stderr)
                for it in recent:
                    print(
                        f"  {it.key}  ({it.tags.get('hostname') or 'unknown host'})",
                        file=sys.stderr,
                    )
            raise SystemExit(1)

        print(
            f"jero-benchmarks · run {run.run_id} · host {run.hostname or 'unknown'} · "
            f"py:{run.python_server or 'peregrine'}/{run.loop or 'uvloop'} · "
            f"{run.loadgen or 'k6'} · {run.vus} connections · "
            f"{run.duration}/test · best-of-{run.best_of} · {run.workers} worker(s) · "
            f"results -> {destination}"
        )

        results_index_id = _find_index(client, _RESULTS_INDEX_KEY)
        all_results = _fetch_results(client, results_index_id, run_id) if results_index_id else []
        all_results.sort(key=lambda r: (r.framework, r.test, r.attempt))

        tests = sorted({r.test for r in all_results})
        results_by_test: dict[str, list[Result]] = {}
        for test in tests:
            results = sorted(
                (r for r in all_results if r.test == test and r.is_best),
                key=lambda r: r.reqs_per_sec,
                reverse=True,
            )
            if not results:
                continue
            results_by_test[test] = results
            print()
            for line in _render_table(test, results):
                print(line)

        if results_by_test:
            report_path = _write_report(run, tests, results_by_test, all_results, destination)
            print(f"\n==> wrote report to {report_path}")

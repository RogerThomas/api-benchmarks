#!yeet
"""Prints the comparison tables for one `task bench` run: one box table per
test, the best-of-N winner for each framework (Result.is_best), sorted by
req/s descending, with "vs" columns normalized against jero (the fleet's
baseline) — same shape the old table.awk produced, now reading
results/bench.db instead of a report-<ts>.json file.

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
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import peewee
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Results backend: Postgres (e.g. Neon) if PG_HOST is set in the
    environment/.env, else SQLite at SQLITE_PATH, else the local default.
    Same rule loadtest/run.py's Settings uses to pick a backend."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
    return Settings()


@cache
def _get_db() -> peewee.DatabaseProxy:
    return peewee.DatabaseProxy()


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
    return peewee.SqliteDatabase(settings.sqlite_path or str(ROOT / "results" / "bench.db"))


def _describe(settings: Settings) -> str:
    if settings.pg_host:
        return f"postgres://{settings.pg_host}/{settings.pg_db}"
    return settings.sqlite_path or str(ROOT / "results" / "bench.db")


class BaseModel(peewee.Model):
    class Meta:
        database = _get_db()


class Run(BaseModel):
    run_id = peewee.CharField(primary_key=True)
    created_at = peewee.DateTimeField()
    duration = peewee.CharField()
    vus = peewee.IntegerField()
    best_of = peewee.IntegerField()
    workers = peewee.IntegerField()
    python_server = peewee.CharField()
    loop = peewee.CharField(null=True)
    hostname = peewee.CharField(null=True)
    ec2_ami_id = peewee.CharField(null=True)
    ec2_instance_type = peewee.CharField(null=True)
    aws_region = peewee.CharField(null=True)

    class Meta:
        table_name = "runs"


class Result(BaseModel):
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
    is_best = peewee.BooleanField()
    peak_rss_mb = peewee.FloatField(null=True)
    avg_rss_mb = peewee.FloatField(null=True)
    avg_cpu_pct = peewee.FloatField(null=True)
    peak_cpu_pct = peewee.FloatField(null=True)
    cpu_spark = peewee.CharField(null=True)
    mem_spark = peewee.CharField(null=True)

    class Meta:
        table_name = "results"


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
        "language": "Python 3.13",
        "server": "granian ASGI",
        "http_client": "pyreqwest",
        "db_driver": "psqlpy",
        "validates_body": "msgspec Struct",
        "parses_upstream": "typed (msgspec)",
        "serializer": "msgspec",
    },
    "fastapi": {
        "language": "Python 3.13",
        "server": "granian ASGI",
        "http_client": "pyreqwest",
        "db_driver": "psqlpy",
        "validates_body": "pydantic",
        "parses_upstream": "typed (pydantic) + response-model re-validate",
        "serializer": "pydantic",
    },
    "litestar": {
        "language": "Python 3.13",
        "server": "granian ASGI",
        "http_client": "pyreqwest",
        "db_driver": "psqlpy",
        "validates_body": "msgspec Struct",
        "parses_upstream": "typed (msgspec)",
        "serializer": "msgspec",
    },
    "blacksheep": {
        "language": "Python 3.13",
        "server": "granian ASGI",
        "http_client": "pyreqwest",
        "db_driver": "psqlpy",
        "validates_body": "dataclass bind",
        "parses_upstream": "passthrough dict",
        "serializer": "orjson",
    },
    "robyn": {
        "language": "Python 3.13",
        "server": "built-in Rust server",
        "http_client": "pyreqwest",
        "db_driver": "psqlpy",
        "validates_body": "pydantic (native param)",
        "parses_upstream": "typed (pydantic)",
        "serializer": "stdlib json / pydantic",
    },
    "flask": {
        "language": "Python 3.13",
        "server": "granian WSGI",
        "http_client": "pyreqwest (sync)",
        "db_driver": "psycopg",
        "validates_body": "pydantic",
        "parses_upstream": "typed (pydantic)",
        "serializer": "stdlib json",
    },
    "django-ninja": {
        "language": "Python 3.13",
        "server": "granian ASGI",
        "http_client": "pyreqwest",
        "db_driver": "psqlpy",
        "validates_body": "pydantic (Schema)",
        "parses_upstream": "passthrough bytes",
        "serializer": "pydantic",
    },
    "django-bolt": {
        "language": "Python 3.13",
        "server": "built-in Rust server",
        "http_client": "pyreqwest",
        "db_driver": "psqlpy",
        "validates_body": "msgspec Struct",
        "parses_upstream": "passthrough bytes",
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
the shared Postgres/upstream/k6-runner infra -- brought up via `compose.base.yml`
plus that framework's own `compose.<fw>.yml`, torn down before the next framework
starts. No two frameworks ever share a core or contend for host resources.

**One worker, one core.** Every service runs exactly 1 worker (granian
`--workers 1`, Gin `GOMAXPROCS=1`, Bun's single JS thread, Bolt `--processes 1`),
pinned to one dedicated CPU core via `cpuset` affinity -- not a CFS quota, which
throttles a saturated container every 100ms scheduler period and adds
tail-latency stalls; affinity confines all of a framework's threads (including
GIL-releasing extensions like `msgspec`/`psqlpy`) to one core with no such stalls.

**Equal resource budgets.** DB pool and outbound-HTTP pool are capped at **64**
connections for every framework/language.

**Best of N.** Each (framework, test) pair runs multiple attempts; the
attempt with the highest req/s is kept.

**Resource-use columns.** `memPk`/`memAv` = peak/average resident memory (MB);
`cpuAv`/`cpuPk` = average/peak CPU as % of one core (pinned via `cpuset`, so
these sit ≤100%); `cpu ~`/`mem ~` = a 0-to-max-scaled sparkline of the CPU/memory
time series during the attempt. Only the framework's own container is measured
-- Postgres and the upstream are excluded.

**Equal work, per test** -- every framework does the same task; only the
*native* tool differs:

{fact_table}

**One deliberate exception to per-framework idiom:** the two Django frameworks
reach Postgres through raw psqlpy -- the same driver the rest of the async
Python fleet uses -- rather than Django's ORM, whose sync-driver-behind-an-async-facade
design would make test 4 a measurement of Django's data layer instead of the
framework. For the same reason, every JWT endpoint hand-decodes the bearer
token with PyJWT rather than using each framework's own auth integration.

**Known, intended differences** (each framework's real idiomatic behaviour, kept
rather than normalised away): the JSON serializer column (stdlib `json` is
slower than msgspec/orjson/native); FastAPI additionally re-validates the
*response* against its `response_model`; Blacksheep/Elysia/Django Ninja/Django
Bolt return the upstream payload straight through as bytes/dict; the two Django
frameworks return snake_case field names where the rest of the Python fleet
returns camelCase; Spring Boot's Jackson binding coerces a numeric field given
as a JSON string rather than rejecting it like pydantic/msgspec do. These are
visible here so a number is never mistaken for pure framework speed."""


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
        f"| **k6 VUs** | {run.vus} |",
        f"| **Duration per attempt** | {run.duration} |",
        f"| **Best of** | {run.best_of} |",
        f"| **Server workers** | {run.workers} |",
        f"| **Python server** | {run.python_server} |",
        f"| **Event loop** | {run.loop or 'uvloop (default, pre-dates this column)'} |",
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
    }


def _write_results_json(run: Run, json_path: Path) -> None:
    """The raw data backing the report: every attempt of every (framework,
    test) pair in this run -- not just the is_best winners the markdown
    tables show -- so the best-of-N selection can be reprocessed or verified
    independently."""
    all_results = list(
        Result
        .select()
        .where(Result.run == run.run_id)
        .order_by(Result.framework, Result.test, Result.attempt)
    )
    payload = {
        "run": _run_to_dict(run),
        "results": [_result_to_dict(r) for r in all_results],
    }
    json_path.write_text(json.dumps(payload, indent=2))


def _write_report(
    run: Run, tests: list[str], results_by_test: dict[str, list[Result]], destination: str
) -> Path:
    run_dir = ROOT / "reports" / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    svg_path = run_dir / "chart.svg"
    md_path = run_dir / "report.md"
    json_path = run_dir / "results.json"

    _build_chart_svg(tests, results_by_test, svg_path)
    md_path.write_text(_render_report(run, tests, results_by_test, destination, svg_path.name))
    _write_results_json(run, json_path)
    return md_path


def _pick_run(destination: str) -> str:
    """No run_id given: list the most recent runs with a single base36
    character label each (0-9, a-z — 36 max, so one keypress always
    identifies one) and prompt for a pick."""
    # Fetch the 36 most recent so a busy DB doesn't bury today's runs under
    # old ones, then re-sort that set oldest to newest for display.
    runs = list(Run.select().order_by(Run.created_at.desc()).limit(36))
    if not runs:
        print(f"no runs found in {destination}", file=sys.stderr)
        raise SystemExit(1)
    runs.sort(key=lambda r: r.created_at)

    table = Table(title=f"runs in {destination}")
    table.add_column("#", style="bold cyan", justify="center")
    table.add_column("run_id", style="bold")
    table.add_column("host")
    table.add_column("created_at")
    for label, run in zip("0123456789abcdefghijklmnopqrstuvwxyz", runs, strict=False):
        table.add_row(
            label,
            run.run_id,
            run.hostname or "unknown host",
            run.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
    Console().print(table)

    choice = input("pick a run: ").strip().lower()
    index = "0123456789abcdefghijklmnopqrstuvwxyz".find(choice)
    if index < 0 or index >= len(runs):
        print(f"invalid pick: {choice!r}", file=sys.stderr)
        raise SystemExit(1)
    return runs[index].run_id


def main(run_id: str = "") -> None:
    settings = _get_settings()
    destination = _describe(settings)
    if not settings.pg_host and not Path(destination).exists():
        print(f"no results database at {destination}", file=sys.stderr)
        raise SystemExit(1)

    db = _get_db()
    db.initialize(_build_db(settings))
    db.connect()

    if not run_id:
        run_id = _pick_run(destination)

    run = Run.get_or_none(Run.run_id == run_id)
    if run is None:
        print(f"no run {run_id!r} in {destination}", file=sys.stderr)
        recent = list(Run.select().order_by(Run.created_at.desc()).limit(10))
        if recent:
            print("most recent runs:", file=sys.stderr)
            for r in recent:
                print(f"  {r.run_id}  ({r.hostname or 'unknown host'})", file=sys.stderr)
        raise SystemExit(1)

    print(
        f"jero-benchmarks · run {run.run_id} · host {run.hostname or 'unknown'} · "
        f"py:{run.python_server}/{run.loop or 'uvloop'} · {run.vus} VUs · {run.duration}/test · "
        f"best-of-{run.best_of} · {run.workers} worker(s) · results -> {destination}"
    )

    tests = [
        r.test
        for r in Result
        .select(Result.test)
        .where(Result.run == run_id)
        .distinct()
        .order_by(Result.test)
    ]
    results_by_test: dict[str, list[Result]] = {}
    for test in tests:
        results = list(
            Result
            .select()
            .where((Result.run == run_id) & (Result.test == test) & (Result.is_best == True))  # noqa: E712
            .order_by(Result.reqs_per_sec.desc())
        )
        if not results:
            continue
        results_by_test[test] = results
        print()
        for line in _render_table(test, results):
            print(line)

    if results_by_test:
        report_path = _write_report(run, tests, results_by_test, destination)
        print(f"\n==> wrote report to {report_path}")

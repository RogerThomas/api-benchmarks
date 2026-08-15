# jero-benchmarks

Benchmarks comparing API frameworks using **idiomatic, framework-recommended code**
(no deep optimisations). The question: *how fast is each framework under best practices?*

Everything runs inside docker. Frameworks are benched **one at a time** — for a given
run, exactly one framework container is ever alive alongside the dependent services
(Postgres, the upstream, the k6 runner), so no two frameworks ever share a core or
contend for host resources.

> **Disclosure**: I'm also the author of [jero](https://pypi.org/project/jero/), one of
> the frameworks benchmarked here. Every measure in this repo — equal resource budgets,
> idiomatic code per framework, isolated single-framework runs, documented intended
> differences — applies identically to jero and everyone else; nothing here is tuned in
> its favor. Judge the methodology, not my word for it, and open an issue/PR if you spot
> a framework being shortchanged.

## Run

```bash
task bench                                     # every framework, one at a time, best-of-3
task bench -- --frameworks "jero fastapi"      # just these two, still one at a time
task bench -- --duration 30s --vus 200         # override k6 knobs (see: uv run yeet ./bench.py --help)
task export-results -- 20260813T120000         # re-print a past run's tables
```

`task bench` (`bench.py`) generates one **RUN_ID** — the kickoff timestamp — and, for
each name in `--frameworks`, brings up `compose.base.yml` (Postgres + the upstream + the
k6 runner) plus that framework's own `compose.<fw>.yml`, waits for the runner to finish
every test, tears the pair back down, then moves to the next framework. Every
framework's results land in `results/bench.db` (SQLite) tagged with the shared RUN_ID —
that's what ties a multi-framework run together. At the end, `bench.py` hands off to
`export_results.py` to print the comparison tables and write a full report — tables, a
chart SVG, exact run config (VUs/duration/AMI/region if run on EC2), and the methodology
— to `reports/<run_id>.md`; re-run it standalone any time with a past RUN_ID via
`task export-results`.

All knobs are CLI flags only (no env-var fallback) — run `uv run yeet ./bench.py --help`
for the full list.

### Best of N

Every (framework, test) pair runs `RUNS` times (default **3**) and the best attempt is
kept — smoothing out noise. "Best" is the highest composite score, equally weighting
throughput and latency, each metric normalized against the best of that test's attempts:

```
score = reqsPerSec/maxReqs  +  minMean/mean  +  minP99/p99
```

so higher reqs/s and lower mean & p99 all push the score up (each term ∈ (0, 1]). The
chosen attempt is what the comparison tables use; every attempt is still in
`results/bench.db` (`results.is_best` marks the winner) for transparency.

Other knobs (CLI flags — see `uv run yeet ./bench.py --help`): `--vus` (k6 concurrency,
default 100), `--runs` (attempts per test, default 3), `--workers` (server workers per
service, default 1), `--python-server` (`granian` default, or `uvicorn`),
`--frameworks`, `--tests`.

Each framework is pinned to **one dedicated CPU core / 2 GB** (compose `cpuset`); the
infra (Postgres, upstream, k6 runner) runs on other cores. Since only one framework is
ever alive at a time, every framework gets the *same* core — there's no cross-framework
contention to pin apart (see Fairness).

At the end of a run it prints one table per test — throughput, latency, success rate,
and per-container resource use (CPU/mem + sparklines), rows sorted by req/s with
vs-jero multipliers — and every attempt is recorded in `results/bench.db`. See
`results/FINAL-*.md` for examples of the format from earlier (pre-SQLite) runs; a
trimmed row looks like:

```
1 - GET /info
│ Framework │ req/s  │ vs    │ mean   │ vs    │ p99    │ vs    │ succ%  │ memPk │ cpuAv │ cpu ~            │
│ gin       │ ~54.6k │ x1.13 │ 1.78ms │ x1.14 │ 9.23ms │ x1.04 │ 100.00 │ 14M   │ 71%   │ ▇▇▇▇████████████ │
│ jero      │ ~48.3k │ x1.00 │ 2.03ms │ x1.00 │ 9.60ms │ x1.00 │ 100.00 │ 91M   │ 90%   │ ████████████████ │
```

## Frameworks & servers

| Framework | Language | Server (1 worker) | Outbound HTTP client | DB driver |
| --- | --- | --- | --- | --- |
| jero, FastAPI, Litestar, Blacksheep | Python 3.13 | granian ASGI (`--loop uvloop`) | pyreqwest | psqlpy |
| Django Ninja | Python 3.13 | granian ASGI | pyreqwest | psycopg (Django ORM) |
| Flask | Python 3.13 | granian WSGI | pyreqwest (sync) | psycopg |
| Robyn | Python 3.13 | built-in Rust server | pyreqwest | psqlpy |
| Django Bolt | Python 3.13 | built-in Rust server (`manage.py runbolt`) | pyreqwest | psycopg (Django ORM) |
| Gin | Go | net/http (`GOMAXPROCS=1`) | net/http | pgx |
| Elysia | Bun / TS | Bun native | `fetch` | Bun `SQL` |
| Spring Boot | Java 25 | embedded Tomcat, virtual threads | RestClient (Apache HttpClient5) | JdbcTemplate (HikariCP) |

All apps use idiomatic, framework-recommended code (no deep optimisations). The Python
ASGI frameworks share granian as the server so the variable under test is the
*framework*, not the server (switch to uvicorn with `--python-server uvicorn` — Robyn and
Django Bolt ship their own servers and ignore this knob). The two Django frameworks use
Django's ORM (an unmanaged model over the same shared `users` table) rather than a raw
driver — the idiomatic Django data-access pattern, and a real, visible difference from
the rest of the fleet.

The whole Python field runs **Python 3.13.14** (pinned base image) so **Robyn** — which
has no `manylinux_aarch64` (Linux/arm64) wheel for CPython 3.14 yet, only for 3.13 —
runs natively rather than emulated. (Checked 2026-08-10: Robyn 0.88.0 ships a cp314
wheel for macOS and manylinux x86_64, but still not aarch64 Linux.) Once that wheel
lands, bump the base image back to 3.14.

## Tests

1. **GET /info** — medium JSON (8 fields, varying types) + a custom `x-response-id` UUID header.
2. **POST /movies** — JWT-authenticated; validates a 5-field body, returns the movie with a
   UUID `id` and the authenticated `user`.
3. **GET /catalog** — fetches a static JSON payload from the fast Rust (axum) `upstream`
   service and returns it. Public endpoint; the service-to-service call carries a bearer
   API key the upstream verifies. With every Python framework on the same Rust HTTP
   client (pyreqwest), this test differentiates *frameworks* — historically, a pure-Python
   client (niquests) capped everyone at ~3k req/s and masked the framework entirely.
4. **GET /users/me** — JWT-authenticated; id from the token, the rest from a Postgres
   `users` row.

Every JWT-authenticated endpoint (test 2, test 4) decodes the same `Authorization:
Bearer <token>` header by hand with PyJWT — including the two Django frameworks, whose
own JWT integrations (django-ninja-jwt's cookie auth, Bolt's `JWTAuthentication` tied to
`django.contrib.auth.User`) would each be doing different work than the rest of the fleet.

## Fairness & methodology

The goal is *idiomatic per framework*, held to equal conditions and made scrutable.

- **One framework alive at a time.** `task bench` runs each framework in its own
  `docker compose` invocation (`compose.base.yml` + that framework's `compose.<fw>.yml`),
  torn down before the next one starts. Every framework gets an identical,
  contention-free environment — the same core, the same otherwise-idle host — so
  absolute numbers are comparable both within a run *and* across separate runs, so long
  as the host itself is otherwise idle. (Earlier versions of this benchmark ran the full
  fleet concurrently, each pinned to its own core; that measures *"the framework under
  fleet-wide contention,"* a different and reasonable question, but not what this repo
  now measures — see `results/FINAL-*.md` for that era's numbers, which aren't directly
  comparable to newer isolated runs.)
- **One worker each.** Every service runs 1 worker: granian `--workers 1`, Gin
  `GOMAXPROCS=1`, Bun's single JS thread, Bolt `--processes 1`. Flask is synchronous
  (granian WSGI, `--blocking-threads 1`). A thread sweep (1/2/4/8) confirmed **1 is
  fastest on every test — including the I/O-bound ones**: on a single capped core the
  GIL + thread scheduling swamp any I/O-overlap benefit, so more threads only add
  overhead and memory. Flask trailing on I/O is the honest cost of the sync model on one
  core, not a handicap we imposed. (granian's *default* pool is worse still — it sizes
  to host cores, ignoring the single-core pin, and thrashes.)
- **One *core* each — `cpuset` affinity.** `WORKERS=1` bounds worker *processes*, not
  threads: granian's Rust HTTP runtime and GIL-releasing extensions (`msgspec`, the
  `psqlpy`/`psycopg` drivers) run on their own threads and would otherwise spread across
  cores. Each framework is pinned to a single core, which confines all its threads to
  one core — the honest apples-to-apples cap. We use affinity (`cpuset`) rather than a
  CFS quota (`cpus: "1"`) deliberately: a quota *throttles* a saturated multi-threaded
  container at each 100 ms scheduler period, adding tens-of-ms stalls to P99; affinity
  just says "run only here," so the tail stays clean. Infra (Postgres, upstream, k6
  runner) gets its own separate cores so it never bottlenecks the framework under test.
  **Caveat on Apple Silicon (Docker Desktop on Mac):** `cpuset` pins a container to a
  *virtual* CPU number inside the Linux VM — it does not choose which physical core that
  vCPU runs on. Apple Silicon's performance/efficiency cores are heterogeneous, and
  macOS's own hypervisor scheduler (not Linux, not cpuset) decides which physical core a
  given vCPU lands on at any moment — it can migrate between a P-core and an E-core run
  to run. So "every framework pinned to cpuset 0" does not guarantee identical silicon
  across frameworks or even across repeated attempts of the same one. This is exact only
  on bare-metal Linux with uniform cores; on Apple Silicon it's a real, unresolved source
  of noise, not something this harness currently controls for.
- **Equal resource budgets.** DB pool and outbound-HTTP pool are **64** for every
  framework/language (Python/Django `db_pool_size`, Gin `pgx MaxConns` +
  `MaxConnsPerHost`, Bun `SQL max` + `BUN_CONFIG_MAX_HTTP_REQUESTS=64`). The Bun fetch
  cap matters beyond parity: Bun keeps a 64-connection keep-alive pool per host but does
  **not** queue overflow — beyond 64 concurrent fetches it opens one-shot connections
  that flood TIME_WAIT and exhaust the container's ephemeral ports (~28k) within
  seconds, collapsing the proxy test under sustained load. Capped, Bun queues like the
  others.
- **Equal work, per test** — every framework does the same task; only the *native* tool
  differs (documented below):

  | | Validates body (test 2) | Parses upstream (test 3) | JSON serializer |
  | --- | --- | --- | --- |
  | jero | msgspec Struct | typed (msgspec) | msgspec |
  | FastAPI | pydantic | typed (pydantic) + response-model re-validate | pydantic |
  | Litestar | msgspec Struct | typed (msgspec) | msgspec |
  | Blacksheep | dataclass bind | passthrough dict | orjson |
  | Robyn | pydantic (native param) | typed (pydantic) | stdlib `json` / pydantic |
  | Flask | pydantic | typed (pydantic) | stdlib `json` |
  | Django Ninja | pydantic (Schema) | passthrough bytes | pydantic |
  | Django Bolt | msgspec Struct | passthrough bytes | msgspec |
  | Gin | `ShouldBindJSON` struct | typed struct | `encoding/json` |
  | Elysia | typebox schema | passthrough object | Bun native |
  | Spring Boot | jakarta bean validation (record) | typed (Jackson) | Jackson |

  **Known, intended differences** (each framework's real idiomatic behaviour — kept, not
  normalised away): the JSON **serializer** column (stdlib json is slower than
  msgspec/orjson/native — relevant for Flask); **FastAPI** additionally re-validates the
  *response* against its `response_model`; Blacksheep/Elysia/Django Ninja/Django Bolt
  return the upstream payload straight through as bytes/dict rather than a typed model;
  and the two Django frameworks return **snake_case** field names (pydantic's/msgspec's
  default) where the other Python frameworks return camelCase; **Spring Boot**'s Jackson
  binding coerces a numeric field given as a JSON string (e.g. `"year": "2020"`) rather
  than rejecting it like pydantic/msgspec do. These are visible here so a number is never
  mistaken for pure framework speed.

### Resource use (CPU / memory)

Each run also records what the framework *cost* to hit its numbers: during every k6
attempt the runner polls `docker stats` (cgroup accounting) on the framework's container.
The report shows, per framework × test:

| column | meaning |
| --- | --- |
| `memPk` / `memAv` | peak / average resident memory (MB) |
| `cpuAv` / `cpuPk` | average / peak CPU, as **% of one core** |
| `cpu ~` / `mem ~` | Unicode sparkline of the CPU / memory time series (0-to-max scaled) |

Only the framework's own container is measured — **Postgres and the upstream are
excluded**, so you see each framework's own cost.

> Because every framework is pinned to one core (`cpuset`), `cpuAv`/`cpuPk` sit **≤100%**
> (one core). Near 100% means the test is CPU-bound on its core; lower means it's I/O-bound
> (e.g. test 3, waiting on the upstream). Read it alongside throughput as *what one core
> actually delivers*. (`docker stats` needs ~1–2s per sample, so runs shorter than a few
> seconds yield too few CPU samples to be meaningful — use `-s 5`+ for the CPU columns.)

## HTTP client shootout

A separate, standalone benchmark: which Python HTTP client is fastest for the outbound
call every framework makes in test 3? One core vs the `upstream` service, sequential
then concurrent, pyreqwest vs httpx2 vs aiohttp vs niquests.

```bash
task bench-http-clients                 # 10s/client, concurrency 64
task bench-http-clients -- -d 20 -c 128 # override duration / concurrency
```

Builds and tears down its own stack (`compose.http-clients.yml`) — unrelated to `task bench`.

## Layout

```
compose.base.yml          # Postgres + upstream + k6 runner (shared, no framework)
compose.<fw>.yml          # one framework's service + its runner depends_on/env
                           #   combine as: docker compose -f compose.base.yml -f compose.<fw>.yml up ...
compose.http-clients.yml  # standalone: outbound HTTP client shootout (task bench-http-clients)
bench.py                  # host orchestrator: loops --frameworks, one compose pair at a time
export_results.py         # host script: prints the comparison tables for a past RUN_ID
pyproject.toml            # host-side deps for bench.py/export_results.py (yeetr, peewee)
Taskfile.yml              # `task bench` / `task export-results` / `task bench-http-clients`
services/python/          # all Python frameworks: ONE pyproject, group per framework
  pyproject.toml          #   [dependency-groups] jero = [...], fastapi = [...], ...
  Dockerfile               #   multi-stage: one stage per framework, isolated venvs
  apps/<fw>_app.py         #   one app module per single-file framework
  django_app/               #   shared Django project: Ninja + Bolt variants
  manage.py                 #   only needed to launch Bolt (`runbolt`)
services/gin/              # Go / Gin service (multi-stage build)
services/elysia/           # Bun / Elysia service
services/spring-boot/      # Java / Spring Boot service (multi-stage Maven build)
services/upstream/         # fast Rust (axum) static-JSON upstream for test 3
services/http-clients/     # one-core shootout comparing outbound Python HTTP clients
loadtest/                  # k6 + orchestration image (one framework per container run)
  scenarios/testN.js       #   one script per test
  lib/common.js            #   shared options, JWT minting, summary -> per-attempt JSON
  run.py                   #   loops TESTS x RUNS for one framework, writes results/bench.db
  pyproject.toml           #   in-container deps (peewee)
results/
  bench.db                 # SQLite: every run's every attempt (git-ignored)
reports/
  <run_id>.md               # full report: tables, chart, exact run config, methodology
  <run_id>.svg               # the chart embedded in that report
```

## Adding a Python framework

1. Add a `[dependency-groups]` entry in `services/python/pyproject.toml`.
2. Add an app module `services/python/apps/<fw>_app.py` (or, for a Django-based
   framework, wire it into `services/python/django_app/`).
3. Add a stage to `services/python/Dockerfile` (`FROM base AS <fw>` →
   `uv sync --no-default-groups --group <fw>`).
4. Add `compose.<fw>.yml` (copy an existing one — e.g. `compose.jero.yml` — and swap the
   build target, service name, and any framework-specific env).
5. Bench it with `task bench -- --frameworks "... <fw>"`.

Non-Python frameworks (Go/Gin, Bun/Elysia, Java/Spring Boot) have their own `services/<fw>/` dir + Dockerfile.

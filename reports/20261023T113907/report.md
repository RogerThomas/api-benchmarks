# jero-benchmarks — run `20261023T113907`

_Generated 2026-10-23T12:10:24+00:00_

## Run configuration

| | |
| --- | --- |
| **Run ID** | `20261023T113907` |
| **Created** | 2026-10-23 11:42:28 UTC |
| **Host** | ip-172-31-21-168.eu-central-1.compute.internal |
| **AWS region** | eu-central-1 |
| **EC2 instance type** | c9g.2xlarge |
| **EC2 AMI** | `ami-0f7d895aa37851cb2` |
| **Images** | `blacksheep-2026.10.23.03`, `django-bolt-2026.10.23.03`, `fastapi-2026.10.23.03`, `flask-2026.10.23.03`, `jero-2026.10.23.03`, `litestar-2026.10.23.03`, `postgres-2026.10.23.01`, `robyn-2026.10.23.03`, `runner-2026.10.23.02`, `upstream-2026.10.23.01` |
| **Load generator** | wrk |
| **Connections** | 128 |
| **Duration per attempt** | 60s |
| **Best of** | 3 |
| **Server workers** | 1 |
| **Python server** | peregrine |
| **Event loop** | uvloop |
| **Frameworks** | blacksheep, django-bolt, fastapi, flask, jero, litestar, robyn |
| **Results backend** | TaglyDB |

## Results

![jero-benchmarks results grid](chart.svg)

### 1 - GET /info

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero | ~100.4k | x1.00 | 1.27ms | x1.00 | 1.31ms | x1.00 | 100.00 | 50M | 50M | 100% | 102% | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| django-bolt | ~95.7k | x0.95 | 1.33ms | x0.95 | 1.36ms | x0.96 | 100.00 | 74M | 73M | 98% | 103% | ▇▇▇█▇▇▇▇▇▇▇▇▇▇▇▄ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| blacksheep | ~73.6k | x0.73 | 1.73ms | x0.73 | 1.78ms | x0.74 | 100.00 | 52M | 52M | 100% | 103% | ▇▇▇▇▇▇▇▇▇█▇▇▇▇▇▇ | ▇▇▇▇▇▇▇▇█▇▇▇▇▇▇▇ |
| litestar | ~48.9k | x0.49 | 2.60ms | x0.49 | 2.66ms | x0.49 | 100.00 | 61M | 61M | 97% | 102% | ▇▇█▇▇▇▇▇▇▇▇▇▇▇▇▄ | ▇█▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| robyn | ~43.4k | x0.43 | 2.95ms | x0.43 | 3.08ms | x0.43 | 100.00 | 40M | 40M | 101% | 102% | ▇▇▇█▇▇▇▇▇▇▇▇▇▇▇▇ | ▇▇█▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| fastapi | ~30.6k | x0.30 | 4.17ms | x0.30 | 4.22ms | x0.31 | 100.00 | 58M | 58M | 100% | 101% | ▇▇▇▇▇▇▇▇█▇▇▇▇▇▇▇ | ▇▇▇▇█▇▇▇▇▇▇▇▇▇▇▇ |
| flask | ~27.3k | x0.27 | 4.69ms | x0.27 | 4.80ms | x0.27 | 100.00 | 62M | 62M | 97% | 102% | ▇▇▇▇█▇▇▇▇▇▇▇▇▇▇▄ | ████▇▇▇▇▇▇▇▇▇▇▇▇ |

### 2 - POST /movies (JWT)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| django-bolt | ~83.1k | x1.00 | 1.54ms | x1.00 | 1.57ms | x1.01 | 100.00 | 74M | 74M | 101% | 103% | ▇▇▇█▇▇▇▇▇▇▇▇▇▇▇▇ | ▇▇▇▇▇▇▇▇█▇▇▇▇▇▇▇ |
| jero | ~83.0k | x1.00 | 1.53ms | x1.00 | 1.59ms | x1.00 | 100.00 | 51M | 50M | 100% | 105% | ▇▇▇▇▇▇▇▇▇█▇▇▇▇▇▇ | ▇▇▇█▇▇▇▇▇▇▇▇▇▇▇▇ |
| blacksheep | ~33.1k | x0.40 | 3.85ms | x0.40 | 3.91ms | x0.41 | 100.00 | 53M | 53M | 100% | 101% | ▇▇█▇▇▇▇▇▇▇▇▇▇▇▇▇ | ▇█▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| litestar | ~29.9k | x0.36 | 4.27ms | x0.36 | 4.34ms | x0.37 | 100.00 | 62M | 61M | 97% | 102% | ▇▇█▇▇▇▇▇▇▇▇▇▇▇▇▄ | ▇▇▇▇█▇▇▇▇▇▇▇▇▇▇▇ |
| robyn | ~26.4k | x0.32 | 4.83ms | x0.32 | 4.93ms | x0.32 | 100.00 | 41M | 41M | 97% | 101% | ▇▇▇▇▇▇▇▇▇▇▇▇█▇▇▄ | ▇▇█▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| flask | ~20.2k | x0.24 | 6.34ms | x0.24 | 6.48ms | x0.24 | 100.00 | 63M | 63M | 97% | 101% | ▇▇▇▇█▇▇▇▇▇▇▇▇▇▇▄ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| fastapi | ~18.5k | x0.22 | 6.89ms | x0.22 | 6.96ms | x0.23 | 100.00 | 59M | 58M | 100% | 101% | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |

### 3 - GET proxy (upstream)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero | ~30.3k | x1.00 | 4.23ms | x1.00 | 7.19ms | x1.00 | 100.00 | 67M | 64M | 97% | 102% | ▇▇▇▇█▇▇▇▇▇▇▇▇▇▇▄ | ▇█▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| django-bolt | ~23.4k | x0.77 | 5.52ms | x0.77 | 13.09ms | x0.55 | 100.00 | 101M | 100M | 101% | 102% | ▇▇▇▇▇▇▇▇█▇▇▇▇▇▇▇ | ▇▇█▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| blacksheep | ~20.7k | x0.68 | 6.20ms | x0.68 | 11.61ms | x0.62 | 100.00 | 68M | 66M | 97% | 102% | ▇▇▇▇▇▇▇▇▇▇█▇▇▇▇▄ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| litestar | ~18.2k | x0.60 | 7.06ms | x0.60 | 17.32ms | x0.42 | 100.00 | 75M | 75M | 101% | 102% | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ | ▇▇▇▇▇▇▇▇▇█▇▇▇▇▇▇ |
| robyn | ~17.9k | x0.59 | 7.15ms | x0.59 | 10.89ms | x0.66 | 100.00 | 67M | 66M | 101% | 101% | ▇▇▇▇▇▇▇▇▇▇█▇▇▇▇▇ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| fastapi | ~12.2k | x0.40 | 10.45ms | x0.41 | 20.04ms | x0.36 | 100.00 | 74M | 73M | 100% | 102% | ▇▇▇▇▇▇█▇▇▇▇▇▇▇▇▇ | ▇▇▇█▇▇▇▇▇▇▇▇▇▇▇▇ |
| flask | ~11.2k | x0.37 | 11.35ms | x0.37 | 12.05ms | x0.60 | 100.00 | 64M | 64M | 90% | 94% | ▇▇▇▇▇▇▇▇█▇▇▇▇▇▇▄ | ▇▇▇▇▇█▇▇▇▇▇▇▇▇▇▇ |

### 4 - GET /users/me (DB)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero | ~46.9k | x1.00 | 2.72ms | x1.00 | 3.26ms | x1.00 | 100.00 | 66M | 65M | 101% | 103% | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| django-bolt | ~36.4k | x0.78 | 3.51ms | x0.78 | 4.18ms | x0.78 | 100.00 | 107M | 106M | 96% | 106% | ▇▇▇▇█▇▇▇▇▇▇▇▇▇▇▄ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| blacksheep | ~28.7k | x0.61 | 4.47ms | x0.61 | 6.71ms | x0.49 | 100.00 | 69M | 69M | 97% | 103% | ▇▇▇█▇▇▇▇▇▇▇▇▇▇▇▄ | ▇▇▇█▇▇▇▇▇▇▇▇▇▇▇▇ |
| robyn | ~22.4k | x0.48 | 5.71ms | x0.48 | 8.62ms | x0.38 | 100.00 | 70M | 70M | 98% | 102% | ▇▇▇▇▇▇▇▇▇▇▇▇▇▇█▄ | ▇▇█▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| litestar | ~21.9k | x0.47 | 5.87ms | x0.46 | 10.37ms | x0.31 | 100.00 | 77M | 76M | 101% | 103% | ▇▇▇▇█▇▇▇▇▇▇▇▇▇▇▇ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| fastapi | ~14.0k | x0.30 | 9.11ms | x0.30 | 18.28ms | x0.18 | 100.00 | 77M | 76M | 100% | 102% | ▇█▇▇▇▇▇▇▇▇▇▇▇▇▇▇ | ▇█▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| flask | ~8.8k | x0.19 | 14.53ms | x0.19 | 16.05ms | x0.20 | 100.00 | 63M | 63M | 79% | 79% | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ | █▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |

## How these results were made

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

| Framework | Language | Server | HTTP client | DB driver | Validates body (test 2) | Parses upstream (test 3) | JSON serializer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| blacksheep | Python 3.14 | peregrine ASGI | lothc | fastpg | pydantic (FromJSON) | typed (pydantic) | stdlib json (BlackSheep default) |
| django-bolt | Python 3.14 | built-in Rust server | lothc | fastpg | msgspec Struct | typed (msgspec) + response re-validate | msgspec |
| fastapi | Python 3.14 | peregrine ASGI | lothc | fastpg | pydantic | typed (pydantic) + response-model re-validate | pydantic |
| flask | Python 3.14 | peregrine WSGI | lothc (sync) | psycopg | pydantic | typed (pydantic) | stdlib json |
| jero | Python 3.14 | peregrine ASGI | lothc | fastpg | msgspec Struct | typed (msgspec) | msgspec |
| litestar | Python 3.14 | peregrine ASGI | lothc | fastpg | msgspec Struct | typed (msgspec) | msgspec |
| robyn | Python 3.14 | built-in Rust server | lothc | fastpg | pydantic (native param) | typed (pydantic) | orjson (dicts) / pydantic |

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
visible here so a number is never mistaken for pure framework speed.

## Disclosure

The author of this benchmark suite is also the author of [jero](https://pypi.org/project/jero/), one of the frameworks benchmarked here. Every measure above -- equal resource budgets, idiomatic code per framework, isolated single-framework runs, documented intended differences -- applies identically to jero and everyone else; nothing here is tuned in its favor.

---
_Generated by `export_results.py` from `results.is_best` rows in TaglyDB._
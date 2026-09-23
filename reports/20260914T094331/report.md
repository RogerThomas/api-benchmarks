# jero-benchmarks — run `20260914T094331`

_Generated 2026-09-14T10:27:16+00:00_

## Run configuration

| | |
| --- | --- |
| **Run ID** | `20260914T094331` |
| **Created** | 2026-09-14 09:44:55 UTC |
| **Host** | ip-172-31-24-36.eu-central-1.compute.internal |
| **AWS region** | eu-central-1 |
| **EC2 instance type** | c9g.2xlarge |
| **EC2 AMI** | `ami-0f7d895aa37851cb2` |
| **k6 VUs** | 128 |
| **Duration per attempt** | 15s |
| **Best of** | 3 |
| **Server workers** | 1 |
| **Python server** | granian |
| **Event loop** | uvloop |
| **Frameworks** | blacksheep, django-bolt, django-ninja, elysia, fastapi, flask, gin, jero, litestar, robyn, spring-boot |
| **Results backend** | mr-blobby |

## Results

![jero-benchmarks results grid](chart.svg)

### 1 - GET /info

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gin | ~49.7k | x1.09 | 2.44ms | x1.12 | 12.19ms | x1.09 | 100.00 | 12M | 11M | 63% | 68% | ▆▆▇▇▇▇▇▇▇▇▇▇▇▇██ | ▇▇▇▇██▇▇▇▇▇▇▇▇▇▇ |
| elysia | ~49.6k | x1.09 | 2.43ms | x1.12 | 11.83ms | x1.12 | 100.00 | 27M | 23M | 49% | 53% | ▆▆▇▇▇▇▇▇▇▇▇▇██▇▇ | ▆▆▇▇██▆▆▆▆▆▆▆▆▆▆ |
| django-bolt | ~49.5k | x1.09 | 2.47ms | x1.10 | 12.16ms | x1.09 | 100.00 | 94M | 84M | 69% | 82% | ▇▇▇▇▇▇▇▇▇▇▇▇██▁▁ | ▇▇▇▇██▇▇▇▇▇▇▇▇▇▇ |
| jero | ~45.5k | x1.00 | 2.72ms | x1.00 | 13.30ms | x1.00 | 100.00 | 80M | 78M | 74% | 93% | ▄▄▇▇▇▇▇▇▇▇▇▇▇██▁ | ▇▇██▇▇▇▇▇▇▇▇▇▇▇▇ |
| blacksheep | ~40.0k | x0.88 | 3.13ms | x0.87 | 13.24ms | x1.00 | 100.00 | 71M | 71M | 84% | 94% | ▇▇▇▇▇▇▇▇██▇▇▇▇▂▂ | ██▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| spring-boot | ~37.2k | x0.82 | 3.33ms | x0.82 | 13.85ms | x0.96 | 100.00 | 395M | 356M | 79% | 93% | ▇▇▇▇▇▇▇▇██▇▇▇▇▁▁ | ▆▆▆▆▆▆▇▇▇▇▇▇▇▇██ |
| robyn | ~35.7k | x0.78 | 3.50ms | x0.78 | 13.39ms | x0.99 | 100.00 | 50M | 50M | 85% | 97% | ▇▇▇▇▇▇▇▇▇▇▇▇██▂▂ | ▇▇▇▇▇▇██▇▇▇▇▇▇▇▇ |
| litestar | ~31.8k | x0.70 | 3.97ms | x0.69 | 13.82ms | x0.96 | 100.00 | 84M | 77M | 84% | 97% | ▇▇▇▇▇▇▇▇▇▇▇▇██▁▁ | ▇▇▇▇██▇▇▇▇▇▇▇▇▇▇ |
| fastapi | ~24.7k | x0.54 | 5.12ms | x0.53 | 14.62ms | x0.91 | 100.00 | 84M | 75M | 97% | 100% | ▇▇▇▇▇▇▇▇▇▇▇▇▇▇██ | ██▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| flask | ~19.4k | x0.43 | 6.55ms | x0.42 | 16.95ms | x0.78 | 100.00 | 78M | 77M | 89% | 103% | ▇▇▇▇▇▇▇▇▇▇██▇▇▁▁ | ██▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| django-ninja | ~2.6k | x0.06 | 49.32ms | x0.06 | 81.62ms | x0.16 | 100.00 | 121M | 115M | 88% | 100% | ▇▇▇▇▇▇▇▇▇▇██▇▇▁▁ | ▇▇▇▇▇▇▇▇▇▇██▇▇▆▆ |

### 2 - POST /movies (JWT)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gin | ~39.0k | x2.03 | 3.03ms | x2.17 | 13.67ms | x1.29 | 100.00 | 13M | 12M | 66% | 79% | ▇▇▇▇▇▇▇▇▇▇██▇▇▁▁ | ▇▇▇▇▇▇▇▇▇▇▇▇██▆▆ |
| elysia | ~38.2k | x1.99 | 3.17ms | x2.08 | 14.40ms | x1.22 | 100.00 | 30M | 30M | 70% | 84% | ▇▇▇▇▇▇▇▇▇▇▇▇██▁▁ | ▇▇▇▇▇▇▇▇▇▇██▇▇▇▇ |
| django-bolt | ~27.6k | x1.44 | 4.53ms | x1.45 | 15.23ms | x1.16 | 100.00 | 83M | 82M | 84% | 99% | ▇▇▇▇▇▇▇▇▇▇▇▇██▁▁ | ▇▇▇▇▇▇▇▇▇▇▇▇██▇▇ |
| spring-boot | ~25.8k | x1.35 | 4.78ms | x1.38 | 16.99ms | x1.04 | 100.00 | 612M | 612M | 83% | 96% | ▇▇▇▇▇▇▇▇▇▇▇▇██▁▁ | ▇▇▇▇▇▇██▇▇▇▇▇▇▇▇ |
| jero | ~19.2k | x1.00 | 6.58ms | x1.00 | 17.61ms | x1.00 | 100.00 | 91M | 80M | 88% | 102% | ▇▇▇▇▇▇▇▇██▇▇▇▇▁▁ | ██▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| robyn | ~16.4k | x0.85 | 7.74ms | x0.85 | 17.91ms | x0.98 | 100.00 | 51M | 50M | 92% | 102% | ▇▇▇▇▇▇██▇▇▇▇▇▇▂▂ | ▇▇▇▇▇▇▇▇▇▇██▇▇▇▇ |
| blacksheep | ~13.7k | x0.71 | 9.31ms | x0.71 | 19.59ms | x0.90 | 100.00 | 74M | 73M | 88% | 102% | ▇▇██▇▇▇▇▇▇▇▇▇▇▁▁ | ██▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| litestar | ~11.1k | x0.58 | 11.51ms | x0.57 | 23.12ms | x0.76 | 100.00 | 79M | 78M | 92% | 102% | ▇▇▇▇▇▇▇▇██▇▇▇▇▂▂ | ▇▇▇▇▇▇▇▇██▇▇▇▇▇▇ |
| flask | ~9.4k | x0.49 | 13.56ms | x0.49 | 24.85ms | x0.71 | 100.00 | 78M | 78M | 89% | 102% | ██▇▇▇▇▇▇▇▇▇▇▇▇▁▁ | ▇▇▇▇▇▇▇▇██▇▇▇▇▇▇ |
| fastapi | ~8.2k | x0.43 | 15.50ms | x0.42 | 29.68ms | x0.59 | 100.00 | 76M | 76M | 89% | 102% | ▇▇▇▇▇▇▇▇▇▇▇▇██▁▁ | ██▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| django-ninja | ~2.1k | x0.11 | 60.57ms | x0.11 | 96.54ms | x0.18 | 100.00 | 115M | 109M | 91% | 100% | ▇▇▇▇▇▇▇▇██▇▇▇▇▃▃ | ██▇▇▇▇▇▇▇▇▇▇▇▇▆▆ |

### 3 - GET proxy (upstream)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| elysia | ~41.1k | x1.61 | 2.96ms | x1.67 | 13.85ms | x1.06 | 100.00 | 34M | 33M | 77% | 91% | ▇▇▇▇▇▇▇▇▇▇██▇▇▁▁ | ▇▇▇▇▇▇▇▇▇▇▇▇██▆▆ |
| gin | ~30.1k | x1.18 | 4.14ms | x1.19 | 14.53ms | x1.01 | 100.00 | 17M | 15M | 84% | 98% | ▇▇▇▇▇▇▇▇▇▇▇▇██▂▂ | ██▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| jero | ~25.6k | x1.00 | 4.93ms | x1.00 | 14.74ms | x1.00 | 100.00 | 99M | 92M | 87% | 99% | ▇▇██▇▇▇▇▇▇▇▇▇▇▁▁ | ▇▇▇▇▇▇██▇▇▇▇▇▇▇▇ |
| django-bolt | ~21.4k | x0.84 | 5.91ms | x0.83 | 16.09ms | x0.92 | 100.00 | 113M | 111M | 88% | 102% | ██▇▇▇▇▇▇▇▇▇▇▇▇▁▁ | ██▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| blacksheep | ~21.3k | x0.83 | 5.96ms | x0.83 | 15.52ms | x0.95 | 100.00 | 84M | 82M | 88% | 101% | ▇▇▇▇▇▇▇▇▇▇██▇▇▁▁ | ▇▇██▇▇▇▇▇▇▇▇▇▇▇▇ |
| spring-boot | ~20.9k | x0.82 | 6.03ms | x0.82 | 15.55ms | x0.95 | 100.00 | 639M | 639M | 88% | 101% | ▇▇▇▇██▇▇▇▇▇▇▇▇▁▁ | ██▇▇██▇▇████▇▇▇▇ |
| robyn | ~18.7k | x0.73 | 6.79ms | x0.73 | 16.30ms | x0.90 | 100.00 | 72M | 71M | 88% | 102% | ▇▇▇▇██▇▇▇▇▇▇▇▇▁▁ | ▇▇▇▇▇▇▇▇▇▇▇▇██▇▇ |
| litestar | ~17.5k | x0.69 | 7.24ms | x0.68 | 17.64ms | x0.84 | 100.00 | 93M | 92M | 89% | 100% | ▇▇██▇▇▇▇▇▇▇▇▇▇▂▂ | ██▇▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| fastapi | ~13.5k | x0.53 | 9.40ms | x0.52 | 20.85ms | x0.71 | 100.00 | 90M | 89M | 88% | 102% | ▇▇▇▇▇▇▇▇▇▇██▇▇▁▁ | ▇▇▇▇██▇▇▇▇▇▇▇▇▇▇ |
| flask | ~9.9k | x0.39 | 12.82ms | x0.38 | 21.03ms | x0.70 | 100.00 | 89M | 81M | 86% | 100% | ██▇▇▇▇▇▇▇▇▇▇▇▇▁▁ | ▇▇██▇▇▇▇▇▇▇▇▇▇▇▇ |
| django-ninja | ~2.6k | x0.10 | 49.71ms | x0.10 | 81.87ms | x0.18 | 100.00 | 134M | 122M | 88% | 100% | ▇▇▇▇▇▇▇▇▇▇██▇▇▁▁ | ██▇▇▇▇▇▇▇▇▇▇▇▇▆▆ |

### 4 - GET /users/me (DB)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gin | ~32.9k | x3.18 | 3.71ms | x3.31 | 14.80ms | x1.48 | 100.00 | 31M | 31M | 78% | 93% | ▇▇▇▇▇▇▇▇▇▇▇▇██▁▁ | ▇▇▇▇▇▇██▇▇▇▇▇▇▇▇ |
| elysia | ~28.0k | x2.71 | 4.47ms | x2.75 | 15.30ms | x1.43 | 100.00 | 37M | 36M | 83% | 100% | ▇▇██▇▇▇▇▇▇▇▇▇▇▁▁ | ▇▇▇▇▇▇▇▇▇▇▇▇██▇▇ |
| spring-boot | ~20.9k | x2.02 | 6.00ms | x2.05 | 16.80ms | x1.30 | 100.00 | 654M | 654M | 87% | 101% | ██▇▇▇▇▇▇▇▇▇▇▇▇▁▁ | ▇▇▇▇▇▇▇▇▇▇██▇▇▇▇ |
| jero | ~10.3k | x1.00 | 12.29ms | x1.00 | 21.86ms | x1.00 | 100.00 | 101M | 94M | 88% | 103% | ▇▇▇▇▇▇▇▇██▇▇▇▇▁▁ | ▇▇▇▇▇▇▇▇██▇▇▇▇▇▇ |
| blacksheep | ~9.2k | x0.89 | 13.79ms | x0.89 | 24.52ms | x0.89 | 100.00 | 87M | 84M | 89% | 103% | ██▇▇▇▇▇▇▇▇▇▇▇▇▁▁ | ▇▇▇▇██▇▇▇▇▇▇▇▇▇▇ |
| django-bolt | ~8.9k | x0.86 | 14.27ms | x0.86 | 29.75ms | x0.73 | 100.00 | 117M | 117M | 88% | 102% | ▇▇▇▇▇▇▇▇▇▇██▇▇▁▁ | ▇▇▇▇▇▇██▇▇▇▇▇▇▇▇ |
| robyn | ~8.8k | x0.85 | 14.46ms | x0.85 | 25.61ms | x0.85 | 100.00 | 76M | 74M | 88% | 102% | ▇▇▇▇▇▇▇▇▇▇██▇▇▁▁ | ▇▇▇▇▇▇▇▇▇▇▇▇██▇▇ |
| litestar | ~7.7k | x0.74 | 16.62ms | x0.74 | 29.79ms | x0.73 | 100.00 | 97M | 97M | 88% | 102% | ▇▇▇▇▇▇▇▇▇▇▇▇██▁▁ | ▇▇▇▇▇▇▇▇██▇▇▇▇▇▇ |
| fastapi | ~6.3k | x0.61 | 20.18ms | x0.61 | 34.65ms | x0.63 | 100.00 | 99M | 92M | 88% | 101% | ▇▇▇▇▇▇██▇▇▇▇▇▇▁▁ | ▇▇▇▇██▇▇▇▇▇▇▇▇▇▇ |
| flask | ~5.3k | x0.52 | 23.87ms | x0.51 | 55.98ms | x0.39 | 100.00 | 80M | 80M | 81% | 90% | ▇▇██▇▇▇▇▇▇▇▇▇▇▂▂ | ▇▇██▇▇▇▇▇▇▇▇▇▇▇▇ |
| django-ninja | ~2.0k | x0.19 | 64.45ms | x0.19 | 101.27ms | x0.22 | 100.00 | 131M | 121M | 88% | 101% | ▇▇██▇▇▇▇▇▇▇▇▇▇▁▁ | ██▇▇▇▇▇▇▇▇▇▇▇▇▆▆ |

## How these results were made

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

| Framework | Language | Server | HTTP client | DB driver | Validates body (test 2) | Parses upstream (test 3) | JSON serializer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| blacksheep | Python 3.13 | granian ASGI | pyreqwest | psqlpy | dataclass bind | passthrough dict | orjson |
| django-bolt | Python 3.13 | built-in Rust server | pyreqwest | psqlpy | msgspec Struct | passthrough bytes | msgspec |
| django-ninja | Python 3.13 | granian ASGI | pyreqwest | psqlpy | pydantic (Schema) | passthrough bytes | pydantic |
| elysia | Bun / TS | Bun native | fetch | Bun SQL | typebox schema | passthrough object | Bun native |
| fastapi | Python 3.13 | granian ASGI | pyreqwest | psqlpy | pydantic | typed (pydantic) + response-model re-validate | pydantic |
| flask | Python 3.13 | granian WSGI | pyreqwest (sync) | psycopg | pydantic | typed (pydantic) | stdlib json |
| gin | Go | net/http (GOMAXPROCS=1) | net/http | pgx | ShouldBindJSON struct | typed struct | encoding/json |
| jero | Python 3.13 | granian ASGI | pyreqwest | psqlpy | msgspec Struct | typed (msgspec) | msgspec |
| litestar | Python 3.13 | granian ASGI | pyreqwest | psqlpy | msgspec Struct | typed (msgspec) | msgspec |
| robyn | Python 3.13 | built-in Rust server | pyreqwest | psqlpy | pydantic (native param) | typed (pydantic) | stdlib json / pydantic |
| spring-boot | Java 25 | embedded Tomcat, virtual threads | RestClient (Apache HttpClient5) | JdbcTemplate (HikariCP) | jakarta bean validation (record) | typed (Jackson) | Jackson |

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
visible here so a number is never mistaken for pure framework speed.

## Disclosure

The author of this benchmark suite is also the author of [jero](https://pypi.org/project/jero/), one of the frameworks benchmarked here. Every measure above -- equal resource budgets, idiomatic code per framework, isolated single-framework runs, documented intended differences -- applies identically to jero and everyone else; nothing here is tuned in its favor.

---
_Generated by `export_results.py` from `results.is_best` rows in mr-blobby._
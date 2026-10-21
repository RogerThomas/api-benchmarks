# jero-benchmarks — run `20261020T235525`

_Generated 2026-10-21T00:03:43+00:00_

## Run configuration

| | |
| --- | --- |
| **Run ID** | `20261020T235525` |
| **Created** | 2026-10-20 23:55:25 UTC |
| **Host** | 9350 |
| **AWS region** | -- (not run on EC2) |
| **EC2 instance type** | -- |
| **EC2 AMI** | -- |
| **k6 VUs** | 100 |
| **Duration per attempt** | 10s |
| **Best of** | 3 |
| **Server workers** | 1 |
| **Python server** | granian |
| **Event loop** | uvloop |
| **Frameworks** | blacksheep, jero, wred |
| **Results backend** | /home/harrisonerd/Dropbox/Projects/sandbox/api-benchmarks/results/bench.db |

## Results

![jero-benchmarks results grid](chart.svg)

### 1 - GET /info

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero | ~29.4k | x1.00 | 3.31ms | x1.00 | 16.03ms | x1.00 | 100.00 | 68M | 67M | 71% | 74% | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ | ████▇▇▇▇▇▇▇▇▇▇▇▇ |
| wred | ~29.4k | x1.00 | 3.31ms | x1.00 | 15.66ms | x1.02 | 100.00 | 64M | 63M | 68% | 71% | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ | ████▇▇▇▇▇▇▇▇▇▇▇▇ |
| blacksheep | ~28.9k | x0.98 | 3.41ms | x0.97 | 15.62ms | x1.03 | 100.00 | 68M | 68M | 79% | 82% | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ | ▇▇▇▇███▇▇▇▇▇▇▇▇▇ |

### 2 - POST /movies (JWT)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero | ~16.4k | x1.00 | 6.03ms | x1.00 | 20.02ms | x1.00 | 100.00 | 68M | 68M | 81% | 97% | ▇▇▇▇▇▇▇▇███▇▇▇▁▁ | ███▇▇▇▇▇▇▇▇▇▇▇▇▇ |
| wred | ~16.3k | x0.99 | 6.06ms | x1.00 | 20.12ms | x0.99 | 100.00 | 66M | 65M | 97% | 98% | ▇▇▇▇▇▇▇▇▇▇███▇▇▇ | ████▇▇▇▇▇▇▇▇▇▇▇▇ |
| blacksheep | ~11.4k | x0.69 | 8.73ms | x0.69 | 21.00ms | x0.95 | 100.00 | 80M | 72M | 101% | 101% | ████▇▇▇▇▇▇▇▇▇▇▇▇ | ▇▇▇▇▇▇▇███▇▇▇▇▇▇ |

### 3 - GET proxy (upstream)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| wred | ~22.6k | x1.01 | 4.35ms | x1.01 | 17.57ms | x1.00 | 100.00 | 80M | 78M | 73% | 91% | ▇▇▇▇▇▇▇▇▇▇▇███▁▁ | ▇▇▇███▇▇▇▇▇▇▇▇▇▇ |
| jero | ~22.5k | x1.00 | 4.38ms | x1.00 | 17.61ms | x1.00 | 100.00 | 84M | 82M | 73% | 90% | ▇▇▇▇▇▇▇▇▇▇▇███▁▁ | ▇▇▇▇▇▇▇▇▇▇▇███▇▇ |
| blacksheep | ~19.5k | x0.87 | 5.05ms | x0.87 | 17.94ms | x0.98 | 100.00 | 87M | 82M | 94% | 94% | ▇▇▇▇▇▇▇███▇▇▇▇▇▇ | ▇▇▇▇▇▇▇███▇▇▇▇▇▇ |

### 4 - GET /users/me (DB)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| wred | ~9.9k | x1.01 | 10.05ms | x1.01 | 21.30ms | x1.01 | 100.00 | 80M | 79M | 101% | 101% | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ | ████▇▇▇▇▇▇▇▇▇▇▇▇ |
| jero | ~9.8k | x1.00 | 10.14ms | x1.00 | 21.52ms | x1.00 | 100.00 | 83M | 82M | 100% | 101% | ▇▇▇▇▇▇▇███▇▇▇▇▇▇ | ████▇▇▇▇▇▇▇▇▇▇▇▇ |
| blacksheep | ~8.5k | x0.87 | 11.70ms | x0.87 | 23.41ms | x0.92 | 100.00 | 91M | 84M | 100% | 101% | ▇▇▇▇███▇▇▇▇▇▇▇▇▇ | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ |

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
| jero | Python 3.13 | granian ASGI | pyreqwest | psqlpy | msgspec Struct | typed (msgspec) | msgspec |
| wred | Python 3.13 | granian ASGI | pyreqwest | psqlpy | msgspec Struct | passthrough dict | orjson |

**One deliberate exception to per-framework idiom:** the two Django frameworks
reach Postgres through raw psqlpy -- the same driver the rest of the async
Python fleet uses -- rather than Django's ORM, whose sync-driver-behind-an-async-facade
design would make test 4 a measurement of Django's data layer instead of the
framework. For the same reason, every JWT endpoint hand-decodes the bearer
token with PyJWT rather than using each framework's own auth integration.

**Known, intended differences** (each framework's real idiomatic behaviour, kept
rather than normalised away): the JSON serializer column (stdlib `json` is
slower than msgspec/orjson/native); FastAPI additionally re-validates the
*response* against its `response_model`; Wred/Blacksheep/Elysia/Django Ninja/Django
Bolt return the upstream payload straight through as bytes/dict; the two Django
frameworks return snake_case field names where the rest of the Python fleet
returns camelCase; Spring Boot's Jackson binding coerces a numeric field given
as a JSON string rather than rejecting it like pydantic/msgspec do. These are
visible here so a number is never mistaken for pure framework speed.

Wred reuses the fixed `/info` dictionary and its msgspec movie decoder across
requests. It still serializes each response and generates a fresh response UUID
per request.

## Disclosure

The upstream suite was written by the author of [jero](https://pypi.org/project/jero/). This fork adds [Wred](https://pypi.org/project/wred/) and is maintained by Wred's author. Every measure above -- equal resource budgets, idiomatic code per framework, isolated single-framework runs, documented intended differences -- applies identically to jero, Wred, and everyone else; nothing here is tuned in their favor.

---
_Generated by `export_results.py` from `results.is_best` rows in /home/harrisonerd/Dropbox/Projects/sandbox/api-benchmarks/results/bench.db._

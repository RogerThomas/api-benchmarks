# jero-benchmarks — run `post-upgrade-comparison`

_Generated 2026-08-16T07:11:35+00:00_

## Run configuration

| | |
| --- | --- |
| **Run ID** | `post-upgrade-comparison` |
| **Created** | 2026-08-16 07:05:36 UTC |
| **Host** | NITRO-GY7N7RYTHK |
| **AWS region** | -- (not run on EC2) |
| **EC2 instance type** | -- |
| **EC2 AMI** | -- |
| **k6 VUs** | 128 |
| **Duration per attempt** | 10s |
| **Best of** | 3 |
| **Server workers** | 1 |
| **Python server** | granian |
| **Event loop** | uvloop |
| **Frameworks** | jero-granian, jero-uvicorn |

## Results

![jero-benchmarks results grid](chart.svg)

### 1 - GET /info

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero-granian | ~51.2k | - | 2.43ms | - | 12.15ms | - | 100.00 | 77M | 77M | 88% | 91% | ▇▇▇▇▇▇▇▇▇▇███▇▇▇ | ▇▇▇▇▇▇▇███▇▇▇▇▇▇ |
| jero-uvicorn | ~51.1k | - | 2.42ms | - | 11.65ms | - | 100.00 | 50M | 50M | 89% | 91% | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ | ▇▇▇▇███▇▇▇▇▇▇▇▇▇ |

### 2 - POST /movies (JWT)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero-uvicorn | ~32.7k | - | 3.80ms | - | 13.98ms | - | 100.00 | 50M | 50M | 93% | 94% | ▇▇▇▇▇▇▇▇▇▇███▇▇▇ | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ |
| jero-granian | ~27.4k | - | 4.59ms | - | 14.61ms | - | 100.00 | 78M | 78M | 81% | 98% | ▇▇▇▇▇▇▇▇███▇▇▇▁▁ | ▇▇▇▇▇▇▇▇███▇▇▇▇▇ |

### 3 - GET proxy (upstream)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero-uvicorn | ~28.9k | - | 4.36ms | - | 12.93ms | - | 100.00 | 62M | 61M | 98% | 99% | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ | ▇▇▇▇███▇▇▇▇▇▇▇▇▇ |
| jero-granian | ~28.1k | - | 4.49ms | - | 13.73ms | - | 100.00 | 105M | 95M | 98% | 99% | ▇▇▇▇▇▇▇███▇▇▇▇▇▇ | ████▇▇▇▇▇▇▇▇▇▇▇▇ |

### 4 - GET /users/me (DB)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero-uvicorn | ~13.8k | - | 9.23ms | - | 21.28ms | - | 100.00 | 63M | 63M | 100% | 100% | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ |
| jero-granian | ~13.1k | - | 9.72ms | - | 16.99ms | - | 100.00 | 103M | 96M | 100% | 101% | ▇▇▇▇▇▇▇███▇▇▇▇▇▇ | ▇▇▇▇▇▇▇▇▇▇███▇▇▇ |

### 5 - POST /echo (body only, no JWT -- diagnostic, jero only)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero-uvicorn | ~51.3k | - | 2.38ms | - | 12.20ms | - | 100.00 | 72M | 65M | 81% | 84% | ▇▇▇▇▇▇▇▇▇▇▇▇▇███ | ▇▇▇▇███▇▇▇▇▇▇▇▇▇ |
| jero-granian | ~36.9k | - | 3.41ms | - | 13.35ms | - | 100.00 | 95M | 95M | 95% | 96% | ▇▇▇▇▇▇▇███▇▇▇▇▇▇ | ▇▇▇▇▇▇▇███▇▇▇▇▇▇ |

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
best-scoring attempt is kept. Score equally weights throughput and latency,
each normalized against that test's best attempt:

```
score = reqsPerSec/maxReqs + minMean/mean + minP99/p99
```

**Resource-use columns.** `memPk`/`memAv` = peak/average resident memory (MB);
`cpuAv`/`cpuPk` = average/peak CPU as % of one core (pinned via `cpuset`, so
these sit ≤100%); `cpu ~`/`mem ~` = a 0-to-max-scaled sparkline of the CPU/memory
time series during the attempt. Only the framework's own container is measured
-- Postgres and the upstream are excluded.

**Equal work, per test** -- every framework does the same task; only the
*native* tool differs:



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
_Generated by `export_results.py` from `results.is_best` rows._
# jero-benchmarks — run `sweep-smoketest`

_Generated 2026-08-15T20:39:49+00:00_

## Run configuration

| | |
| --- | --- |
| **Run ID** | `sweep-smoketest` |
| **Created** | 2026-08-15 20:38:25 UTC |
| **Host** | NITRO-GY7N7RYTHK |
| **AWS region** | -- (not run on EC2) |
| **EC2 instance type** | -- |
| **EC2 AMI** | -- |
| **k6 VUs** | 10 |
| **Duration per attempt** | 5s |
| **Best of** | 1 |
| **Server workers** | 1 |
| **Python server** | granian |
| **Event loop** | uvloop |
| **Frameworks** | jero-granian, jero-uvicorn |

## Results

![jero-benchmarks results grid](chart.svg)

### 1 - GET /info

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero-uvicorn | ~40.8k | - | 0.22ms | - | 1.29ms | - | 100.00 | 54M | 50M | 83% | 83% | ▇▇▇▇▇▇█████▇▇▇▇▇ | ▇▇▇▇▇▇█████▇▇▇▇▇ |
| jero-granian | ~38.6k | - | 0.24ms | - | 1.00ms | - | 100.00 | 73M | 73M | 93% | 95% | ▇▇▇▇▇▇▇▇▇▇▇█████ | ██████▇▇▇▇▇▇▇▇▇▇ |

### 2 - POST /movies (JWT)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero-uvicorn | ~30.5k | - | 0.30ms | - | 1.35ms | - | 100.00 | 49M | 48M | 68% | 91% | ▇▇▇▇▇▇█████▂▂▂▂▂ | ▇▇▇▇▇▇█████▇▇▇▇▇ |
| jero-granian | ~18.7k | - | 0.51ms | - | 1.21ms | - | 100.00 | 73M | 73M | 77% | 99% | ▇▇▇▇▇▇█████▃▃▃▃▃ | ██████▇▇▇▇▇▇▇▇▇▇ |

### 3 - GET proxy (upstream)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero-uvicorn | ~22.3k | - | 0.43ms | - | 1.35ms | - | 100.00 | 51M | 51M | 66% | 97% | ▇▇▇▇▇▇█████▁▁▁▁▁ | ██████▇▇▇▇▇▇▇▇▇▇ |
| jero-granian | ~19.0k | - | 0.50ms | - | 1.30ms | - | 100.00 | 76M | 76M | 70% | 99% | ▇▇▇▇▇▇█████▁▁▁▁▁ | ▇▇▇▇▇▇█████▇▇▇▇▇ |

### 4 - GET /users/me (DB)

| Framework | req/s | vs | mean | vs | p99 | vs | succ% | memPk | memAv | cpuAv | cpuPk | cpu ~ | mem ~ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jero-granian | ~10.2k | - | 0.95ms | - | 2.04ms | - | 100.00 | 77M | 77M | 72% | 101% | ▇▇▇▇▇▇█████▁▁▁▁▁ | ██████▇▇▇▇▇▇▇▇▇▇ |
| jero-uvicorn | ~10.0k | - | 0.97ms | - | 2.16ms | - | 100.00 | 52M | 52M | 71% | 101% | ▇▇▇▇▇▇█████▁▁▁▁▁ | ██████▇▇▇▇▇▇▇▇▇▇ |

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
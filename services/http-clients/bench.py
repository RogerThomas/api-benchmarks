#!yeet
"""Benchmark sequential and concurrent HTTP GET requests with four clients."""

import asyncio
import logging
import math
import statistics
import time
from collections.abc import AsyncGenerator, Awaitable, Buffer, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Annotated, Literal, Self

import aiohttp
import httpx2
import niquests
from msgspec import Struct, json
from pyreqwest.client import Client, ClientBuilder
from rich.console import Console
from rich.table import Table
from yeetr import Opt

logging.getLogger("httpx2").setLevel(logging.WARNING)

type Tag = Literal["electronics", "peripherals", "keyboard"]
type DurationOpt = Annotated[float, Opt(alias="d", help="Duration per client and test")]
type ConcurrencyOpt = Annotated[int, Opt(alias="c", help="Concurrent requests")]
type APIKeyOpt = Annotated[str, Opt(envvar="UPSTREAM_API_KEY")]


class Vendor(Struct):
    id: str
    name: str


class Product(Struct):
    id: str
    title: str
    price: float
    inStock: bool
    tags: list[Tag]
    rating: float
    description: str
    vendor: Vendor


@dataclass(slots=True)
class _ProductDecoder:
    _decoder: json.Decoder = field(
        default_factory=lambda: json.Decoder(type=Product), init=False, repr=False
    )

    def _decode_product(self, body: Buffer) -> Product:
        return self._decoder.decode(body)


@dataclass(frozen=True, slots=True)
class Result:
    client: str
    samples_ms: list[float]
    elapsed_seconds: float

    @property
    def mean(self) -> float:
        return statistics.fmean(self.samples_ms)

    @property
    def p99(self) -> float:
        ordered = sorted(self.samples_ms)
        return ordered[math.ceil(0.99 * len(ordered)) - 1]

    @property
    def stdev(self) -> float:
        return statistics.pstdev(self.samples_ms)

    @property
    def requests_per_second(self) -> float:
        return len(self.samples_ms) / self.elapsed_seconds


@dataclass(slots=True)
class HTTPXHandler(_ProductDecoder):
    _client: httpx2.AsyncClient

    @classmethod
    @asynccontextmanager
    async def build(
        cls, base_url: str, headers: dict[str, str], concurrency: int
    ) -> AsyncGenerator[Self]:
        timeout = httpx2.Timeout(10.0, connect=1.0, read=5.0)
        async with httpx2.AsyncClient(
            headers=headers,
            base_url=base_url,
            timeout=timeout,
            follow_redirects=False,
            limits=httpx2.Limits(
                max_connections=concurrency,
                max_keepalive_connections=concurrency,
            ),
            trust_env=False,
        ) as client:
            yield cls(client)

    async def get_product(self) -> Product:
        response = await self._client.get("/data")
        response.raise_for_status()
        return self._decode_product(response.content)


@dataclass(slots=True)
class AIOHTTPHandler(_ProductDecoder):
    _client: aiohttp.ClientSession

    @classmethod
    @asynccontextmanager
    async def build(
        cls, base_url: str, headers: dict[str, str], concurrency: int
    ) -> AsyncGenerator[Self]:
        timeout = aiohttp.ClientTimeout(total=10.0, connect=1.0, sock_read=5.0)
        connector = aiohttp.TCPConnector(limit=concurrency)
        async with aiohttp.ClientSession(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            connector=connector,
            raise_for_status=True,
            trust_env=False,
        ) as client:
            yield cls(client)

    async def get_product(self) -> Product:
        async with self._client.get("/data", allow_redirects=False) as response:
            return self._decode_product(await response.read())


@dataclass(slots=True)
class NiquestsHandler(_ProductDecoder):
    _client: niquests.AsyncSession

    @classmethod
    @asynccontextmanager
    async def build(
        cls, base_url: str, headers: dict[str, str], concurrency: int
    ) -> AsyncGenerator[Self]:
        async with niquests.AsyncSession(
            base_url=base_url,
            headers=headers,
            timeout=(1.0, 5.0),
            pool_maxsize=concurrency,
        ) as client:
            yield cls(client)

    async def get_product(self) -> Product:
        response = await self._client.get("/data", allow_redirects=False, stream=False)
        response.raise_for_status()
        body = response.content
        if body is None:
            raise ValueError("niquests returned an empty response body")
        return self._decode_product(body)


@dataclass(slots=True)
class PyreqwestHandler(_ProductDecoder):
    _client: Client

    @classmethod
    @asynccontextmanager
    async def build(
        cls, base_url: str, headers: dict[str, str], concurrency: int
    ) -> AsyncGenerator[Self]:
        client = (
            ClientBuilder()
            .base_url(base_url)
            .default_headers(headers)
            .error_for_status()
            .connect_timeout(timedelta(seconds=1))
            .read_timeout(timedelta(seconds=5))
            .timeout(timedelta(seconds=10))
            .max_connections(concurrency)
            .follow_redirects(False)
            .no_proxy()
            .build()
        )
        async with client:
            yield cls(client)

    async def get_product(self) -> Product:
        response = await self._client.get("data").build().send()
        return self._decode_product(await response.bytes())


async def _worker(
    deadline: float,
    get_product: Callable[[], Awaitable[Product]],
    samples_ms: list[float],
) -> None:
    while time.perf_counter() < deadline:
        started = time.perf_counter_ns()
        await get_product()
        samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)


async def _measure(
    duration: float,
    concurrency: int,
    get_product: Callable[[], Awaitable[Product]],
) -> tuple[list[float], float]:
    samples_ms: list[float] = []
    started = time.perf_counter()
    deadline = started + duration
    async with asyncio.TaskGroup() as tasks:
        for _ in range(concurrency):
            tasks.create_task(_worker(deadline, get_product, samples_ms))
    return samples_ms, time.perf_counter() - started


def _make_result(client: str, measurement: tuple[list[float], float]) -> Result:
    samples_ms, elapsed_seconds = measurement
    return Result(client, samples_ms, elapsed_seconds)


def _result_throughput(result: Result) -> float:
    return result.requests_per_second


def _render_table(title: str, results: list[Result], console: Console) -> None:
    table = Table(title=title)
    table.add_column("Client", style="cyan")
    table.add_column("Requests", justify="right")
    table.add_column("Mean (ms)", justify="right")
    table.add_column("P99 (ms)", justify="right")
    table.add_column("Stdev (ms)", justify="right")
    table.add_column("Req/s", justify="right")
    table.add_column("vs httpx2", justify="right")

    httpx2_rps = next(result.requests_per_second for result in results if result.client == "httpx2")

    for result in sorted(results, key=_result_throughput, reverse=True):
        table.add_row(
            result.client,
            f"{len(result.samples_ms):,}",
            f"{result.mean:.3f}",
            f"{result.p99:.3f}",
            f"{result.stdev:.3f}",
            f"{result.requests_per_second:,.0f}",
            f"{result.requests_per_second / httpx2_rps:.2f}×",
        )

    console.print()
    console.print(table)


async def _run_suite(
    base_url: str,
    headers: dict[str, str],
    duration: float,
    concurrency: int,
    console: Console,
) -> list[Result]:
    results: list[Result] = []
    mode = "sequential" if concurrency == 1 else f"concurrent ({concurrency})"

    console.print(f"Running [bold]pyreqwest[/bold] {mode} for {duration:g}s...")
    async with PyreqwestHandler.build(base_url, headers, concurrency) as handler:
        result = await _measure(duration, concurrency, handler.get_product)
        results.append(_make_result("pyreqwest", result))

    console.print(f"Running [bold]httpx2[/bold] {mode} for {duration:g}s...")
    async with HTTPXHandler.build(base_url, headers, concurrency) as handler:
        result = await _measure(duration, concurrency, handler.get_product)
        results.append(_make_result("httpx2", result))

    console.print(f"Running [bold]aiohttp[/bold] {mode} for {duration:g}s...")
    async with AIOHTTPHandler.build(base_url, headers, concurrency) as handler:
        result = await _measure(duration, concurrency, handler.get_product)
        results.append(_make_result("aiohttp", result))

    console.print(f"Running [bold]niquests[/bold] {mode} for {duration:g}s...")
    async with NiquestsHandler.build(base_url, headers, concurrency) as handler:
        result = await _measure(duration, concurrency, handler.get_product)
        results.append(_make_result("niquests", result))

    return results


async def _run(
    base_url: str,
    api_key: str,
    duration: float,
    concurrency: int,
    console: Console,
) -> None:
    base_url = f"{base_url.rstrip('/')}/"
    console.print(
        f"Settings: base URL [cyan]{base_url}[/cyan], "
        f"duration [cyan]{duration:g}s[/cyan], "
        f"concurrency [cyan]{concurrency}[/cyan]"
    )
    headers = {"Authorization": f"Bearer {api_key}"}
    sequential = await _run_suite(base_url, headers, duration, 1, console)
    _render_table(f"Sequential GET benchmark ({duration:g}s per client)", sequential, console)

    concurrent = await _run_suite(base_url, headers, duration, concurrency, console)
    _render_table(
        f"Concurrent GET benchmark ({duration:g}s per client, concurrency {concurrency})",
        concurrent,
        console,
    )


async def main(
    base_url: str = "http://127.0.0.1:6700/",
    *,
    upstream_api_key: APIKeyOpt,
    duration: DurationOpt = 10.0,
    concurrency: ConcurrencyOpt = 10,
) -> None:
    if duration <= 0:
        raise ValueError("-d must be greater than zero")
    if concurrency < 1:
        raise ValueError("-c must be at least 1")
    await _run(base_url, upstream_api_key, duration, concurrency, Console())

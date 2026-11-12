"""Small loopback latency probe. Does not establish internet-scale capacity."""

import argparse
import asyncio
import json
import math
import time
from collections import Counter
from pathlib import Path

import httpx


async def run(args):
    if not args.base_url.startswith("http://127.0.0.1:"):
        raise ValueError("Only the local development service is supported")
    payload = json.loads(
        (Path(__file__).resolve().parents[1] / "examples/request.json").read_text()
    )
    gate = asyncio.Semaphore(args.concurrency)
    durations, statuses = [], Counter()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=15, trust_env=False) as client:

        async def one():
            async with gate:
                started = time.perf_counter()
                try:
                    response = await client.post("/v1/recommend", json=payload)
                    statuses[str(response.status_code)] += 1
                except httpx.HTTPError:
                    statuses["transport_error"] += 1
                durations.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(args.requests)))
        elapsed = time.perf_counter() - started
    durations.sort()
    result = {
        "label": "LOCAL_PROBE_NOT_PRODUCTION_CAPACITY",
        "requests": args.requests,
        "concurrency": args.concurrency,
        "statuses": dict(statuses),
        "wall_seconds": round(elapsed, 3),
        "throughput_per_second": round(args.requests / elapsed, 2),
        "p50_ms": round(durations[math.ceil(0.5 * len(durations)) - 1], 2),
        "p95_ms": round(durations[math.ceil(0.95 * len(durations)) - 1], 2),
    }
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if not 1 <= args.requests <= 500 or not 1 <= args.concurrency <= 16:
        raise ValueError("Probe is intentionally bounded to 500 requests and 16 concurrency")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()

"""Exercise a running loopback API without any real browsing data."""

import argparse
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    payload = json.loads(
        (Path(__file__).resolve().parents[1] / "examples/request.json").read_text()
    )
    # Only loopback targets: this utility is not an arbitrary production traffic sender.
    if not args.base_url.startswith("http://127.0.0.1:"):
        raise ValueError("Use the loopback development service")
    with httpx.Client(base_url=args.base_url, timeout=15, trust_env=False) as client:
        client.get("/health/ready").raise_for_status()
        response = client.post("/v1/recommend", json=payload)
        response.raise_for_status()
        result = response.json()
        assert result["mode"] in {"demo", "live"}
        assert len(result["recommendations"]) <= 10
        assert result["request_id"] == response.headers["X-Request-ID"]
        print(
            json.dumps(
                {
                    "status": "passed",
                    "mode": result["mode"],
                    "ranker": result["ranker"],
                    "results": len(result["recommendations"]),
                    "elapsed_ms": result["elapsed_ms"],
                }
            )
        )


if __name__ == "__main__":
    main()

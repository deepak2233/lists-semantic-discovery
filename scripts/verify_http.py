"""Start, exercise and stop a local server within one isolated test environment."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default="")
    args = parser.parse_args()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        {
            "LISTS_ENV": "development",
            "LISTS_PROVIDER": "demo",
            "LISTS_AUTH_MODE": "none",
            "CACHE_TTL_SECONDS": "0",
            "REQUESTS_PER_MINUTE": "1000",
            "LISTS_MODEL_PATH": args.model_path,
            "LISTS_ALLOWED_HOSTS": "127.0.0.1",
            "LISTS_ALLOWED_ORIGINS": "",
        }
    )
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "lists_api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-access-log",
        "--no-proxy-headers",
    ]
    server = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=1, trust_env=False) as client:
            for _attempt in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Test server failed to start: " + server.stdout.read())
                try:
                    if client.get(base + "/health/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Test server did not become ready in 10 seconds")
        subprocess.run(
            [sys.executable, "scripts/smoke.py", "--base-url", base], check=True, cwd=ROOT
        )
        mode = "semantic" if args.model_path else "lexical"
        target = ROOT / f"evaluation/local_probe_{mode}.json"
        subprocess.run(
            [
                sys.executable,
                "scripts/load_probe.py",
                "--base-url",
                base,
                "--requests",
                "20",
                "--concurrency",
                "2",
                "--output",
                str(target),
            ],
            check=True,
            cwd=ROOT,
        )
        result = json.loads(target.read_text())
        if result["statuses"] != {"200": 20}:
            raise RuntimeError("HTTP probe included failed requests")
    finally:
        server.terminate()
        try:
            server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate()


if __name__ == "__main__":
    main()

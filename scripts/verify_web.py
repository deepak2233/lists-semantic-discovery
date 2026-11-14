"""Verify the actual web entrypoint using only installed production dependencies."""

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
    parser.add_argument("--model-path", required=True)
    args = parser.parse_args()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.pop("VERCEL", None)
    environment.update(
        LISTS_ENV="demo",
        LISTS_PROVIDER="demo",
        LISTS_AUTH_MODE="none",
        LISTS_ALLOWED_ORIGINS="",
        LISTS_ALLOWED_HOSTS="127.0.0.1",
        LISTS_WEB_ORIGINS=base,
        LISTS_MODEL_PATH=str(Path(args.model_path).resolve()),
        PYTHONPATH=str(ROOT / "backend"),
    )
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
            "--no-proxy-headers",
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        with httpx.Client(base_url=base, timeout=20, trust_env=False) as client:
            for _ in range(150):
                if server.poll() is not None:
                    raise RuntimeError("Web startup failed: " + server.stdout.read())
                try:
                    if client.get("/health/ready", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Web server did not become ready")
            assert client.get("/v1/config").json()["semantic_available"] is True
            for path in (
                "/",
                "/assets/app.js",
                "/assets/playground.js",
                "/assets/comparison.js",
                "/assets/nlp.js",
                "/assets/safety.js",
                "/assets/styles.css",
                "/assets/tokens.css",
            ):
                client.get(path).raise_for_status()
            payload = json.loads((ROOT / "examples/request.json").read_text())
            counts = {}
            for mode in ("semantic", "lexical", "fine_tuned"):
                response = client.post(
                    "/v1/recommend", json=payload | {"ranking": mode}, headers={"Origin": base}
                )
                response.raise_for_status()
                data = response.json()
                assert len(data["recommendations"]) == 10
                assert ("minilm" in data["ranker"]) == (mode != "lexical")
                assert all(
                    (r["semantic_similarity"] is not None) == (mode != "lexical")
                    for r in data["recommendations"]
                )
                counts[mode] = len(data["recommendations"])
            config = client.get("/v1/config").json()
            assert config["fine_tuned_available"] is True
            scores = []
            for text in (
                "A developer sets timeouts and retry limits for a service.",
                "A baker kneads dough and puts bread in an oven.",
            ):
                comparison = client.post(
                    "/v1/compare",
                    headers={"Origin": base},
                    json={
                        "text_a": "An engineer adds request deadlines and retries to a Python API.",
                        "text_b": text,
                    },
                )
                comparison.raise_for_status()
                evidence = comparison.json()
                assert "snli-lora-v1" in evidence["fine_tuned_model"]
                assert len(evidence["fine_tuned_checkpoint_sha256"]) == 64
                assert -1 <= evidence["fine_tuned_cosine"] <= 1
                scores.append(evidence["fine_tuned_cosine"])
            assert scores[0] > scores[1] + 0.2
            print(
                json.dumps(
                    {"web_runtime": "passed", "results": counts, "actual_comparison_scores": scores}
                )
            )
    finally:
        server.terminate()
        try:
            server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate()


if __name__ == "__main__":
    main()

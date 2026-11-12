"""Reproducible Vercel build. No model downloads occur in the inference request path."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable, "scripts/build_web.py"], cwd=ROOT, check=True)
    if os.getenv("LISTS_BUILD_SEMANTIC", "1") == "0":
        print("Explicit lexical deployment selected; semantic capability will report unavailable.")
        return
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--requirement",
            "deploy/vercel-requirements.txt",
        ],
        cwd=ROOT,
        check=True,
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "backend")
    subprocess.run(
        [sys.executable, "scripts/download_model.py"], cwd=ROOT, env=environment, check=True
    )
    print("Pinned MiniLM model and locked runtime dependencies are ready for deployment.")


if __name__ == "__main__":
    main()

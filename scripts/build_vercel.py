"""Reproducible Vercel build. No model downloads occur in the inference request path."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable, "scripts/build_web.py"], cwd=ROOT, check=True)
    if os.getenv("LISTS_BUILD_SEMANTIC", "1") == "0":
        print("Explicit lexical deployment selected; semantic capability will report unavailable.")
        return
    # Vercel packages the declared runtime graph, not packages added after its dependency scan.
    # Fail this build immediately if that graph cannot load the actual inference dependencies.
    subprocess.run(
        [sys.executable, "-c", "import onnxruntime, tokenizers, numpy"], cwd=ROOT, check=True
    )
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("Install uv to reproduce the locked model export environment")
    environment = os.environ.copy()
    export_env = ROOT / "tmp/export-env"
    environment.update(UV_PROJECT_ENVIRONMENT=str(export_env), PYTHONHASHSEED="2233")
    # This isolated toolchain merges the committed adapter. It never trains during a build.
    subprocess.run(
        [uv, "sync", "--project", "training", "--frozen", "--no-install-project"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    subprocess.run(
        [str(export_env / "bin/python"), "training/export_model.py", "--check-catalog"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    print("Reviewed baseline and trained adapter exported; runtime uses only ONNX dependencies.")


if __name__ == "__main__":
    main()

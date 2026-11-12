"""Explicit build-time download of one pinned public model. No access token is needed."""

import argparse
import hashlib
import json
from pathlib import Path

import httpx
from lists_api.semantic import MODEL_REPO, MODEL_REVISION, MODEL_SHA256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="models/minilm")
    args = parser.parse_args()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    checksums = {}
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        for source, target, size_limit in [
            ("tokenizer.json", "tokenizer.json", 2_000_000),
            ("onnx/model.onnx", "model.onnx", 100_000_000),
        ]:
            path = root / target
            temporary = path.with_suffix(".download")
            url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{source}"
            digest = hashlib.sha256()
            received = 0
            try:
                with client.stream("GET", url) as response, temporary.open("wb") as output:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        received += len(chunk)
                        if received > size_limit:
                            raise ValueError("Model download exceeds expected size")
                        digest.update(chunk)
                        output.write(chunk)
                if target == "model.onnx" and digest.hexdigest() != MODEL_SHA256:
                    raise ValueError("Model checksum does not match the pinned publisher artifact")
                temporary.replace(path)
                checksums[target] = digest.hexdigest()
                print(f"Verified {target}: {received} bytes")
            finally:
                temporary.unlink(missing_ok=True)
    manifest = {
        "repository": MODEL_REPO,
        "revision": MODEL_REVISION,
        "sha256": checksums,
        "license": "Apache-2.0",
        "max_tokens": 256,
        "dimensions": 384,
        "pooling": "attention-mask mean + L2 normalization",
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Set LISTS_MODEL_PATH={root.resolve()}")


if __name__ == "__main__":
    main()

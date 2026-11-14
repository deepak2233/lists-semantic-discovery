"""Pinned public inputs shared by training and deterministic deployment export."""

import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE_REPO = "sentence-transformers/all-MiniLM-L6-v2"
BASE_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
BASE_WEIGHT_SHA256 = "53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db"
DATA_REPO = "stanfordnlp/snli"
DATA_REVISION = "cdb5c3d5eed6ead6e5a341c8e56e669bb666725b"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def download(url, path, *, expected=None, maximum=150_000_000):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (expected is None or digest(path) == expected):
        return {"url": url, "sha256": digest(path), "bytes": path.stat().st_size}
    temp = path.with_suffix(path.suffix + ".download")
    size = 0
    try:
        with httpx.Client(timeout=90, follow_redirects=True) as client:
            with client.stream("GET", url) as response, temp.open("wb") as out:
                response.raise_for_status()
                for block in response.iter_bytes():
                    size += len(block)
                    if size > maximum:
                        raise ValueError("Pinned download exceeds its size bound")
                    out.write(block)
        if expected and digest(temp) != expected:
            raise ValueError("Pinned download checksum mismatch")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return {"url": url, "sha256": digest(path), "bytes": path.stat().st_size}


def prepare_base():
    base = ROOT / "models/minilm-pytorch"
    records = {}
    for name in (
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "model.safetensors",
    ):
        records[name] = download(
            f"https://huggingface.co/{BASE_REPO}/resolve/{BASE_REVISION}/{name}",
            base / name,
            expected=BASE_WEIGHT_SHA256 if name == "model.safetensors" else None,
        )
    (base / "source_manifest.json").write_text(json.dumps(records, indent=2) + "\n")
    return base


def normalize(text):
    return " ".join(text.casefold().split())

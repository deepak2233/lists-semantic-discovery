"""Prepare a bounded SNLI experiment without mixing this run's evaluation text into training."""

import argparse
import hashlib
import json
import random
from collections import defaultdict

import httpx
import pyarrow.parquet as pq
from common import DATA_REPO, DATA_REVISION, ROOT, digest, download, normalize, prepare_base


def triples(rows, rng):
    grouped = defaultdict(lambda: {0: [], 2: []})
    for row in rows:
        if row["label"] in (0, 2):
            grouped[row["premise"]][row["label"]].append(row["hypothesis"])
    items = []
    for anchor, values in grouped.items():
        if not values[0] or not values[2]:
            continue
        positive, negative = rng.choice(values[0]), rng.choice(values[2])
        if len({normalize(t) for t in (anchor, positive, negative)}) == 3:
            items.append({"anchor": anchor, "positive": positive, "negative": negative})
    rng.shuffle(items)
    return items


def texts(row):
    return {normalize(row[k]) for k in ("anchor", "positive", "negative")}


def choose(rows, maximum, blocked):
    selected, seen_pairs, own = [], set(), set()
    for row in rows:
        terms = texts(row)
        key = tuple(normalize(row[k]) for k in ("anchor", "positive", "negative"))
        if terms & blocked or key in seen_pairs:
            continue
        selected.append(row)
        own.update(terms)
        seen_pairs.add(key)
        if len(selected) == maximum:
            break
    if len(selected) != maximum:
        raise ValueError("Insufficient distinct records for the requested split")
    return selected, own


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=int, default=8192)
    parser.add_argument("--validation", type=int, default=512)
    parser.add_argument("--test", type=int, default=512)
    args = parser.parse_args()
    base = prepare_base()
    root = ROOT / "training/data"
    root.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(
            f"https://huggingface.co/api/datasets/{DATA_REPO}/tree/{DATA_REVISION}/plain_text"
        )
        response.raise_for_status()
        metadata = {r["path"]: r for r in response.json()}
    sources, pool = {}, {}
    for split in ("train", "validation", "test"):
        name = f"plain_text/{split}-00000-of-00001.parquet"
        expected = metadata[name]["lfs"]["oid"]
        path = root / (split + ".parquet")
        sources[split] = download(
            f"https://huggingface.co/datasets/{DATA_REPO}/resolve/{DATA_REVISION}/{name}",
            path,
            expected=expected,
        )
        pool[split] = triples(pq.read_table(path).to_pylist(), random.Random(2233))
    # Official partitions first, then remove exact normalized text overlap in the actual run.
    test, test_text = choose(pool["test"], args.test, set())
    val, val_text = choose(pool["validation"], args.validation, test_text)
    train, train_text = choose(pool["train"], args.train, test_text | val_text)
    assert not (train_text & test_text or train_text & val_text or test_text & val_text)
    selected = {"train": train, "validation": val, "test": test}
    files = {}
    for split, rows in selected.items():
        path = root / (split + ".jsonl")
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        files[split] = {"records": len(rows), "sha256": digest(path)}
    manifest = {
        "dataset": DATA_REPO,
        "revision": DATA_REVISION,
        "license": "CC-BY-SA-4.0",
        "source": "https://nlp.stanford.edu/projects/snli/",
        "seed": 2233,
        "files": files,
        "downloads": sources,
        "normalized_cross_split_text_overlap": 0,
        "limitations": [
            "The pretrained baseline may already have encountered SNLI through AllNLI.",
            "These are sentence-entailment retrieval labels, not webpage usefulness judgments.",
            "Only a bounded subset is used; the full SNLI corpus is not trained in this run.",
        ],
        "base_source_sha256": hashlib.sha256(
            (base / "source_manifest.json").read_bytes()
        ).hexdigest(),
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"prepared": files, "cross_split_text_overlap": 0}), flush=True)


if __name__ == "__main__":
    main()

"""Evaluate the exact deployment artifacts without training or checkpoint selection."""

import json
import sys

import numpy as np
from common import ROOT, digest

sys.path.insert(0, str(ROOT / "backend"))
from lists_api.semantic import MiniLMEncoder  # noqa: E402


def evaluate(encoder, rows):
    corpus = list(dict.fromkeys(t for row in rows for t in (row["positive"], row["negative"])))
    index = {text: i for i, text in enumerate(corpus)}
    vectors = encoder.encode(corpus)
    queries = encoder.encode([row["anchor"] for row in rows])
    scores = queries @ vectors.T
    ranks, paired = [], []
    for i, row in enumerate(rows):
        positive, negative = index[row["positive"]], index[row["negative"]]
        order = np.argsort(-scores[i], kind="stable")
        ranks.append(int(np.flatnonzero(order == positive)[0]) + 1)
        paired.append(scores[i, positive] > scores[i, negative])
    reciprocal = np.array([1 / rank if rank <= 10 else 0 for rank in ranks])
    return {
        "queries": len(rows),
        "candidates": len(corpus),
        "mrr_at_10": float(reciprocal.mean()),
        "recall_at_10": float(np.mean(np.array(ranks) <= 10)),
        "top_1_accuracy": float(np.mean(np.array(ranks) == 1)),
        "positive_over_contradiction": float(np.mean(paired)),
    }, {"ranks": ranks, "reciprocal_at_10": reciprocal.tolist()}


def main():
    source = ROOT / "training/data/test.jsonl"
    report = json.loads((ROOT / "model_artifacts/snli-lora-v1/training_report.json").read_text())
    if digest(source) != report["dataset_manifest"]["files"]["test"]["sha256"]:
        raise ValueError("Held-out data checksum mismatch")
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    results, detail = {}, {}
    for variant, directory in (("baseline", "minilm"), ("fine_tuned", "snli-lora-v1")):
        encoder = MiniLMEncoder(str(ROOT / "models" / directory))
        metrics, query_details = evaluate(encoder, rows)
        results[variant] = {"model_id": encoder.model_id, "sha256": encoder.model_sha256, **metrics}
        detail[variant] = query_details
        print(json.dumps({variant: results[variant]}), flush=True)
    difference = np.array(detail["fine_tuned"]["reciprocal_at_10"]) - np.array(
        detail["baseline"]["reciprocal_at_10"]
    )
    rng = np.random.default_rng(2233)
    samples = difference[rng.integers(0, len(difference), (2000, len(difference)))].mean(1)
    results.update(
        evaluation="SNLI held-out retrieval using the exact deployed INT8 artifacts",
        checkpoint_selection="Fixed validation-selected adapter; no selection on this evaluation",
        test_sha256=digest(source),
        inference_max_tokens=256,
        test_mrr_at_10_difference=float(difference.mean()),
        paired_bootstrap_95_percent_interval=np.quantile(samples, [0.025, 0.975]).tolist(),
        limitations=report["limitations"],
    )
    artifact = ROOT / "model_artifacts/snli-lora-v1"
    (artifact / "deployment_evaluation.json").write_text(json.dumps(results, indent=2) + "\n")
    (artifact / "deployment_metrics_by_query.json").write_text(json.dumps(detail, indent=2) + "\n")
    print(
        json.dumps(
            {
                "difference": results["test_mrr_at_10_difference"],
                "interval": results["paired_bootstrap_95_percent_interval"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

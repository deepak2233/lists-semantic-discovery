"""Reconstruct which verified training records the selected checkpoint actually saw."""

import json
import random

from common import ROOT, digest
from train import batches, normalize, read_split


def main():
    artifact = ROOT / "model_artifacts/snli-lora-v1"
    report = json.loads((artifact / "training_report.json").read_text())
    assert digest(ROOT / "training/train.py") == report["training_source_sha256"]
    assert digest(artifact / "adapter_model.safetensors") == report["adapter_sha256"]
    assert (
        digest(ROOT / "training/data/train.jsonl")
        == report["dataset_manifest"]["files"]["train"]["sha256"]
    )
    rows = read_split("train")
    plans = [
        batch
        for epoch in range(report["epochs"])
        for batch in batches(rows, report["batch_size"], random.Random(report["seed"] + epoch))
    ]
    selected = [r for batch in plans[: report["selected_checkpoint_update"]] for r in batch]
    assert len(plans) == report["optimizer_updates"]
    assert sum(map(len, plans)) == report["processed_triplets"]
    audit = {
        "adapter_sha256": report["adapter_sha256"],
        "training_source_sha256": report["training_source_sha256"],
        "training_data_sha256": report["dataset_manifest"]["files"]["train"]["sha256"],
        "experiment_processed_triplets": report["processed_triplets"],
        "experiment_optimizer_updates": report["optimizer_updates"],
        "selected_checkpoint_update": report["selected_checkpoint_update"],
        "selected_checkpoint_processed_triplets": len(selected),
        "selected_checkpoint_distinct_anchors": len({normalize(r["anchor"]) for r in selected}),
        "method": (
            "Post-run reconstruction of the seeded batches; original training source unchanged"
        ),
    }
    (artifact / "selection_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit))


if __name__ == "__main__":
    main()

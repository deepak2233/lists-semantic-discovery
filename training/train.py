"""Actually fine-tune MiniLM query/value LoRA weights on pinned, human-labelled SNLI data."""

import argparse
import hashlib
import importlib.metadata
import json
import random
import time

import numpy as np
import torch
import torch.nn.functional as F
from common import BASE_REPO, BASE_REVISION, ROOT, digest, normalize
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModel, AutoTokenizer


def read_split(split):
    path = ROOT / "training/data" / (split + ".jsonl")
    return [json.loads(line) for line in path.read_text().splitlines()]


def pooled(model, tokenizer, texts, max_length):
    inputs = tokenizer(
        texts, padding=True, truncation=True, max_length=max_length, return_tensors="pt"
    )
    hidden = model(**inputs).last_hidden_state
    weights = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
    value = (hidden * weights).sum(1) / weights.sum(1).clamp(min=1e-9)
    return F.normalize(value, p=2, dim=1)


def evaluate(model, tokenizer, rows, batch_size=32):
    model.eval()
    corpus = list(dict.fromkeys(t for r in rows for t in (r["positive"], r["negative"])))
    index = {text: i for i, text in enumerate(corpus)}
    with torch.inference_mode():
        vectors = torch.cat(
            [
                pooled(model, tokenizer, corpus[i : i + batch_size], 128)
                for i in range(0, len(corpus), batch_size)
            ]
        )
        queries = torch.cat(
            [
                pooled(model, tokenizer, [r["anchor"] for r in rows[i : i + batch_size]], 128)
                for i in range(0, len(rows), batch_size)
            ]
        )
        scores = (queries @ vectors.T).numpy()
    ranks, correct_pair = [], []
    for i, row in enumerate(rows):
        pos, neg = index[row["positive"]], index[row["negative"]]
        # Stable corpus-order tie breaking, same for baseline and the adapted model.
        order = np.argsort(-scores[i], kind="stable")
        ranks.append(int(np.flatnonzero(order == pos)[0]) + 1)
        correct_pair.append(float(scores[i, pos] > scores[i, neg]))
    reciprocal = np.array([1 / rank if rank <= 10 else 0 for rank in ranks])
    return {
        "queries": len(rows),
        "candidates": len(corpus),
        "mrr_at_10": float(reciprocal.mean()),
        "recall_at_10": float(np.mean(np.array(ranks) <= 10)),
        "top_1_accuracy": float(np.mean(np.array(ranks) == 1)),
        "positive_over_contradiction": float(np.mean(correct_pair)),
    }, {"ranks": ranks, "reciprocal_at_10": reciprocal.tolist()}


def frozen_digest(model):
    digest = hashlib.sha256()
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            digest.update(name.encode())
            digest.update(parameter.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def batches(rows, batch_size, rng):
    remaining = rows[:]
    rng.shuffle(remaining)
    result, batch, used = [], [], set()
    for row in remaining:
        terms = {normalize(row[k]) for k in ("anchor", "positive", "negative")}
        if terms & used:
            result.append(row)
            continue
        batch.append(row)
        used.update(terms)
        if len(batch) == batch_size:
            yield batch
            batch, used = [], set()
    if len(batch) >= 2:
        yield batch
    # Deferred collisions are reported as unused, rather than called trained examples.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=0.0002)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=64)
    args = parser.parse_args()
    seed = 2233
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    base = ROOT / "models/minilm-pytorch"
    tokenizer = AutoTokenizer.from_pretrained(base, local_files_only=True)
    original = AutoModel.from_pretrained(base, local_files_only=True, attn_implementation="eager")
    model = get_peft_model(
        original,
        LoraConfig(
            task_type=TaskType.FEATURE_EXTRACTION,
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=["query", "value"],
            bias="none",
        ),
    )
    frozen_before = frozen_digest(model)
    params = [p for p in model.parameters() if p.requires_grad]
    trainable = sum(p.numel() for p in params)
    optimizer = torch.optim.AdamW(params, lr=args.learning_rate, weight_decay=0.01)
    train, validation, test = [read_split(s) for s in ("train", "validation", "test")]
    plans = [
        list(batches(train, args.batch_size, random.Random(seed + epoch)))
        for epoch in range(args.epochs)
    ]
    total = sum(map(len, plans))
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda step: min((step + 1) / 32, max(0.0, (total - step) / max(1, total - 32)))
    )
    artifact = ROOT / "model_artifacts/snli-lora-v1"
    artifact.mkdir(parents=True, exist_ok=True)
    with model.disable_adapter():
        base_val, _ = evaluate(model, tokenizer, validation)
    print(
        json.dumps(
            {
                "event": "started",
                "trainable_parameters": trainable,
                "planned_updates": total,
                "baseline_validation": base_val,
            }
        ),
        flush=True,
    )
    started, step, processed = time.perf_counter(), 0, 0
    history, validation_history, seen = [], [], set()
    best, best_step = -1.0, 0
    for plan in plans:
        for rows in plan:
            model.train()
            texts = [r[k] for k in ("anchor", "positive", "negative") for r in rows]
            vector = pooled(model, tokenizer, texts, args.max_length)
            size = len(rows)
            query, positive, negative = vector[:size], vector[size : 2 * size], vector[2 * size :]
            logits = query @ torch.cat([positive, negative]).T * 20
            loss = F.cross_entropy(logits, torch.arange(size))
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            optimizer.step()
            scheduler.step()
            step += 1
            processed += size
            seen.update(normalize(r["anchor"]) for r in rows)
            history.append(float(loss.detach()))
            if step % 32 == 0:
                print(
                    json.dumps(
                        {
                            "event": "training",
                            "step": step,
                            "total": total,
                            "mean_recent_loss": float(np.mean(history[-32:])),
                            "elapsed_seconds": round(time.perf_counter() - started, 1),
                        }
                    ),
                    flush=True,
                )
            if step % 128 == 0 or step == total:
                metrics, _ = evaluate(model, tokenizer, validation)
                validation_history.append({"step": step, **metrics})
                print(json.dumps({"event": "validation", "step": step, **metrics}), flush=True)
                if metrics["mrr_at_10"] > best:
                    best, best_step = metrics["mrr_at_10"], step
                    model.save_pretrained(artifact, safe_serialization=True)
    frozen_unchanged = frozen_before == frozen_digest(model)
    # Select on validation only. Test labels have not been evaluated or used for selection.
    from peft import PeftModel

    original = AutoModel.from_pretrained(base, local_files_only=True, attn_implementation="eager")
    model = PeftModel.from_pretrained(original, artifact)
    with model.disable_adapter():
        baseline_test, baseline_detail = evaluate(model, tokenizer, test)
    tuned_test, tuned_detail = evaluate(model, tokenizer, test)
    difference = np.array(tuned_detail["reciprocal_at_10"]) - np.array(
        baseline_detail["reciprocal_at_10"]
    )
    rng = np.random.default_rng(seed)
    estimates = difference[rng.integers(0, len(difference), (2000, len(difference)))].mean(1)
    config_path = artifact / "adapter_config.json"
    config = json.loads(config_path.read_text())
    config["base_model_name_or_path"] = BASE_REPO
    config["revision"] = BASE_REVISION
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    metadata = {
        "experiment": "lists-snli-lora-v1",
        "base_repository": BASE_REPO,
        "base_revision": BASE_REVISION,
        "seed": seed,
        "device": "CPU",
        "objective": (
            "InfoNCE / multiple-negatives cross-entropy with in-batch "
            "and labelled contradiction negatives"
        ),
        "lora": {"rank": 8, "alpha": 16, "dropout": 0.05, "targets": ["query", "value"]},
        "trainable_parameters": trainable,
        "frozen_parameters_unchanged": frozen_unchanged,
        "optimizer": "AdamW",
        "learning_rate": args.learning_rate,
        "weight_decay": 0.01,
        "warmup_updates": 32,
        "batch_size": args.batch_size,
        "train_max_tokens": args.max_length,
        "epochs": args.epochs,
        "optimizer_updates": step,
        "processed_triplets": processed,
        "distinct_training_anchors_seen": len(seen),
        "selected_checkpoint_update": best_step,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "loss_first_32": float(np.mean(history[:32])),
        "loss_last_32": float(np.mean(history[-32:])),
        "baseline_validation": base_val,
        "validation_history": validation_history,
        "baseline_test": baseline_test,
        "fine_tuned_test": tuned_test,
        "test_mrr_at_10_difference": float(difference.mean()),
        "paired_bootstrap_95_percent_interval": np.quantile(estimates, [0.025, 0.975]).tolist(),
        "dataset_manifest": json.loads((ROOT / "training/data/manifest.json").read_text()),
        "adapter_sha256": digest(artifact / "adapter_model.safetensors"),
        "training_source_sha256": digest(__file__),
        "software": {
            p: importlib.metadata.version(p)
            for p in ("torch", "transformers", "peft", "numpy", "pyarrow", "safetensors")
        },
        "limitations": [
            (
                "Baseline pretraining may include SNLI/AllNLI; "
                "this does not establish unseen-domain quality."
            ),
            "The task is sentence entailment retrieval, not live-web usefulness or generation.",
            "The model does not create or discover URLs outside the candidate provider.",
        ],
    }
    assert frozen_unchanged and step > 0 and trainable > 0
    (artifact / "training_report.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (artifact / "test_metrics_by_query.json").write_text(
        json.dumps({"baseline": baseline_detail, "fine_tuned": tuned_detail}, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "event": "completed",
                "report": str(artifact / "training_report.json"),
                "baseline_test": baseline_test,
                "fine_tuned_test": tuned_test,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

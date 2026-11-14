"""Merge the small trained LoRA artifact into pinned base weights and export CPU ONNX."""

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from common import BASE_REPO, BASE_REVISION, ROOT, digest, prepare_base
from onnxruntime.quantization import QuantType, quantize_dynamic
from safetensors.torch import load_file
from transformers import AutoModel, AutoTokenizer


def strip_doc_strings(message):
    """Remove exporter source paths using protobuf's supported repeated-field API."""
    if "doc_string" in message.DESCRIPTOR.fields_by_name:
        message.ClearField("doc_string")
    for field, value in message.ListFields():
        if field.message_type is not None:
            if field.is_repeated:
                for child in value:
                    strip_doc_strings(child)
            else:
                strip_doc_strings(value)


def merge_adapter(model, artifact):
    config = json.loads((artifact / "adapter_config.json").read_text())
    if (
        config["r"] != 8
        or config["lora_alpha"] != 16
        or config.get("use_rslora")
        or config.get("use_dora")
        or config.get("bias") != "none"
    ):
        raise ValueError("Only the reviewed rank-8 query/value adapter is supported")
    weights = load_file(artifact / "adapter_model.safetensors")
    changed = 0
    for name, value in weights.items():
        if not name.endswith(".lora_A.weight"):
            continue
        prefix = name.removesuffix(".lora_A.weight")
        target = prefix.removeprefix("base_model.model.")
        if not target.endswith((".query", ".value")):
            raise ValueError("Unexpected LoRA target")
        layer = model.get_submodule(target)
        left = weights[prefix + ".lora_B.weight"].numpy().astype(np.float64)
        right = value.numpy().astype(np.float64)
        original = layer.weight.detach().numpy().astype(np.float64)
        delta = np.zeros_like(original)
        # Fixed-order float64 accumulation avoids platform BLAS ordering in merged weights.
        for k in range(config["r"]):
            delta += left[:, k, None] * right[k, None, :]
        merged = (original + delta * config["lora_alpha"] / config["r"]).astype(np.float32)
        if not np.isfinite(merged).all():
            raise ValueError("Invalid merged weights")
        with torch.no_grad():
            layer.weight.copy_(torch.from_numpy(merged))
        changed += 1
    if changed != 12 or len(weights) != 24:
        raise ValueError("Expected query and value adapters in all six transformer layers")


class HiddenStates(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask, token_type_ids):
        return self.model(
            input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids
        ).last_hidden_state


def export(model, tokenizer, base, root, model_id, report, check_catalog):
    wrapped = HiddenStates(model.eval())
    root.mkdir(parents=True, exist_ok=True)
    sample = tokenizer(
        ["An engineer reviews a public article.", "Two people are reading."],
        return_tensors="pt",
        padding=True,
    )
    names = ["input_ids", "attention_mask", "token_type_ids"]
    target = root / "model.onnx"
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    with tempfile.TemporaryDirectory(prefix="lists-export-") as directory:
        fp32 = str(Path(directory) / "float.onnx")
        with torch.inference_mode():
            expected = wrapped(*(sample[n] for n in names)).numpy()
            torch.onnx.export(
                wrapped,
                tuple(sample[n] for n in names),
                fp32,
                input_names=names,
                output_names=["last_hidden_state"],
                opset_version=17,
                dynamo=False,
                dynamic_axes={
                    n: {0: "batch", 1: "sequence"} for n in names + ["last_hidden_state"]
                },
                do_constant_folding=True,
                external_data=False,
            )
        graph = onnx.load(fp32)
        strip_doc_strings(graph)
        onnx.checker.check_model(graph)
        onnx.save(graph, fp32)
        session = ort.InferenceSession(
            fp32, sess_options=options, providers=["CPUExecutionProvider"]
        )
        inputs = {n: sample[n].numpy() for n in names}
        actual = session.run(None, inputs)[0]
        maximum_error = float(np.max(np.abs(actual - expected)))
        if not np.allclose(actual, expected, rtol=1e-4, atol=3e-5):
            raise ValueError(f"FP32 ONNX parity check failed: {maximum_error}")
        del session
        # Same fixed quantization for the control and the adapted encoder; no test-set tuning.
        quantize_dynamic(
            fp32,
            target,
            weight_type=QuantType.QUInt8,
            per_channel=False,
            reduce_range=False,
            op_types_to_quantize=["MatMul", "Gather"],
        )
    graph = onnx.load(target)
    strip_doc_strings(graph)
    onnx.checker.check_model(graph)
    # Quantization traverses sets internally. Canonicalize independent initializers.
    initializers = sorted(graph.graph.initializer, key=lambda value: value.name)
    del graph.graph.initializer[:]
    graph.graph.initializer.extend(initializers)
    onnx.save(graph, target)
    quantized = ort.InferenceSession(
        str(target), sess_options=options, providers=["CPUExecutionProvider"]
    )
    hidden = quantized.run(None, inputs)[0]
    mask = inputs["attention_mask"][..., None].astype(np.float32)

    def embedding(values):
        result = (values * mask).sum(1) / mask.sum(1)
        return result / np.linalg.norm(result, axis=1, keepdims=True)

    parity = float((embedding(hidden) * embedding(expected)).sum(1).min())
    if not np.isfinite(hidden).all() or parity < 0.98:
        raise ValueError(f"Quantized embedding parity failed: {parity}")
    shutil.copyfile(base / "tokenizer.json", root / "tokenizer.json")
    for name in ("README.md", "LICENSE"):
        shutil.copyfile(ROOT / "model_artifacts/upstream-minilm" / name, root / ("BASE_" + name))
    if model_id == "minilm-snli-lora-v1":
        shutil.copyfile(ROOT / "model_artifacts/snli-lora-v1/LICENSE", root / "ADAPTER_LICENSE")
    checksums = {n: digest(root / n) for n in ("model.onnx", "tokenizer.json")}
    if check_catalog:
        catalog = json.loads((ROOT / "backend/lists_api/data/model_catalog.json").read_text())
        if checksums != catalog[model_id]["sha256"]:
            raise ValueError(f"Export differs from reviewed model catalog: {model_id}")
    manifest = {
        "model_id": model_id,
        "repository": BASE_REPO,
        "revision": BASE_REVISION,
        "sha256": checksums,
        "dimensions": 384,
        "max_tokens": 256,
        "pooling": "attention-mask mean + L2 normalization",
        "quantization": "dynamic QUInt8 MatMul and Gather; per-tensor; full range",
        "onnx_fp32_maximum_absolute_error": maximum_error,
        "quantized_sample_minimum_embedding_cosine": parity,
        "onnx_bytes": target.stat().st_size,
    }
    if model_id == "minilm-snli-lora-v1":
        audit = json.loads((ROOT / "model_artifacts/snli-lora-v1/selection_audit.json").read_text())
        if audit["adapter_sha256"] != report["adapter_sha256"]:
            raise ValueError("Checkpoint exposure audit does not match the trained adapter")
        manifest.update(
            adapter_sha256=report["adapter_sha256"],
            training_dataset=report["dataset_manifest"]["dataset"],
            training_examples=audit["selected_checkpoint_processed_triplets"],
            experiment_training_examples=report["processed_triplets"],
        )
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-catalog", action="store_true")
    args = parser.parse_args()
    if os.getenv("PYTHONHASHSEED") != "2233":
        raise ValueError("Start export with PYTHONHASHSEED=2233 for reproducible quantization")
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    artifact = ROOT / "model_artifacts/snli-lora-v1"
    report = json.loads((artifact / "training_report.json").read_text())
    if digest(artifact / "adapter_model.safetensors") != report["adapter_sha256"]:
        raise ValueError("Trained adapter checksum mismatch")
    base = prepare_base()
    tokenizer = AutoTokenizer.from_pretrained(base, local_files_only=True)
    model = AutoModel.from_pretrained(base, local_files_only=True, attn_implementation="eager")
    export(model, tokenizer, base, ROOT / "models/minilm", "minilm-q8", report, args.check_catalog)
    merge_adapter(model, artifact)
    export(
        model,
        tokenizer,
        base,
        ROOT / "models/snli-lora-v1",
        "minilm-snli-lora-v1",
        report,
        args.check_catalog,
    )


if __name__ == "__main__":
    main()

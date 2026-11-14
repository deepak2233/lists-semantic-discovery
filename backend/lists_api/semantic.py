"""CPU ONNX inference. Load only local, checksum-verified artifacts; no runtime downloads."""

import hashlib
import json
from importlib.resources import files
from pathlib import Path

MODEL_REPO = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_SHA256 = "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"


class MiniLMEncoder:
    def __init__(self, directory: str) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        root = Path(directory)
        manifest = json.loads((root / "manifest.json").read_text())
        if manifest.get("revision") != MODEL_REVISION:
            raise ValueError("Unexpected model revision")
        for filename in ("tokenizer.json", "model.onnx"):
            actual = hashlib.sha256((root / filename).read_bytes()).hexdigest()
            if actual != manifest["sha256"][filename]:
                raise ValueError("Model artifact checksum mismatch")
        model_id = manifest.get("model_id", "minilm")
        adapter_sha256 = None
        expected = MODEL_SHA256
        if model_id != "minilm":
            catalog = json.loads(files("lists_api").joinpath("data/model_catalog.json").read_text())
            entry = catalog.get(model_id)
            if not entry or manifest["sha256"] != entry["sha256"]:
                raise ValueError("Unreviewed adapted model")
            expected = entry["sha256"]["model.onnx"]
            adapter_sha256 = entry.get("adapter_sha256")
        if manifest["sha256"]["model.onnx"] != expected:
            raise ValueError("Unreviewed model weights")
        self.adapter_sha256 = adapter_sha256
        self.model_id = model_id
        self.model_sha256 = expected
        self.tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(root / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.input_names = {i.name for i in self.session.get_inputs()}

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
        batch_size: int = 16,
    ):
        import numpy as np

        outputs = []
        for start in range(0, len(texts), batch_size):
            encoded = self.tokenizer.encode_batch(texts[start : start + batch_size])
            ids = np.array([e.ids for e in encoded], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            inputs = {
                "input_ids": ids,
                "attention_mask": mask,
                "token_type_ids": np.array([e.type_ids for e in encoded], dtype=np.int64),
            }
            hidden = self.session.run(
                None, {k: v for k, v in inputs.items() if k in self.input_names}
            )[0]
            if hidden.ndim != 3 or hidden.shape[-1] != 384:
                raise ValueError("Unexpected model output dimensions")
            weights = mask[..., None].astype(np.float32)
            pooled = (hidden * weights).sum(axis=1) / weights.sum(axis=1).clip(min=1e-9)
            if normalize_embeddings:
                pooled /= np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
            outputs.append(pooled)
        return np.concatenate(outputs, axis=0)

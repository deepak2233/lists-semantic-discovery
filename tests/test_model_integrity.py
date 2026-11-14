"""Model allowlisting must reject edited and unreviewed deployment artifacts."""

import hashlib
import json

import pytest
from lists_api.semantic import MODEL_REVISION, MiniLMEncoder


@pytest.mark.parametrize("model_id", ["minilm-q8", "minilm-snli-lora-v1", "unknown-model"])
def test_self_signed_artifacts_cannot_bypass_reviewed_catalog(tmp_path, model_id):
    checksums = {}
    for name in ("model.onnx", "tokenizer.json"):
        payload = b"unreviewed but self-consistent artifact"
        (tmp_path / name).write_bytes(payload)
        checksums[name] = hashlib.sha256(payload).hexdigest()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "model_id": model_id,
                "revision": MODEL_REVISION,
                "sha256": checksums,
            }
        )
    )
    with pytest.raises(ValueError, match="Unreviewed"):
        MiniLMEncoder(str(tmp_path))

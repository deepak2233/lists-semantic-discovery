# Fine-tuning MiniLM for LISTS

Actual CPU experiment completed on 14 November 2026 (Asia/Kolkata). This repository includes trained LoRA weights, measured evaluation reports and reproducible export commands. It does not claim a production-quality improvement in webpage recommendation.

## Dataset and permission

We use [Stanford Natural Language Inference (SNLI)](https://nlp.stanford.edu/projects/snli/), a public, human-labelled sentence-pair dataset, distributed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Dataset authors: Samuel R. Bowman, Gabor Angeli, Christopher Potts and Christopher D. Manning. Paper: [A large annotated corpus for learning natural language inference](https://aclanthology.org/D15-1075/), EMNLP 2015.

The pinned mirror is [`stanfordnlp/snli`](https://huggingface.co/datasets/stanfordnlp/snli/tree/cdb5c3d5eed6ead6e5a341c8e56e669bb666725b), revision `cdb5c3d5eed6ead6e5a341c8e56e669bb666725b`. The original corpus contains approximately 570,000 sentence pairs. This run uses a bounded subset, not the entire dataset.

| Partition | Triplets actually used | Role |
| --- | ---: | --- |
| Train | 8,192 | Optimizer updates |
| Validation | 512 | Select the checkpoint |
| Test | 512 | Report after selection |

Each premise is an anchor, an entailment hypothesis is a positive, and a contradiction hypothesis is an explicit negative. Neutral and unlabelled examples are excluded. We first respect the official partitions, then remove exact overlap after case-folding and whitespace normalization. This run has zero normalized exact-text overlap across the three selected partitions. This is not a semantic-duplicate guarantee.

The published MiniLM baseline already used AllNLI upstream. SNLI exposure during pretraining cannot be excluded. These test results therefore measure a bounded adaptation experiment, not generalization to a proven unseen dataset. The labels measure sentence entailment retrieval, not whether someone would find a recommended webpage useful.

## Model and training technique

Base encoder: [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/README.md), pinned revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Its publisher labels the weights Apache-2.0. LISTS trains actual transformer query/value adapters, not a UI simulation or a renamed pretrained checkpoint.

| Setting | Executed value |
| --- | --- |
| Adapter | LoRA, query and value projections in all six transformer layers |
| Trainable parameters | 73,728; original base parameters frozen and verified unchanged |
| Rank / alpha / dropout | 8 / 16 / 0.05 |
| Loss | Contrastive cross-entropy with in-batch positives and explicit contradiction negatives |
| Similarity | Mean-pooled, L2-normalized vectors; dot product scaled by 20 during training |
| Optimizer | AdamW; learning rate 0.0002; weight decay 0.01 |
| Schedule | 32 warmup updates, then linear decay; gradient clipping 1.0 |
| Batch / epochs / updates | 16 triplets / 1 / 512 |
| Selected checkpoint | Update 256, selected by validation MRR@10 |
| Token limits | Training 64; training evaluation 128; deployed inference 256 |
| Seed | 2233 |
| Hardware | CPU, four training threads; no GPU used |
| Measured run duration | 452.12 seconds, including validation and final evaluation |

The full experiment processed 8,192 triplets, but the served checkpoint was selected at update 256 and had seen **4,096 triplets**. The [checkpoint exposure audit](../model_artifacts/snli-lora-v1/selection_audit.json) reconstructs those batches from the frozen source and dataset hashes. Later updates were evaluated and discarded.

Training uses PyTorch 2.8.0+cpu, Transformers 4.57.6 and PEFT 0.18.0, with a separate [locked environment](../training/uv.lock). Those libraries are not deployed in the inference function. The [executed source](../training/train.py) SHA-256 is recorded in the report. Training loss was 0.2844 over the first 32 updates and 0.2820 over the last 32; this is not evidence of a large learning gain.

## Measured results

All columns below use the same 512 test anchors and 1,019 deduplicated candidate hypothesis strings. Each query has one selected labelled positive; other potentially relevant hypotheses are not exhaustively judged. Retrieval uses the whole candidate pool with stable tie breaking. This is not a benchmark over the 44 webpage demo records.

| Metric | Pretrained FP32 | Adapted FP32 | Deployed pretrained INT8 | Deployed adapted INT8 |
| --- | ---: | ---: | ---: | ---: |
| MRR@10 | 0.7911 | 0.7987 | 0.7877 | 0.7909 |
| Recall@10 | 0.9570 | 0.9590 | 0.9453 | 0.9551 |
| Top-1 accuracy | 0.6895 | 0.7051 | 0.6914 | 0.6973 |
| Positive over contradiction | 0.9453 | 0.9531 | 0.9414 | 0.9492 |

The FP32 paired MRR@10 difference is **+0.00755**, with a 2,000-sample paired-bootstrap 95% interval **[-0.00333, +0.01949]**. The deployed INT8 difference is **+0.00320**, interval **[-0.00935, +0.01606]**. Both intervals include zero. We cannot claim a statistically established improvement. Pretrained MiniLM remains the automatic default; the SNLI model is an explicit experimental option.

The INT8 configuration was fixed before evaluating those deployment artifacts. Both models receive identical dynamic unsigned 8-bit quantization for MatMul and Gather, per-tensor and full range. Each model is 22,843,905 bytes. The exporter checks FP32 ONNX output against the merged Torch model, then checks quantized sample embedding agreement. Two repeated exports produced identical catalog checksums. Quantization changes scores and has a small measured quality cost; the deployed scores must not be represented by the more favorable FP32 numbers.

On the eight authored webpage regression fixtures, INT8 NDCG@10 is 0.9127 for the control and 0.9095 for the adaptation; recall is unchanged at 0.8756. These fixtures were authored with the candidate collection and are not an independent benchmark. They provide no reason to replace the default.

Machine-readable evidence:

- [Training report, dataset hashes and validation history](../model_artifacts/snli-lora-v1/training_report.json)
- [FP32 per-query ranks](../model_artifacts/snli-lora-v1/test_metrics_by_query.json)
- [Exact deployment evaluation](../model_artifacts/snli-lora-v1/deployment_evaluation.json)
- [Deployment per-query ranks](../model_artifacts/snli-lora-v1/deployment_metrics_by_query.json)
- [Reviewed model catalog and checksums](../backend/lists_api/data/model_catalog.json)
- [Trained adapter and model card](../model_artifacts/snli-lora-v1/)

## Reproduce the actual experiment

Linux x86-64 and Python 3.12 are the supported training/export environment. The CPU environment needs about 2 GB of disk space; downloads require access to Hugging Face and the PyTorch CPU wheel index. Raw dataset files are not committed.

```bash
uv sync --frozen --extra dev
UV_PROJECT_ENVIRONMENT="$PWD/.venv-training" uv sync --project training --frozen --no-install-project
.venv-training/bin/python training/prepare_data.py
.venv-training/bin/python -u training/train.py
.venv-training/bin/python training/audit_checkpoint.py
PYTHONHASHSEED=2233 .venv-training/bin/python training/export_model.py --check-catalog
.venv-training/bin/python training/evaluate_export.py
uv run --no-sync python scripts/verify_web.py --model-path models/minilm
```

Retraining writes to `model_artifacts/snli-lora-v1`. Use a separate checkout for a new experiment. The catalog check deliberately fails if a new checkpoint produces different model bytes; review a new experiment and update its evaluation before registering it. Training reproducibility is not a promise of bitwise identical optimizer results on every CPU. Exporting the committed checkpoint is deterministic in the pinned environment.

For inference from the committed adapter without retraining:

```bash
uv run --no-sync python scripts/build_vercel.py
uv run --no-sync python scripts/dev_web.py --port 8000
```

This downloads the pinned base, merges the committed adapter and exports the two reviewed INT8 encoders during the build. No dataset, optimizer or training job runs during deployment or requests. Inference uses ONNX Runtime, NumPy and Tokenizers only.

## Generate inference with your own text

Open the [model comparison page](https://lists-semantic-discovery.vercel.app/#model-lab), paste two English passages and run the comparison. You receive actual baseline and adapted cosine scores, a request ID, the deployed model SHA-256 and the trained adapter SHA-256. This endpoint is independent of the fixed webpage corpus.

```bash
curl http://127.0.0.1:8000/v1/compare \
  -H 'Content-Type: application/json' \
  -d '{"text_a":"An engineer adds request deadlines to a Python API.","text_b":"A developer configures service timeouts."}'
```

To use the trained model in webpage ranking, select **Fine-tuned · SNLI LoRA**, or submit `"ranking": "fine_tuned"` to `/v1/recommend`. The API returns `409` if the trained model is unavailable; it does not silently substitute a baseline. Existing origin, authentication, admission and input controls also apply to comparison requests.

## What this does and does not deliver

This delivers a real trained checkpoint and working embedding inference. It does not generate article text, learn a personal browsing profile or create new URLs. The hosted recommendation provider still contains 44 explicitly authored technical-resource records. Live web discovery still requires the implemented search provider to be configured, or a maintained authorized index. Fine-tuning cannot replace candidate retrieval.

The own-text comparison accepts up to 1,800 characters per passage and truncates inference at 256 tokens. English is the supported language. Cosine scores are not calibrated probabilities, correctness judgments or proof that the adapted model is better. Website usefulness must be evaluated with independent article-to-page judgments before promoting this option to the default.

## Attribution and artifact licensing

Source code remains under the root MIT license. The adapter and SNLI-derived evaluation artifacts in `model_artifacts/snli-lora-v1` are offered under CC BY-SA 4.0, with dataset authors credited above and modifications identified as LISTS triplet preparation, LoRA training and retrieval evaluation. See that directory's license notice. Reconstructed model weights also retain the upstream MiniLM Apache-2.0 notices. Dataset licensing is documented separately from code licensing; this is not a legal determination about model-weight derivatives.

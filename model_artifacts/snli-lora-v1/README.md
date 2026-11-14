---
language: en
license: cc-by-sa-4.0
base_model: sentence-transformers/all-MiniLM-L6-v2
datasets:
  - stanfordnlp/snli
library_name: peft
pipeline_tag: sentence-similarity
---

# LISTS MiniLM SNLI LoRA v1

Actual rank-8 query/value LoRA adapter with 73,728 trainable parameters. The experiment processed 8,192 human-labelled SNLI triplets; the served checkpoint was selected at update 256 after seeing 4,096 triplets. One CPU epoch, 512 optimizer updates; checkpoint 256 selected using 512 validation anchors. The base encoder was frozen.

See [the complete training and inference record](../../docs/FINE_TUNING.md) for the exact method, dataset revision, source attribution, reproduction commands, hashes and limitations.

On 512 held-out SNLI retrieval queries, FP32 MRR@10 changes from 0.7911 to 0.7987. After identical deployment quantization it changes from 0.7877 to 0.7909. Both paired confidence intervals include zero. This does not establish improved general-web recommendations. Baseline pretraining may have included SNLI through AllNLI.

Use the supplied deterministic exporter to merge this adapter into the exact pinned MiniLM revision. The adapter is not a standalone encoder. Training and inference use mean pooling and L2 normalization. Deployed inference is capped at 256 tokens. Scores are not probabilities.

SNLI: Samuel R. Bowman, Gabor Angeli, Christopher Potts and Christopher D. Manning, 2015. CC BY-SA 4.0. Modifications: LISTS triplet preparation, adapter training and retrieval evaluation. Base MiniLM: Apache-2.0, with its publisher's notices retained. Adapter and dataset-derived reports: CC BY-SA 4.0. Source code: root MIT license.

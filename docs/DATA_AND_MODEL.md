# Data sources, model provenance and training status

Updated on 14 November 2026 (Asia/Kolkata). LISTS now includes an actual SNLI LoRA fine-tuning experiment and an explicit trained-model inference option. The earlier version only reused pretrained weights. The full [training record](FINE_TUNING.md) distinguishes those versions.

## What this project actually uses

| Component | Actual source | Purpose | Training performed here |
| --- | --- | --- | --- |
| Pretrained control | [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | Encode reviewed text and candidate descriptions | None for this control; reuse published weights |
| SNLI LoRA adaptation | [Stanford SNLI](https://nlp.stanford.edu/projects/snli/), CC BY-SA 4.0 | Experimental sentence embeddings and own-text comparison | 8,192-triplet experiment; served update-256 checkpoint saw 4,096; query/value LoRA |
| Hosted demo candidates | [demo_corpus.json](../backend/lists_api/data/demo_corpus.json) | 44 descriptions authored for this project, pointing to technical resources | None; these are inference candidates |
| Authored relevance fixtures | [queries.json](../evaluation/queries.json) | Eight contexts with relevance judgments over those same 44 descriptions | None; regression checks only |
| Live candidate retrieval | [BraveProvider](../backend/lists_api/retrieval.py) | Retrieve web-search candidates when explicitly configured | No trained model in the adapter; hosted demo does not enable it |
| BM25, rank fusion and diversity | [ranking.py](../backend/lists_api/ranking.py) | Score and order the retrieved candidates | Deterministic algorithms; no fitted learning-to-rank model |

The demonstration descriptions were not scraped from a public training dataset. Their destination URLs point to real resources, but their snippets and labels were authored together. They are not an independent benchmark, representative browsing data or evidence of production recommendation quality.

No MS MARCO or BEIR dataset has been downloaded or used to train or independently evaluate this implementation. Referencing those sources in research notes does not establish that a training or evaluation run occurred.

## The reused model's upstream training

The [publisher's pinned model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/README.md) attributes approximately 1.17 billion training tuples to a mixture including Reddit, S2ORC, WikiAnswers, PAQ, Stack Exchange and MS MARCO, among other datasets.

Its authors fine-tuned a pretrained MiniLM encoder using contrastive learning: cosine scores distinguish matched sentences from other sentences within the batch, optimized with cross-entropy. They report AdamW, a 0.00002 learning rate, 100,000 updates, batches of 1,024, 500 warmup steps and a 128-token training limit. These are the publisher's reported settings, not experiments reproduced for LISTS.

The model card labels the model Apache-2.0. That model license does not establish a uniform license for every underlying dataset.

Both encoders pin revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. The legacy FP32 download is pinned to SHA-256 `6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452`. The deployed baseline and trained adapter use the reviewed INT8 hashes in [model_catalog.json](../backend/lists_api/data/model_catalog.json). Runtime loading rejects unregistered model bytes and tokenizer checksums.

## What happens during inference

1. The user reviews a title and excerpt. The extension extracts that context locally. The webpage requires the user to provide it; entering a URL alone does not download the article.
2. The selected provider supplies candidate descriptions. Demo mode always supplies the fixed authored collection; live mode calls the configured search provider.
3. BM25 computes lexical scores. The selected pretrained or adapted MiniLM encoder produces 384-dimensional vectors using attention-mask mean pooling and L2 normalization. Inference is capped at 256 tokens and runs on CPU through ONNX Runtime.
4. Reciprocal rank fusion combines the available rankings. A diversity step and duplicate filters select up to ten pages.

Weights are not updated during requests. There is no personalization model, feedback training loop, fitted cross-encoder or custom learning-to-rank training job in this version.

## Why the demo cannot satisfy arbitrary web discovery

The ranker can only return pages supplied by its candidate provider. A topic outside the 44 technical descriptions can receive weak matches or fewer useful results. A larger training dataset would not make unindexed or newly published web pages available to this provider.

For the original live-web use case, enable candidate discovery using the implemented Brave adapter with server-side credentials and the protected production configuration in [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md). Alternatively, build and maintain an authorized document index. That alternative is described in the HLD but is not implemented here.

The hosted fixed-corpus demo is not a completed general-web recommendation product. A working demonstration and passing software tests do not remove that limitation.

## Completed training and measured quality

The [SNLI experiment](FINE_TUNING.md) used 8,192 training triplets, 512 validation queries and 512 held-out test queries, with zero normalized exact-text overlap across the selected partitions. Query/value LoRA trains 73,728 parameters while the original transformer remains frozen. The model card, weight hashes, pinned data downloads, checkpoint-selection history and evaluation outputs are committed.

For the actual deployed INT8 models, held-out MRR@10 is 0.7877 for the pretrained control and 0.7909 for the adaptation. Its paired-bootstrap interval includes zero. This is a real trained checkpoint, but not evidence of a statistically established quality gain or validated webpage usefulness. Baseline pretraining may already have included SNLI/AllNLI. The pretrained control stays the automatic default.

The own-text comparison at `/v1/compare` runs both encoders on two arbitrary English passages, independent of the 44-page provider. It returns actual cosine scores and checkpoint checksums. The webpage also exposes an explicit fine-tuned ranking option. Neither endpoint trains during requests.

For this use case, a more representative future evaluation needs independent article-to-page usefulness judgments, separated by article and topic. MS MARCO and BEIR were not used in this run. Training more sentence pairs would still not expand the provider's URL collection.

## Earlier hosted verification (before the SNLI update)

Deployment `dpl_8FAFYwq7FeGaEAeg8aJqfGdvgXeR` serves code commit `d0580c3c993831b081f001c1f95a794c8deba64e` at [the inference webpage](https://lists-semantic-discovery.vercel.app/). Actual browser interactions verified:

| Input and mode | Observed result |
| --- | --- |
| Hybrid search, automatic | 10 recommendations, 8 hosts, real cosine scores |
| Kafka reliability, automatic | 10 recommendations, 10 hosts, real cosine scores |
| Chrome extensions, automatic | 10 recommendations, 9 hosts, real cosine scores |
| Chrome extensions, lexical | 5 recommendations, lexical ranker, no cosine scores |
| API inspector | Actual request and server response visible |

The deployment fixes declare inference libraries in the packaged runtime graph and include the shared JavaScript assets in source. The browser retains same-origin deployment sessions. The repair commit passed 92 Python tests, 36 Node tests and a clean production-environment web check in [GitHub CI](https://github.com/deepak2233/lists-semantic-discovery/actions/runs/43398071202).

This screenshot shows actual hosted semantic inference over the authored collection. It is not evidence of live web retrieval or new model training.

![Hosted inference over the fixed authored collection](assets/deployed-demo.jpg)

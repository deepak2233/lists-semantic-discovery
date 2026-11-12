# Research and evidence

Reviewed 12 November 2026. Sources below are primary papers, author-hosted copies, publisher model artifacts or official product documentation. Design choices are our engineering judgments; they are not claims that the papers validated this particular product.

## Papers that affect the design

| Source | Relevant finding or method | LISTS decision | Limitation |
| --- | --- | --- | --- |
| [Mihalcea and Tarau, TextRank, EMNLP 2004](https://aclanthology.org/W04-3252/) | Graph-based ranking can select text units without an abstractive generator | Keep extraction deterministic; compare TextRank against the simple frequency baseline later | TextRank is researched but is not the algorithm implemented in `nlp.js` |
| [Reimers and Gurevych, Sentence-BERT, EMNLP 2019](https://aclanthology.org/D19-1410/) | Independent sentence embeddings can be compared efficiently for semantic similarity | Use an optional bi-encoder similarity score over candidate snippets | Paper results do not establish LISTS relevance, privacy or latency |
| [Cormack, Clarke and Buettcher, RRF, SIGIR 2009](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf) | Combine rankings through reciprocal rank contributions | Fuse BM25, provider and optional dense orderings with k=60 | Equal ranking contributions and k require local evaluation |
| [Carbonell and Goldstein, MMR, SIGIR 1998](https://www.cs.cmu.edu/afs/cs/Web/People/jgc/publication/MMR_DiversityBased_Reranking_SIGIR_1998.pdf) | Balance relevance against redundancy in selected documents | Apply an MMR-style lexical redundancy penalty and exact-host cap | Jaccard redundancy and 0.8/0.2 weights are our adaptation |
| [Thakur et al., BEIR, 2021](https://arxiv.org/abs/2104.08663) | Retrieval performance varies across domains; BM25 remains an important baseline | Compare lexical, dense and fused variants on varied held-out topics | Eight authored fixtures are not equivalent to BEIR or an independent benchmark |
| [Malkov and Yashunin, HNSW, 2016 preprint, revised 2018](https://arxiv.org/abs/1603.09320) | Hierarchical proximity graphs support approximate nearest-neighbor search | Consider ANN only if an owned corpus becomes large enough to require it | No ANN index exists in this implementation; no recall claim is made |

## Official implementation references

1. [Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab): temporary page access follows user invocation. LISTS uses this instead of installing persistent readers on all pages.
2. [Chrome extension network requests](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests): extension pages need appropriate host access for remote calls. The options page requests only the chosen HTTPS host at runtime.
3. [Chrome extension service-worker basics](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/basics): workers have event-driven lifetimes and packaged-code constraints. LISTS needs no background worker for its short popup flow.
4. [Chrome Web Store user-data FAQ](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq): handling includes website content and local processing. The release plan therefore requires an accurate privacy disclosure even for local extraction.
5. [Chrome storage](https://developer.chrome.com/docs/extensions/reference/api/storage): local and session storage serve different purposes. Configuration persists locally; access tokens use session storage.
6. [Brave Web Search API reference](https://api-dashboard.search.brave.com/api-reference/web/search/get): the documented web-result count limit is 20 per request, with offset-based pagination. LISTS requests two pages, not an unsupported count of 50 or 100. Duplicates across pages remain possible.
7. [Sentence Transformers retrieve and rerank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html): distinguish efficient retrieval from more expensive joint relevance scoring. LISTS starts with bi-encoder reranking and treats a cross encoder as an optional experiment.
8. [MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2): English sentence/short-paragraph embeddings, 384 dimensions and a default 256-wordpiece truncation boundary. LISTS makes input truncation explicit.
9. [Pinned MiniLM ONNX artifact](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/onnx/model.onnx): revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; publisher SHA256 `6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452`. Setup verifies this value.
10. [ONNX Runtime Python API](https://onnxruntime.ai/docs/api/python/api_summary.html): local graph sessions, named inputs and explicit CPU execution provider. LISTS constrains runtime threads and implements masked mean pooling.
11. [Tokenizers Python reference](https://huggingface.co/docs/tokenizers/python/latest/api/reference.html): local tokenizer loading, truncation, padding and batch encoding. A stable 0.22 dependency family is locked for the implementation.
12. [PyJWT usage](https://pyjwt.readthedocs.io/en/stable/usage.html): verify allowed algorithms and claims using trusted keys. LISTS never accepts a request-supplied key URL.
13. [FastAPI deployment concepts](https://fastapi.tiangolo.com/deployment/concepts/): HTTPS, process lifecycle, replication and memory must be planned explicitly. Model memory is multiplied by worker count.

## Conclusions from the research

The evidence supports a straightforward retrieve/rerank/diversify pipeline. It does not justify promising that embeddings always beat BM25, that RRF always improves the provider, or that an LLM is required. Those are hypotheses to measure.

The highest-impact early experiments are candidate recall, excerpt quality, dense-vs-lexical gains, duplicate rate and provider cost. Model novelty is lower priority than delivering consistently useful next reading with understandable data handling.

Provider prices, quotas, storage rights and Chrome Store decisions are deliberately not frozen as universal facts in this report. Validate the selected subscription and release configuration when deploying. This report does not make legal compliance or store-approval claims.

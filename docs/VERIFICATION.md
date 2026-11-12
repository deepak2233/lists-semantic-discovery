# Verification record

Observed on 12 November 2026 in the supplied Linux x86_64 development environment. Python 3.12.14, Node 24.22.1 and uv 0.13.6. Nine logical CPUs were visible to the process; an enforced cgroup CPU quota was not available to the probe. These results do not establish dedicated-core performance.

## Completed checks

| Check | Observed result | Scope |
| --- | --- | --- |
| Python backend tests | 57 passed | Request contracts, errors, auth claims, rate/admission, URL safety, dedup, provider faults and basic cache isolation |
| Node extension tests | 18 passed | NLP/safety logic and jsdom interaction tests, including no transmission before send and safe result rendering |
| Ruff lint and formatting | Passed | Python source and scripts |
| Production Python dependency audit | No known vulnerabilities reported | Locked base production dependency graph, using pip-audit at verification time |
| npm dependency audit | Zero reported vulnerabilities | Installed extension test dependency graph at verification time |
| Lexical HTTP smoke | Passed; ten demo results | Actual local Uvicorn service over HTTP |
| Semantic HTTP smoke | Passed; ten demo results | Actual local Uvicorn plus pinned MiniLM ONNX inference |
| Model artifact | Downloaded and publisher checksum verified | Pinned model revision and local manifest |
| OpenAPI | Exported to docs/openapi.json | API schema, independent of a running provider |
| Relevance regression | Both modes executed on eight authored contexts | Synthetic regression only, not independent web quality |

The test client emitted a Starlette warning about its future HTTP client transition. The current locked test environment passed; the warning is not hidden. Review it when updating dependencies.

## Local HTTP probe

Each mode received 20 requests at concurrency 2, with caching disabled and demo candidates. All returned HTTP 200. The admission quota was deliberately raised for this isolated local probe. The scripts launch and stop the service themselves.

| Mode | p50 | p95 | Observed throughput | Requests |
| --- | --- | --- | --- | --- |
| Lexical | 63.20 ms | 96.12 ms | 29.23 requests/s | 20/20 HTTP 200 |
| MiniLM semantic | 1129.17 ms | 1270.40 ms | 1.78 requests/s | 20/20 HTTP 200 |

The model adds real CPU cost. Neither result includes browser extraction, TLS or a live web-search provider. They must not be advertised as production p95 or capacity. Startup/warmup behavior is not captured by the percentile sample; the semantic smoke before the sample took approximately 904 ms of backend processing.

Raw probe summaries are `evaluation/local_probe_lexical.json` and `evaluation/local_probe_semantic.json`. Reproduce with `uv run --no-sync python scripts/verify_http.py`, adding `--model-path models/minilm` for the semantic path.

## Authored relevance regression

| Variant | Mean NDCG@10 | Mean labeled Recall@10 |
| --- | --- | --- |
| BM25 plus diversity | 0.8978 | 0.8577 |
| BM25 plus MiniLM fusion and diversity | 0.9097 | 0.8756 |

These are eight authored examples over 44 authored descriptions. Labels were created alongside the corpus. They support regression analysis only. They do not demonstrate a statistically significant real-world improvement or validate search-provider recall. Inspect the query-level results and methodology before using these numbers.

## Not validated in this environment

- Live Brave calls with a real subscription, its quota/cost behavior and provider-display obligations.
- The extension installed and operated in actual Chrome across the supported version matrix. DOM simulation is not browser acceptance.
- A live identity provider, managed OAuth/PKCE sign-in, JWKS rotation and identity outages.
- Docker image build/runtime: no Docker daemon was available here.
- Distributed quota/cache behavior, multi-replica failover, load beyond the small local probe or production SLOs.
- Independent relevance judgments, general-interest web coverage, store approval, accessibility certification or legal/compliance review.

Repository publication and hosted deployment are reported separately. Local build and browser results alone do not establish that a Vercel deployment is live.


## Inference webpage and edge-case revision

Verified on 12 November 2026 UTC using the same runtime versions. This revision adds the shared inference webpage, request-level ranker selection, score diagnostics and deployment packaging.

| Check | Observed result | Practical scope |
| --- | --- | --- |
| Python tests | 92 passed | Added normalized validation, signed links, generic-title deduplication, identity outage, cache/rate expiry and webpage API cases |
| Node tests | 35 passed | Extension plus playground interaction tests, including cancellation, stale results, body timeouts, unsafe text/links and token-free JSON copying |
| Ruff and diff whitespace | Passed | Python source and changed-file whitespace |
| Vercel build script | Passed locally | Hashed runtime export installed; 90,405,214-byte ONNX artifact and tokenizer verified |
| Isolated deployment runtime | Passed with Python `-S` | Imported only the vendored runtime graph, simulated Vercel host/origin configuration and executed five real semantic recommendations |
| Semantic dependency audit | No known vulnerabilities reported | Frozen production plus semantic dependency graph at verification time |
| Browser to API to results | Passed in actual Chrome preview | Ten semantic results, five lexical results, actual request/response inspector, invalid private-source feedback |
| Responsive CSS | Implemented; narrow browser viewport not verified | Desktop browser QA is complete; mobile-device acceptance remains open |
| Relevance regression | Unchanged aggregate metrics above | Both lexical and semantic variants re-executed over the same authored set |

The browser screenshot is `docs/assets/playground-desktop.jpg`. It shows a local fixed-corpus inference run, not a live-web provider or production Vercel response. Browser-host extension metadata errors were observed; no application error was identified in the inspected logs.

The updated semantic HTTP probe returned 20/20 HTTP 200 at concurrency 2, p50 893.54 ms, p95 1008.80 ms and 2.16 requests/s. Raw data is `evaluation/local_probe_semantic_v2.json`. It remains a loopback check, not a capacity claim or serverless cold-start benchmark.

The edge-case matrix in [EDGE_CASES.md](EDGE_CASES.md) describes both regressions and known gaps. Complete corner-case coverage is not claimed. Vercel publication still requires access to the intended project team and actual post-deployment checks.

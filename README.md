# LISTS: contextual web discovery

Find related public pages from the article you are reading. A Chrome Manifest V3 extension prepares a local excerpt, lets you review it, and asks a Python API for up to ten relevant, distinct pages.

**Status: working reference implementation, with a production HLD and explicit release gates.** This is a new implementation of the project brief, not a reconstruction of the original 2017 source. There are no invented users, business gains or production-scale claims.

## What it does

1. Click the extension and select **Preview this page**.
2. Review or edit the title and excerpt. Nothing has been transmitted yet.
3. Select **Find related pages**. The API retrieves candidates, ranks them and removes repetition.
4. Open related pages with a short explanation of their shared topics.

For example, an article about hybrid search can lead to Sentence-BERT, rank fusion, reranking and diversity research. Results are page recommendations, rather than a claim that entire websites have identical meaning.

## Run in five minutes

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 20+ for extension tests, and Chrome 114+.

```bash
uv sync --frozen --extra dev
npm ci
cp .env.example .env
uv run uvicorn lists_api.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

The default is an offline demo corpus with lexical ranking. No provider account or model download is required. Environment variables are read from the process; a `.env` file is used by Docker Compose, not automatically loaded by the Python application.

Load `extension/` using **chrome://extensions > Developer mode > Load unpacked**. Open a public English article, then open LISTS. The default API address is `http://127.0.0.1:8000`. Chrome's restricted pages, local pages and obvious account pages are excluded. Incognito is disabled.

API documentation: `http://127.0.0.1:8000/docs`. Health: `GET /health/ready`.

```bash
uv run python scripts/smoke.py
uv run pytest
npm test
uv run ruff check .
uv run ruff format --check .
uv run python scripts/evaluate.py
```

## Enable live web retrieval

Get a [Brave Search API](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started) subscription appropriate to the request rate. Keep its key on the backend. Do not put it in the extension or commit it.

```bash
export LISTS_PROVIDER=brave
export BRAVE_API_KEY='<your-provider-key>'
uv run uvicorn lists_api.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

PowerShell users can set `$env:LISTS_PROVIDER='brave'` and `$env:BRAVE_API_KEY='<your-provider-key>'` before running the same `uv run` command.

The adapter makes at most two provider calls per recommendation, requesting 20 candidates per page. Your subscription must permit that burst. The two calls share a total timeout. A provider failure produces a clear `503`, never demo results disguised as web results. The provider sees a query built from title/topic words; it does not receive the full excerpt or source URL from this implementation.

## Enable semantic ranking on CPU

```bash
uv sync --frozen --extra dev --extra semantic
uv run python scripts/download_model.py
export LISTS_MODEL_PATH="$PWD/models/minilm"
uv run uvicorn lists_api.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers
```

This explicitly downloads a pinned MiniLM ONNX model at build/setup time. The model checksum is verified; the service itself only reads local artifacts. No PyTorch, GPU, remote model code or hosted embedding API is needed. Missing or invalid configured artifacts stop startup. Without a configured model the response explicitly reports `bm25-rrf-mmr` and a lexical-mode warning.

Ranking combines BM25, provider rank in live mode, and optional dense similarity through reciprocal rank fusion. An MMR-style selection step penalizes redundant text and limits each exact host to two results. Its normalized ranking score is **not a probability or relevance confidence**.

## Container

```bash
cp .env.example .env
docker compose up --build
```

Compose publishes only a loopback port and runs with a read-only filesystem, dropped capabilities and resource limits. The base image and container build still need validation in your deployment environment. For semantic containers, see [deployment instructions](docs/OPERATIONS.md).

## Production deployment boundary

The code includes bounded inputs, fixed-provider egress, JWT validation, per-process admission controls, a small opt-in cache, safe DOM rendering, tests and CI. A public enterprise launch additionally requires a managed sign-in flow, distributed quotas, calibrated relevance evaluation, provider contractual review, browser acceptance testing and operational load tests. Those are [explicit roadmap gates](docs/ROADMAP.md).

The extension's short-lived access token field is for developer/pilot use. It is not a complete end-user authentication experience. Production API startup requires JWT settings, live retrieval and explicit extension origins. Put a TLS gateway in front of the API; never expose unauthenticated development mode publicly.

## Documentation

| Document | Contents |
| --- | --- |
| [High-level design](docs/HLD.md) | Use case, architecture, request sequence, contracts, algorithms, capacity, deployment evolution |
| [Research](docs/RESEARCH.md) | Primary papers and official documentation mapped to actual implementation decisions |
| [Roadmap](docs/ROADMAP.md) | Milestones, owners, exit criteria and production gates |
| [Security and privacy](docs/SECURITY_PRIVACY.md) | Data flow, threats, retention, known limitations and launch disclosures |
| [Operations](docs/OPERATIONS.md) | Configuration, deployment, runbooks, SLOs and rollback |
| [Evaluation](docs/EVALUATION.md) | Relevance methodology, fixture limitations and measurement commands |
| [Decisions](docs/ADR.md) | Technology choices and conditions for changing them |
| [Verification](docs/VERIFICATION.md) | What was actually tested and what remains unverified |
| [API example](examples/request.json) | Valid input for the recommendation endpoint |

The PDF report is built with `uv sync --extra report` followed by `uv run python scripts/build_report.py`. Its source is the same Markdown documentation.

## Repository layout

- `extension/`: installable, dependency-free browser extension.
- `backend/lists_api/`: typed API, providers, ranking, local ONNX adapter and controls.
- `tests/`: backend contracts, dependency failures, identity, security and extension logic.
- `evaluation/`: authored regression queries and relevance labels, not a public benchmark.
- `scripts/`: setup, evaluation, HTTP smoke checks, load probe and PDF report builder.
- `.github/workflows/`: tests, formatting and production dependency audit.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). No live page text, real browsing history, provider responses or credentials belong in issues, logs or fixtures. See [SECURITY.md](SECURITY.md) for private vulnerability reporting guidance. The code is MIT licensed; model artifacts and third-party services have separate terms in [NOTICE.md](NOTICE.md).

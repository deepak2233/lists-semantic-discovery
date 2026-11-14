# Vercel inference deployment

## What is deployed

One FastAPI application serves inference and the webpage. The browser uses same-origin `/v1/recommend` and `/v1/config`; there is no arbitrary remote API proxy or URL scraper. Static files in `public/` are delivered by Vercel's CDN. Locally, the development application serves `/assets` itself.

The default website is a **fixed-corpus demonstration with real inference**. It performs BM25 and, when bundled, pinned MiniLM ONNX inference over 44 authored technical-resource descriptions. It makes no paid search calls. A live web-search service is a separately protected configuration, not an undisclosed fallback.

## Build contract

1. Vercel recognizes root `app.py` as the FastAPI entrypoint and Python 3.12 from `.python-version`.
2. All inference libraries are declared as normal runtime dependencies in `pyproject.toml` and `uv.lock`. Vercel uses that graph when packaging dependencies for startup. Installing an optional library during the build command does not establish that it will be present in the deployed runtime.
3. `scripts/build_vercel.py` prepares shared frontend helpers and verifies the installed inference imports. A separate, frozen CPU export environment in `tmp/export-env` downloads the pinned base, merges the committed SNLI LoRA adapter and reconstructs both reviewed INT8 encoders. No training occurs during builds. Torch and export tools are excluded from the inference function; there are no vendored runtime copies.
4. `app.py` exposes the shared backend package. The API loads only local, checksum-verified model files at startup.
5. `vercel.json` sets a 30-second function duration, excludes development files from the bundle and applies security headers to CDN/function responses.

`.vercel/`, generated ONNX files, raw training data and local environments are excluded from Git. The small trained adapter, reports, provenance and shared frontend helpers are committed. The deployment build reconstructs and verifies the ONNX files. Training sources, adapter sources, the base PyTorch download and the isolated export environment are excluded from the function bundle. There are no tokens in the source or build command.

To regenerate the runtime export after a dependency change:

```bash
uv export --frozen --extra semantic --no-dev --no-emit-project --output-file deploy/vercel-requirements.txt
```

## Default environment

| Setting | Default behavior |
| --- | --- |
| LISTS_ENV | Web entrypoint selects `demo` unless explicitly configured |
| LISTS_PROVIDER | `demo`; demo mode rejects a paid provider |
| LISTS_BUILD_SEMANTIC | `1`; set `0` only for an intentional lexical-only deployment |
| LISTS_MODEL_PATH | Auto-select bundled `models/minilm` when present |
| CACHE_TTL_SECONDS | `0`; result caching disabled |
| LISTS_WEB_ORIGINS | Optional additional exact HTTPS origins |
| LISTS_PUBLIC_HOST | Optional custom host without scheme/path |
| VERCEL_URL / VERCEL_PROJECT_PRODUCTION_URL | Supplied by Vercel; used for exact host/origin configuration |

The web deployment selects a semantic model only when its artifacts exist. A configured but invalid artifact fails startup. The client capability badge comes from `/v1/config`, never a hardcoded semantic claim.

## Deploy and verify

Import `deepak2233/lists-semantic-discovery` into the intended Vercel team, with repository root and the FastAPI framework. Retain the build command from `vercel.json`. Do not create a second project when a matching project already exists.

Before release, verify the target project, team, source commit and environment. After the build reaches READY:

1. Open `/` and confirm the mode badge and candidate-source disclosure.
2. Inspect `/health/ready` and `/v1/config` for the actual ranker/model capability.
3. Run the Hybrid search example. Confirm recommendations, non-null semantic similarities when enabled, stage timing and request ID.
4. Select Lexical baseline and rerun. Confirm the actual ranker changes and cosine scores are absent.
5. Inspect API JSON, change examples during a pending request and exercise an invalid input.
6. Check a narrow mobile viewport, keyboard navigation and runtime errors.

Do not declare deployment complete from a successful upload alone. Verify the build state and a real browser-to-API-to-result interaction.

## Protected live search

Use `LISTS_ENV=production`, `LISTS_PROVIDER=brave`, `LISTS_AUTH_MODE=jwt`, trusted issuer/audience/JWKS/scope settings and exact `LISTS_WEB_ORIGINS` or `LISTS_ALLOWED_ORIGINS`. Store the provider credential on the server. The webpage's protected-session field accepts a short-lived **user access token**, not the provider key.

Managed end-user authorization-code/PKCE sign-in remains a public-release gate. Manual tokens support a technical pilot. Before exposing paid search to multiple users, add centralized quotas, provider spend controls and live subscription tests; per-process limits do not enforce a global budget.

## Operational limitations

Vercel can reuse an instance for concurrent calls and scale to multiple instances. The current semaphore/cache/rate windows are process-local. No durable profiles or browsing history are stored. Serverless cold starts include model initialization; benchmark the deployed configuration rather than quoting loopback latency.

The Python function bundle has a platform limit; keep only required model/runtime files. No large-function beta, paid memory upgrade, custom domain or external database is required by this project. Measure memory and cold-start behavior on the selected account plan before increasing traffic.

For rollback, retain the previous known-good deployment and its source/model versions. Promote that deployment through Vercel's normal rollback mechanism, then repeat health and example-inference checks.

Official references: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Python runtime](https://vercel.com/docs/functions/runtimes/python), [function configuration](https://vercel.com/docs/project-configuration/vercel-json). Platform behavior and plan limits can change; check the deployment's actual build output and settings.

## SNLI inference verification

Confirm `/v1/config` reports `fine_tuned_available: true`. Run an own-text comparison at `/#model-lab`, inspect `/v1/compare` evidence and match the ONNX and adapter checksums against the committed catalog. Run both related and unrelated passages, then select the fine-tuned recommendation mode and verify actual cosine scores. The [training record](FINE_TUNING.md) reports exact deployed INT8 metrics and their uncertainty.

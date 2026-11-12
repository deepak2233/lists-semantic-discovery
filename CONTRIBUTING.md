# Contributing

Use Python 3.11+ and Node 20+. Install with `uv sync --frozen --extra dev`. Run Python tests, Node tests, Ruff checks and the authored relevance regression before opening a change.

Keep provider clients behind the search interface. Network tests must use mock transports. Security fixes need a regression for the exposed boundary. Ranking changes need before/after evaluation on fixed judgments; do not tune on the holdout set.

Never commit `.env`, bearer tokens, provider credentials, real browsing text or raw provider responses. Use authored public-topic fixtures. The model directory is deliberately excluded; use the pinned setup script.

Update the HLD and verification record when behavior changes. Distinguish measured behavior from targets. Do not call the authored regression set a public benchmark or infer production capacity from loopback latency.

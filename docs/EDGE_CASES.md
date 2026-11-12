# Edge cases and remaining boundaries

The test suite covers the concrete cases below. It cannot establish that every possible corner case is covered. Coverage is a set of observed behaviors, not a percentage inferred from a test count.

## Tested contracts

| Boundary | Cases | Expected behavior | Evidence |
| --- | --- | --- | --- |
| Request schema | Missing/unknown fields, unsupported language, invalid ranker, boolean/string limits | 422 without echoing private input | `test_api.py`, `test_edge_cases.py` |
| Text normalization | Whitespace collapses below minimum, non-string text, obvious identifiers | Validate normalized text; redact obvious patterns before query construction | `test_edge_cases.py` |
| Body size | Declared and chunked bodies above 16 KiB | 413 before JSON parsing | `test_api.py` |
| Malformed JSON | Truncated document containing private values | 422 without returning those values | `test_edge_cases.py` |
| URL protocols | Browser/file/javascript URLs, embedded credentials and nonstandard ports | Reject before navigation/recommendation | Python and Node safety tests |
| Address variants | IPv4/IPv6, shortened/hex/octal numeric hosts, malformed DNS labels | Reject unsupported address literals and invalid labels | `test_safety_ranking.py`, `test_edge_cases.py` |
| Internationalized hosts | Unicode DNS labels and trailing dot | Normalize to lowercase ASCII/IDNA without changing path case | `test_edge_cases.py` |
| URL format controls | Bidi controls and raw control characters | Reject disguised URLs | `test_edge_cases.py` |
| Signed links | Signature keys, repeated parameters, `%20` versus `+`, tracking-looking keys | Preserve signed query bytes/order; do not break the destination | `test_edge_cases.py` |
| Ordinary tracking keys | Encoded tracking-key names with ordinary query values | Drop tracking keys while retaining remaining order and escaping | `test_edge_cases.py` |
| Source privacy | Source query string and fragment | Remove before API transmission | Browser interaction tests |
| Duplicate pages | Tracking variants, source URL, www/trailing slash variants | Exclude current page and duplicate URL identities | Ranking tests |
| Duplicate text | Same title with different snippets versus repeated title plus snippet | Preserve different articles; collapse near-identical descriptions | `test_edge_cases.py` |
| Sparse relevance | No lexical overlap and no configured semantic evidence | Return no filler | Ranking tests |
| Diversity | More than two useful pages on one exact host | At most two per exact host; return fewer if necessary | Ranking tests |
| Ranking selection | Semantic selected without model, lexical selected with model loaded | Explicit 409 for missing semantic model; lexical path never executes it | `test_edge_cases.py` |
| Invalid inference | Bad model shape/nonfinite scores or invalid ranking output | Fail clearly; never display substitute recommendations | Backend and playground tests |
| Upstream failures | Search 401/429/5xx, malformed schema, deadline, breaker open | 503 with retry guidance and no raw provider diagnostic | `test_provider_auth.py` |
| JWT | Wrong algorithm, issuer, audience, scope, empty subject, expiry | 401 with no token echo; reject algorithm before key lookup | Auth tests |
| Identity outage | JWKS endpoint unavailable | 503, distinguish service failure from invalid credentials | `test_edge_cases.py` |
| Admission | Quota exceeded and more work than configured slots | 429/503; release slots on dependency failure | API tests |
| Rate-state expiry | Denied requests reorder stale identities at capacity | Expired identities are reclaimed correctly | `test_edge_cases.py` |
| Cache | Disabled cache, TTL expiry, capacity eviction, per-subject keys | No expired or cross-subject result reuse | Control tests |
| Browser origin | Untrusted webpage/extension origin, invalid configured origin | 403 or startup rejection; exact HTTPS origins only outside loopback | API and web tests |
| Public demo | Attempt to enable paid search in demo environment | Startup rejection | `test_edge_cases.py` |
| Page extraction | Hidden text, forms, navigation, editable/password pages and non-English declaration | Skip excluded text or decline the page | Extension DOM tests |
| Review action | Page preview, edits, removed private terms | No request before send; regenerate topics from edited text | Extension DOM tests |
| Token destination | Access token belongs to a different backend origin | Do not attach it | Extension DOM tests |
| Result rendering | Malicious HTML in title/snippet and unsafe link protocols | Plain-text nodes; skip unsafe links | Browser DOM tests |
| Web input | Too-short excerpt, private address, sample changes | Validate before network inference | Playground tests |
| Loading/cancel | Cancellation and an ignored-abort late response | Restore controls; stale response never overwrites new context | Playground tests |
| Deadline | Headers arrive but response body stalls | Total client deadline still aborts the request | Playground tests |
| Web errors | 401/403/409/413/422/429/503 and malformed response JSON | Explicit error; no fabricated or stale result list | Playground tests |
| Inspector | Keyboard tabs, JSON copy and reset | Copy actual body/response without bearer token; reset clears session token | Playground tests |

## Known limitations and unverified situations

- Private-content detection is heuristic. A public-looking URL can contain sensitive or proprietary information. Regex redaction is incomplete.
- The server does not resolve or fetch user URLs. Link validation must not be reused as a general SSRF defense for a future crawler.
- Same-URL SPA content can change without changing the cleaned address. The extension does not perform a cryptographic document snapshot comparison at send time.
- Shadow DOM, cross-origin frames, PDFs, canvas/image-only articles and uncommon markup are not fully supported by article extraction.
- Deduplication uses canonical URL identity and title/snippet overlap, not page-body fingerprints. Mirrors and paraphrased copies can survive.
- Diversity groups exact hosts, not registrable domains or publisher ownership. Subdomains can represent one publisher.
- MiniLM is English-focused and truncates at 256 tokens. The initial cosine floor and diversity weights are not calibrated relevance guarantees.
- Live search-provider calls, subscription quotas and contractual obligations need validation with a real subscription. Mock transports do not establish live provider availability.
- Process-local quotas, breaker and cache are not fleet-wide protections. Multi-instance deployments need shared admission/budget enforcement for live search.
- Browser cancellation prevents stale display but does not guarantee a CPU inference already running in a worker thread is physically interrupted.
- The breaker is process-local and does not coordinate a single half-open probe across a fleet.
- The authored eight-query evaluation is not independent relevance evidence. Broad-topic quality, cold starts under load, regional behavior and failover still need measured evaluation.
- Webpage browser QA is separate from installing and testing the Chrome extension across supported versions.

These limitations are part of the release plan. They are not hidden behind the phrase “all edge cases covered.”

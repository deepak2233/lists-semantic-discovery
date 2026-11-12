# Security and privacy design

## Trust boundaries

Webpage text, provider results and all client input are untrusted. Browser extension code is a public client. The provider credential belongs only on the backend. The identity provider and search provider are separate external services with separate retention and availability behavior.

| Threat | Implemented control | Remaining limitation |
| --- | --- | --- |
| Private page content uploaded unexpectedly | User action, editable preview, obvious account/password/editable-page exclusions, incognito disabled | Host/path rules and regexes are heuristics; they cannot prove a page is public |
| Private terms survive an edit | Regenerate keywords from the edited preview | User must still review the preview carefully |
| Source query tokens leak | Drop source query string and fragment | URL paths and titles can still contain private information |
| Provider secret extracted from extension | Key exists only on server | Server secret management/rotation belongs to deployment |
| Bearer token sent to a changed API host | Session token is bound to its configured origin | A compromised approved backend can receive tokens intended for it |
| Search-result XSS | Text nodes, no HTML insertion, public HTTP(S) navigation validation | User still visits third-party content at their discretion |
| SSRF | Backend never fetches user or candidate URLs; fixed Brave endpoint only | A future crawler needs a separate hardened fetching boundary |
| Request/CPU exhaustion | 16 KiB body cap, field caps, bounded candidates, admission semaphore, rate limits | Upstream gateway must enforce body-read timeouts and global limits |
| Token algorithm/key confusion | RS256 allowlist, configured JWKS, issuer/audience/expiry/scope checks | Rotation/outage behavior needs live identity-provider testing |
| Cross-user cache disclosure | Per-subject HMAC keys, bounded TTL and capacity; off by default | Shared-cache migration requires new isolation tests |
| Sensitive logs | Validation errors omit input; app logs contain status/request ID only | Hosting, reverse proxy and tracing settings must be reviewed |
| Model supply-chain drift | Pinned revision and publisher weight checksum; local artifacts only | Dependency/model provenance review is still required |
| Tenant spend amplification | Per-subject local quota and no automatic provider retry loop | Multi-replica budgets need centralized enforcement |

URL validation does not resolve DNS and is not presented as a general SSRF prevention library. Its role is safe link filtering; the absence of arbitrary fetches is the important architectural boundary.

## Actual data shared

When the user chooses recommendations, the backend receives the reviewed title, excerpt, derived topic words, cleaned source address and request options. In live mode, the search provider receives a constructed title/topic query and normal network metadata from the backend. The full excerpt and source address are not intentionally sent to the search provider.

This does not guarantee anonymization. A title or a few topic words may be identifying. Regex redaction removes only selected obvious patterns. It misses names, addresses, proprietary material, many credential formats and context-specific sensitive information.

## Retention rules for the baseline

- No browsing history, user profiles, persistent raw source text or durable source index.
- Local settings persist until changed or the extension is removed.
- User access tokens use browser session storage and can be cleared explicitly.
- Result caching is disabled unless configured. If enabled, its TTL cannot exceed 300 seconds and capacity is 256 requests per process.
- Production logging retention must be configured by the operator. A proposed 14-day status-log window is a deployment decision, not an enforced code default.
- Provider and identity-service retention follow their contracts and configuration. Review them before processing real user data.

## Public-release disclosure checklist

Publish the actual purpose, fields collected, destinations, retention, user controls and contact channel. Declare minimum permissions and user-data handling in the Chrome Web Store submission. Review local processing as well as server transmission. Do not claim Chrome approval, zero data collection, anonymous processing or legal compliance without a completed review.

## Vulnerability reporting

Do not open public issues containing real page excerpts, credentials or exploit data against a running service. Use the repository's private vulnerability-reporting feature if enabled. Otherwise contact the repository owner through a private channel you already know. No invented security email is provided.

# Delivery roadmap and acceptance gates

Planning assumption: one backend engineer, one extension engineer, one ML engineer, with part-time product/security/SRE review. The durations are estimates for a focused pilot, not a delivery promise.

| Phase | Time | Work | Primary owner | Exit criteria |
| --- | --- | --- | --- | --- |
| 0. Agree the product | Days 1-3 | Choose article recommendation scope, English coverage, user action, provider budget and permitted topics | Product + technical lead | Written scope, data-flow review, target provider subscription, approved evaluation plan |
| 1. Runnable baseline | Week 1 | Packaged extension, local preview, API, fixture corpus, live-provider adapter, lexical ranking | Extension + backend | Clean install works; API/error tests pass; demo is visibly labeled; no embedded provider secrets |
| 2. Semantic relevance | Weeks 2-3 | Pinned local model, judgment dataset, recall/ranking baselines, duplicate controls | ML | Independently reviewed held-out results; paraphrase and rare-entity slices; measured model memory/latency |
| 3. Protected pilot | Weeks 4-5 | Managed OAuth/PKCE, gateway, distributed quotas, redacted telemetry, staging deployment | Backend + SRE | End-user sign-in tested; wrong audience/scope denied; load and dependency-failure tests meet agreed SLOs |
| 4. Release preparation | Weeks 6-7 | Store assets/disclosures, accessibility, Chrome matrix, incident drills, security review | Extension + security | Browser acceptance complete; privacy policy matches actual telemetry; rollback and incident ownership confirmed |
| 5. Controlled launch | Week 8 | Small opted-in cohort, daily quality/cost review, gradual expansion | Product + SRE + ML | Stable quality, spend and availability with documented go/no-go |

## Included in this repository

- A working fixture-driven API and installable extension source.
- A live Brave adapter with a documented setup path; an actual subscription is external configuration.
- Optional pinned MiniLM ONNX inference and model setup script.
- JWT resource-server validation; manual short-lived session tokens for developer/pilot testing.
- Single-process input, cache, rate and concurrency controls.
- Backend/extension tests, frozen dependency resolution, CI and reproducible evaluation scripts.
- HLD, research, operational guidance and this production roadmap.

## Mandatory gates before a public launch

1. **Identity:** Replace manual token entry with a complete public-client authorization-code + PKCE flow. Register exact extension redirect URIs. Validate state, issuer, audience and scopes; support expiry/sign-out without embedding a client secret. The API is already prepared to verify access tokens, but this is not a complete sign-in feature.
2. **Provider rights and quota:** Verify the subscription's allowed use, result-display requirements, retention/cache rights, burst rate, monthly budget and failure policy. Demonstrate that two sequential search calls fit those limits. Do not enable result caching until its terms are approved.
3. **Relevance:** Gather at least 300-500 representative, independently judged contexts across technical, general-interest and difficult slices. Use distinct development and holdout sets. Final numeric quality thresholds must come from this study, not from the authored fixture set.
4. **Browser behavior:** Install the unpacked package on actual supported Chrome versions. Test permissions, SPA navigation, popup closure, short pages, long pages, hidden forms, token expiry, offline state and accessibility. Record evidence. Node tests do not replace these checks.
5. **Global protection:** Before adding replicas, enforce account/global quotas and provider concurrency limits outside process memory. Test one tenant attempting to exhaust another tenant's budget.
6. **Operations:** Deploy a real staging container behind TLS. Add latency/provider/quota histograms and alerts, replay fault scenarios and prove rollback. Validate that infrastructure logs and traces exclude request bodies and provider query strings.
7. **Security and privacy:** Review heuristic extraction/redaction limitations. Publish accurate data-handling disclosures and a retention policy. Review provider and hosting behavior. Resolve critical/high findings from dependency and application review.

## Later work only when justified

| Change | Trigger | Decision evidence |
| --- | --- | --- |
| Cross-encoder reranker | Bi-encoder ranking misses important distinctions | Holdout gain outweighs latency/cost increase |
| Shared Redis cache | Repeated contexts and approved cache rights | Meaningful permitted hit rate; tenant isolation verified |
| Owned search corpus | Provider coverage or unit economics become unacceptable | Lawful source access, freshness cost and recall study |
| ANN/vector engine | Owned corpus exceeds efficient exact comparison | Recall/latency/memory tradeoff benchmark |
| Ingestion event bus | Durable independent consumers and replay are needed | Failure recovery requirements exceed a simple queue |
| Multilingual support | Real demand outside English | Per-language extraction, retrieval and safety evaluation |
| Personalization | Users explicitly want saved preferences | Clear consent, profile deletion and measurable benefit |

Do not add infrastructure to satisfy a label such as “MNC level.” Add it to satisfy a measured requirement with an owner, budget and failure plan.

# Architecture decision records

| Decision | Choice and rationale | Revisit when |
| --- | --- | --- |
| ADR-001: candidate source | Use a contracted search API. Web discovery is the hard data acquisition problem; avoid a premature web crawler. | Coverage/cost evidence supports an owned corpus |
| ADR-002: interaction | User-triggered preview and send using activeTab. The article is temporary query context. | Explicitly approved background mode has a clear user benefit |
| ADR-003: browser structure | Packaged popup modules without a service worker. No background work is necessary. | Background refresh or durable sign-in orchestration is implemented |
| ADR-004: service topology | One Python API containing provider/ranking modules. Keep interfaces separable without deploying microservices prematurely. | Independent scaling or ownership requires a service boundary |
| ADR-005: retrieval ranking | BM25 baseline, optional local dense score, RRF and MMR-style selection. Preserve a transparent low-dependency mode. | Held-out experiments show a simpler or better variant |
| ADR-006: model runtime | Pinned local MiniLM ONNX with CPU execution. Avoid hosted excerpt transmission and GPU/PyTorch requirements. | Measured quality/latency calls for a different reviewed model |
| ADR-007: state | No application database; optional small result cache disabled by default. | Saved preferences, shared quotas or licensed indexing create durable-state requirements |
| ADR-008: failure contract | Dependency failures return 503. Never silently substitute authored fixtures for live search. | A second licensed provider can offer an explicitly labeled, evaluated fallback |
| ADR-009: access | JWT-protected production resource server; temporary manual developer tokens. | Before public launch, implement managed PKCE sign-in |
| ADR-010: evaluation | Separate software correctness, authored regression and independent relevance evaluation. | A new model/data source requires additional evaluation slices |
| ADR-011: scaling | Local controls are explicitly single-process. | Before replica count or worker count exceeds one, add global quotas |

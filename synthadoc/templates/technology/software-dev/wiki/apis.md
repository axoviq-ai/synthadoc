---
title: APIs
status: draft
confidence: low
type: concept
sources: []
---

# APIs

API reference and contract documentation for all services. Populate by ingesting OpenAPI specs, API READMEs, and design docs.

Each API record captures:

- **API identity** — API name, service owner (link to [[services]]), protocol (REST / gRPC / GraphQL / WebSocket), base URL, version
- **Authentication** — authentication scheme (OAuth 2.0 / API key / mTLS / none), token scope, rate limits
- **Endpoints / operations** — for REST: method, path, path params, query params, request body schema, response schema, error codes; for gRPC: service name, RPC methods, request/response message types
- **Breaking change policy** — deprecation window, versioning strategy (URI versioning / header / none), how consumers are notified
- **SLA** — p50/p95/p99 latency targets, availability target, link to [[slos]]
- **Changelog** — version history, breaking changes, migration guides

**How to add an API:**

1. Ingest your OpenAPI specification:
   ```
   synthadoc ingest services/<service>/openapi.yaml -w <wiki>
   ```
2. Ingest API design docs or Postman collection exports

Cross-link to [[services]], [[system-design]], and [[engineering-practices]].

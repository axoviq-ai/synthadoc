---
title: Services
status: draft
confidence: low
type: concept
sources: []
---

# Services

Service catalog for all production services and key internal tools. Populate by ingesting your service README files, runbooks, and architecture docs.

Each service record captures:

- **Service identity** — service name, team owner, tech lead, Slack/chat channel, pager rotation
- **Purpose and scope** — what the service does, primary consumers, SLA commitment
- **Technology stack** — language, framework, database, message broker, external dependencies
- **Deployment** — deploy target (Kubernetes / ECS / Lambda / VM), deploy region(s), current version and deploy frequency
- **Reliability targets** — SLO (link to [[slos]]), alert thresholds, on-call runbook (link to [[runbooks]])
- **Interfaces** — public API (link to [[apis]]), event schemas, gRPC/GraphQL contracts
- **Key ADRs** — major decisions that shaped this service (link to [[adrs]])
- **Known debt and risks** — open issues, tech debt items (link to [[tech-debt]])

Cross-link to [[runbooks]], [[adrs]], [[apis]], and [[tech-debt]].

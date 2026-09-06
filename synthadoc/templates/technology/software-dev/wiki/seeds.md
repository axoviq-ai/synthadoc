---
title: Getting Started — Software Development
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Software Development

## Recommended first ingests

**Your repository README**
```
synthadoc ingest README.md -w <wiki>
```

**Existing architecture docs**
```
synthadoc ingest docs/ --batch -w <wiki>
```

**Recent Claude Code sessions (if applicable)**
```
synthadoc ingest ~/.claude/projects/<project-hash>/<session>.jsonl -w <wiki>
```

## Recommended web searches

- `architecture decision record template ADR Nygard format` — ADR best practices
- `SRE runbook template Google site reliability` — operational runbooks
- `"<your framework>" architecture best practices 2024` — framework-specific
- `REST API documentation standards OpenAPI Swagger` — API docs
- `technical debt register prioritization SQALE` — debt management

## First steps checklist

- [ ] Ingest your README and top-level docs/ folder
- [ ] Create an ADR for the most recent significant design decision
- [ ] Ingest your most recent incident post-mortem
- [ ] Create a service page for each major service
- [ ] Run scaffold to build the index

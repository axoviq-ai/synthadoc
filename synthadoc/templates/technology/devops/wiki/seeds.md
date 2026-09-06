---
title: Getting Started — DevOps
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — DevOps

## Recommended first ingests

**Your infrastructure README**
```
synthadoc ingest infrastructure/README.md -w <wiki>
```

**CI/CD workflow docs**
```
synthadoc ingest .github/workflows/ --batch -w <wiki>
```

**Recent post-mortems**
```
synthadoc ingest docs/post-mortems/ --batch -w <wiki>
```

## Recommended web searches

- `Google SRE book SLI SLO error budget free` — SRE foundations
- `Terraform module documentation best practices` — IaC docs
- `blameless post-mortem template incident review` — post-mortem format
- `DORA metrics deployment frequency lead time 2024` — DevOps benchmarks
- `Prometheus alerting rules best practices recording rules` — monitoring

## First steps checklist

- [ ] Ingest your infrastructure README and existing runbooks
- [ ] Create a pipeline page for each major CI/CD workflow
- [ ] Define SLOs for your top 3 services
- [ ] Ingest your most recent post-mortem
- [ ] Run scaffold to build the index

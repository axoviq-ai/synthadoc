---
title: Getting Started — Compliance
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Compliance

## Recommended first ingests

**Federal Register regulatory updates (public)**
```
synthadoc ingest "https://www.federalregister.gov/agencies/<agency-slug>" -w <wiki>
```

**NIST Risk Management Framework overview (free)**
```
synthadoc ingest "https://csrc.nist.gov/Projects/risk-management/about-rmf" -w <wiki>
```

## Recommended web searches

- `"<regulation name>" compliance requirements checklist 2024` — compliance obligations
- `COSO 2013 integrated framework internal control summary` — control framework
- `NIST cybersecurity framework compliance mapping SP 800-53` — cybersecurity compliance
- `SOC 2 Type II trust services criteria AICPA` — SOC 2 requirements
- `GDPR CCPA data privacy compliance checklist 2024` — privacy compliance

## First steps checklist

- [ ] List all regulations applicable to your entity
- [ ] Ingest the primary regulation text for your most significant obligation
- [ ] Create a control page for each key compliance control
- [ ] Document your top 5 compliance risks in [[risk-register]]
- [ ] Run scaffold to build the index

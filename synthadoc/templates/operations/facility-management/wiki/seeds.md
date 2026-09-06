---
title: Getting Started — Facility Management
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Facility Management

## Recommended first ingests

**DOE commercial buildings resources (public)**
```
synthadoc ingest "https://www.energy.gov/eere/buildings/commercial-buildings" -w <wiki>
```

**OSHA General Industry standards index (public)**
```
synthadoc ingest "https://www.osha.gov/laws-regs/regulations/standardnumber/1910" -w <wiki>
```

## Recommended web searches

- `preventive maintenance schedule template CMMS best practices` — PM planning
- `OSHA inspection checklist general industry 1910` — safety compliance
- `facility asset management ISO 55001 standard overview` — asset management
- `HVAC preventive maintenance schedule commercial building` — HVAC maintenance
- `work order management system best practices facility` — work order process

## First steps checklist

- [ ] Ingest your facility asset register (export from CMMS or spreadsheet)
- [ ] Create an equipment page for your 5 most critical assets
- [ ] Document your PM schedule for critical equipment
- [ ] Ingest your most recent facility inspection report
- [ ] Run scaffold to build the index

---
title: Getting Started — Real Estate Development
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Real Estate Development

## Recommended first ingests

**Your local municipality's zoning code (public)**
```
synthadoc ingest "https://<city>.gov/zoning-code" -w <wiki>
```

**Your project's approved site plan or entitlement documents**
```
synthadoc ingest docs/entitlements/ --batch -w <wiki>
```

## Recommended web searches

- `"<city> <zoning district>" allowed uses development standards` — local zoning
- `construction RFI submittal log template Excel` — project admin
- `AIA contract documents G702 application payment certificate` — contractor payments
- `construction inspection checklist residential commercial` — inspection process
- `change order approval process construction best practices` — change management

## First steps checklist

- [ ] Ingest your entitlement documents or zoning approval letters
- [ ] Create a project page for each active development project
- [ ] Document your general contractor in [[contractors]]
- [ ] Ingest your most recent permit applications
- [ ] Run scaffold to build the index
---
title: Getting Started — Property Management
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Property Management

## Recommended first ingests

**Your lease agreements (export from property management system)**
```
synthadoc ingest docs/leases/ --batch -w <wiki>
```

**Local landlord-tenant law (state legislature website)**
```
synthadoc ingest "https://law.justia.com/codes/<state>/landlord-tenant/" -w <wiki>
```

## Recommended web searches

- `lease abstract template commercial real estate` — lease abstraction
- `landlord tenant law "<your state>" notice requirements 2024` — local compliance
- `property maintenance work order process best practices` — maintenance workflow
- `vendor qualification property management contractor insurance` — vendor management
- `residential rent roll template property management` — financial reporting

## First steps checklist

- [ ] Ingest your lease agreement template
- [ ] Create a tenant page for each current tenant
- [ ] Create a work order entry for each open maintenance item
- [ ] Ingest your current rent roll
- [ ] Run scaffold to build the index
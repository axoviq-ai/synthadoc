---
title: Tenants
status: draft
confidence: low
type: concept
sources: []
---

# Tenants

Tenant directory for all managed properties. Populate by ingesting tenant profile summaries and lease abstracts.

Each tenant record captures:

- **Tenant identity** — tenant legal name, DBA name, tenant type (residential / commercial — retail / office / industrial), property, unit/suite, move-in date
- **Lease reference** — link to [[leases]] for full lease terms; lease expiration date and renewal status
- **Contact information** — primary contact name and title, phone, email; emergency contact; billing contact (if different)
- **Payment history** — current balance, payment method, NSF or late payment history, security deposit held on account
- **Maintenance history** — open and recently closed work orders (link to [[work-orders]])
- **Tenant satisfaction** — any written complaints, resolution status, renewal likelihood (management assessment)
- **Insurance on file** — tenant's renter's or commercial general liability insurance on file (yes/no), certificate expiration date, minimum required coverage met (yes/no)

**How to add a tenant:**

1. Copy `raw_sources/leases/template-lease-abstract.md` and fill in the contact section
2. Ingest the completed form: `synthadoc ingest raw_sources/leases/<tenant-suite>.md -w <wiki>`

Cross-link to [[leases]], [[work-orders]], [[rent-rolls]], and [[property-compliance]].

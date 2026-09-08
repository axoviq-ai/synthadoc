---
title: Rent Rolls
status: draft
confidence: low
type: concept
sources: []
---

# Rent Rolls

Current rent roll and occupancy status for all managed properties. Populate by ingesting rent roll exports from your property management system.

Each rent roll record captures:

- **Roll identity** — property, as-of date, rent roll version
- **Unit roster** — unit number/suite, rentable sf, tenant name, lease commencement, lease expiration, occupancy status (occupied / vacant / notice given / model)
- **Rent** — contracted base rent, current effective rent (after concessions), market rent for the unit, rent-to-market ratio (%), renewal terms
- **Vacancy and loss** — vacant units by count and sf, vacancy rate (%), physical vacancy vs. economic vacancy (loss from concessions, delinquency)
- **Tenant credit** — tenant payment status (current / delinquent — days and amount), security deposit balance
- **Portfolio rollup** — total units, total rentable sf, occupied sf, gross potential rent (GPR), loss-to-lease, effective gross income (EGI)

**How to populate:**

1. Export the rent roll from your property management system and ingest:
   ```
   synthadoc ingest docs/rent-rolls/<property>-<YYYY-MM>.xlsx -w <wiki>
   ```
2. Re-ingest monthly to keep the roll current

Cross-link to [[tenants]], [[leases]], [[operating-expenses]], and [[property-compliance]].

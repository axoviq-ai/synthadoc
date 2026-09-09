---
title: Leases
status: draft
confidence: low
type: concept
sources: []
---

# Leases

Lease abstract library for all managed properties.

Each lease record captures:

- **Lease identity** — tenant name, property, suite/unit, lease abstract date
- **Lease type and term** — lease type (Gross / Modified Gross / Net / NNN / Ground Lease), commencement date, expiration date, initial term, renewal options with notice periods, early termination right
- **Premises** — rentable sf, usable sf, load factor, parking spaces
- **Rent** — base rent and per-sf rate, annual escalation schedule (fixed steps or CPI), free rent period
- **Operating expenses and CAM** — base year or expense stop, CAM inclusions/exclusions, annual reconciliation terms, real estate taxes and insurance tenant share
- **Tenant improvement and concessions** — TI allowance, landlord work scope, rent abatement
- **Key obligations** — permitted use, prohibited uses, assignment/subletting rights, holdover rent rate, security deposit amount
- **Contacts** — tenant primary contact, billing contact, emergency contact

Flag leases expiring within 12 months. Cross-link to [[tenants]], [[rent-rolls]], and [[property-compliance]].

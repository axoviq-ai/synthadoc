---
title: Vendor Contracts
status: draft
confidence: low
type: concept
sources: []
---

# Vendor Contracts

Facility service contracts with external vendors. Each contract record captures:

- **Contract identity** — contract ID, vendor name, service category (HVAC maintenance, janitorial, security, landscaping, elevator service, pest control, waste management, fire suppression)
- **Scope of services** — what the vendor provides; included PM tasks; excluded items; response time for service calls
- **Contract term** — start date, end date, auto-renewal clause, notice period to cancel
- **Pricing** — fixed monthly or annual fee; unit rates for out-of-scope work; rate escalation clause
- **Performance standards** — SLA requirements (response time, PM completion rate); penalty or credit provisions for non-performance
- **Insurance requirements** — required general liability, workers comp, and auto coverage limits; certificate of insurance on file
- **Key contacts** — vendor account manager and emergency after-hours contact
- **Compliance certificates** — whether the vendor must provide certifications (elevator inspection, refrigerant handling certification, pest control license)

**How to populate:**

1. Ingest vendor service agreements:
   ```
   synthadoc ingest docs/facility/contracts/ --batch -w <wiki>
   ```

Cross-link to [[assets]] for the assets covered by each contract, [[preventive-maintenance]] for PM tasks outsourced to each vendor, and [[safety-inspections]] for inspections conducted by contracted inspectors.

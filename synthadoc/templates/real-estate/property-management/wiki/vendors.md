---
title: Vendors
status: draft
confidence: low
type: concept
sources: []
---

# Vendors

Approved vendor directory for all managed properties. Populate by ingesting vendor qualification packages and insurance certificates.

Each vendor record captures:

- **Vendor identity** — company name, trade/specialty (landscaping / janitorial / HVAC / plumbing / electrical / general maintenance / elevator / fire safety), principal contact, phone, email
- **Licensing and insurance** — contractor's license number and state, license expiration, GL insurance limits (per occurrence / aggregate), workers compensation carrier, certificate expiration, additional insured status
- **Contract terms** — service agreement type (on-call / annual contract), service scope, contract value, payment terms, response time SLA (emergency / routine)
- **Properties served** — which properties this vendor is approved for
- **Performance record** — average response time, quality issues, warranty callbacks, incident history
- **W-9 / 1099 status** — W-9 on file (yes/no), 1099 required threshold, last 1099 issued year

**How to add a vendor:**

1. Ingest the vendor's insurance certificate and contract:
   ```
   synthadoc ingest docs/vendors/<vendor-name>/ --batch -w <wiki>
   ```

Cross-link to [[work-orders]], [[operating-expenses]], and [[property-compliance]].

---
title: Applicable Regulations
status: draft
confidence: low
type: concept
sources: []
---

# Applicable Regulations

Master list of regulations, statutes, and standards that apply to the organization. Each entry captures:

- **Regulation identity** — full name, common abbreviation, enforcing agency, primary citation (statute or CFR title and part, or equivalent)
- **Regulatory area** — the compliance domain: data privacy, financial services, environmental, health and safety, export controls, employment, etc.
- **Applicability basis** — why this regulation applies (industry, geography, product type, revenue threshold, employee count)
- **Key obligations summary** — the three to five most operationally significant requirements in plain language
- **Compliance owner** — which department or individual owns compliance with this regulation
- **Effective date / version** — the current effective version; any upcoming amendments and their effective dates
- **Examination / enforcement risk** — frequency of regulatory examination; recent enforcement trends and penalty amounts

**How to populate:**

1. Ingest the primary regulation text:
   ```
   synthadoc ingest "https://www.law.cornell.edu/cfr/text/<title>/<part>" -w <wiki>
   ```
2. Ingest a saved regulation PDF or summary document:
   ```
   synthadoc ingest docs/compliance/regulations/ --batch -w <wiki>
   ```

Cross-link to [[regulatory-requirements]] for specific obligations extracted from each regulation, [[controls]] for the controls that address each requirement, and [[policies]] for the internal policies implementing compliance.

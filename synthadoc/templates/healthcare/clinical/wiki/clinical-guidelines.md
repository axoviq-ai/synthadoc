---
title: Clinical Guidelines
status: draft
confidence: low
type: concept
sources: []
---

# Clinical Guidelines

Evidence-based clinical practice guidelines from professional societies and health agencies. Each guideline record captures:

- **Guideline identity** — title, issuing organization (e.g., AHA, ACC, IDSA, USPSTF), publication year, update status (current / superseded)
- **Clinical topic** — the condition or clinical question addressed; specialty area
- **Recommendation summary** — the strongest (Class I / Grade A or equivalent) recommendations in plain language
- **Evidence grade** — the grading system used (ACC/AHA Class / GRADE A–C / USPSTF A–D) and the overall quality of evidence
- **Relevant population** — patient population the guideline applies to (age, disease stage, setting)
- **Key exclusions** — populations explicitly outside the guideline scope
- **Update frequency** — how often the issuing body updates the guideline; date of next scheduled review

**How to populate:**

1. Ingest guidelines from society websites or AHRQ's National Guideline Clearinghouse successor:
   ```
   synthadoc ingest "https://www.ahajournals.org/doi/10.1161/<doi>" -w <wiki>
   ```
2. Ingest saved guideline PDFs:
   ```
   synthadoc ingest docs/clinical/guidelines/ --batch -w <wiki>
   ```
3. Ingest USPSTF recommendations:
   ```
   synthadoc ingest "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/<topic>" -w <wiki>
   ```

Cross-link to [[conditions]] for the diagnoses covered, [[treatment-protocols]] for the protocols derived from the guideline, and [[diagnostic-criteria]] for the diagnostic thresholds the guideline establishes.

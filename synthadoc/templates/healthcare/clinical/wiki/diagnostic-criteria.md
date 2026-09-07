---
title: Diagnostic Criteria
status: draft
confidence: low
type: concept
sources: []
---

# Diagnostic Criteria

Formal criteria sets used to diagnose specific conditions. Each criteria set record captures:

- **Criteria identity** — name of the criteria set, issuing body, publication year, version
- **Target condition** — the diagnosis the criteria are designed to establish (link to [[conditions]])
- **Criteria elements** — the specific criteria required for diagnosis (symptoms, duration, exclusions, laboratory or imaging thresholds); presented verbatim or in close paraphrase
- **Classification** — whether diagnosis requires all criteria (necessary and sufficient) or a combination (e.g., 4 of 11 ACR criteria)
- **Sensitivity and specificity** — reported diagnostic performance in validation studies, if available
- **Important exclusions** — conditions that must be ruled out before applying the criteria
- **Clinical caveats** — known limitations; populations where criteria perform less well

**How to populate:**

1. Ingest diagnostic manuals and classification systems:
   ```
   synthadoc ingest "https://www.who.int/standards/classifications/classification-of-diseases" -w <wiki>
   ```
2. Ingest society-specific criteria documents:
   ```
   synthadoc ingest docs/clinical/diagnostic-criteria/ --batch -w <wiki>
   ```

Cross-link to [[conditions]] for the diagnoses each criteria set applies to, [[clinical-guidelines]] for the guidelines that reference or endorse the criteria, and [[clinical-procedures]] for any procedural tests the criteria require.

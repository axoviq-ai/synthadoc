---
title: Conditions
status: draft
confidence: low
type: concept
sources: []
---

# Conditions

Index of clinical conditions. Each condition page documents:

- **Condition identity** — condition name, ICD-10 code(s), synonyms and alternative names
- **Definition** — clear clinical definition in one to two sentences
- **Epidemiology** — incidence and prevalence (cite source and year); risk factors; demographic distribution
- **Pathophysiology** — underlying mechanism (briefly); key pathological processes
- **Clinical presentation** — typical signs and symptoms; variants (classic, atypical, subclinical)
- **Diagnostic criteria** — reference to specific criteria sets (link to [[diagnostic-criteria]]) — DSM-5, ICD-10 clinical codes, ACR criteria, etc.
- **Treatment approach** — summary of first-line management (link to [[treatment-protocols]] and [[clinical-guidelines]])
- **Prognosis** — natural history; key prognostic factors; typical outcomes with treatment

**How to populate:**

1. Ingest clinical guidelines covering the condition from [[clinical-guidelines]]:
   ```
   synthadoc ingest "https://www.uptodate.com/contents/<condition-topic>" -w <wiki>
   ```
2. Ingest condition summaries from authoritative sources:
   ```
   synthadoc ingest "https://www.merckmanuals.com/professional/<specialty>/<condition>" -w <wiki>
   ```
3. Ingest local protocols or department condition summaries:
   ```
   synthadoc ingest docs/clinical/conditions/ --batch -w <wiki>
   ```

Cross-link to [[diagnostic-criteria]], [[treatment-protocols]], [[clinical-guidelines]], [[medications]], and [[clinical-procedures]] for the management approach.

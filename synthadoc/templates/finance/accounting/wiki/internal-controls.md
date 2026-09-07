---
title: Internal Controls
status: draft
confidence: low
type: concept
sources: []
---

# Internal Controls

Key controls by process area, control effectiveness tracking, and SOX compliance. Populate by ingesting your controls matrix, walkthroughs, and audit findings.

Each internal control record captures:

- **Control identity** — control ID, control name, process area (revenue, procure-to-pay, treasury, payroll, financial close, IT general controls), control owner, effective date
- **Control description** — what the control does, how it prevents or detects a misstatement, manual vs. automated vs. IT-dependent manual classification
- **Frequency and evidence** — execution frequency (daily / monthly / quarterly), evidence requirement (approval sign-off, system log, reconciliation file), retention period
- **SOX relevance** — whether this is a Key Control for SOX 404, the related financial statement assertion (existence, completeness, accuracy, valuation, cutoff, presentation), and the associated risk of material misstatement (ROMM)
- **Operating effectiveness** — most recent test date, testing methodology (re-performance, observation, inquiry), sample size, findings, exceptions noted
- **Deficiency tracking** — deficiency classification (control deficiency / significant deficiency / material weakness), remediation plan, owner, target date, re-test results

**How to populate:**

1. Ingest your controls matrix or Risk and Control Matrix (RCM):
   ```
   synthadoc ingest <path/to/controls-matrix.xlsx> -w <wiki>
   ```
2. Ingest your internal or external audit findings

Cross-link to [[close-checklist]], [[audit-readiness]], [[journal-entries]], and [[financial-statements]].

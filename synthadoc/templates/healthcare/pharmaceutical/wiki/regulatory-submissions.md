---
title: Regulatory Submissions
status: draft
confidence: low
type: concept
sources: []
---

# Regulatory Submissions

Record of regulatory submissions to health authorities. Each submission record captures:

- **Submission identity** — submission type (IND, CTA, NDA, BLA, MAA, ANDA, sNDA, efficacy supplement), application number, compound (link to [[compounds]])
- **Agency** — regulatory authority (FDA, EMA, MHRA, PMDA, Health Canada, etc.); reviewing division or committee
- **Date submitted**: 
- **Indication submitted for**: 
- **Submission content summary** — CTD modules included (for NDA/BLA/MAA); IND serial number and amendment type; key data packages included
- **Agency actions** — filing acceptance date; complete response letter (CRL) date and issues raised if applicable; advisory committee meeting date and vote if held; approval date
- **Current status** — Pending / Under review / Approved / Refused / Withdrawn
- **Labeling** — approved label sections if approved; key labeling discussions (indication, boxed warning, contraindications)

**How to populate:**

1. Ingest submission cover letters and FDA action letters:
   ```
   synthadoc ingest docs/pharma/submissions/ --batch -w <wiki>
   ```
2. Ingest FDA drug approval package from Drugs@FDA:
   ```
   synthadoc ingest "https://www.accessdata.fda.gov/drugsatfda_docs/nda/<year>/<NDA-number>Orig1s000.pdf" -w <wiki>
   ```

Cross-link to [[compounds]] for the asset, [[clinical-trials]] for the pivotal data supporting the submission, [[protocols]] for the study protocols included, and [[safety]] for the safety database narrative.

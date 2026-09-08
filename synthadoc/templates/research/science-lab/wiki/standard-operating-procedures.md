---
title: Standard Operating Procedures
status: draft
confidence: low
type: concept
sources: []
---

# Standard Operating Procedures

SOPs for lab operations, safety, and administrative procedures. Populate by ingesting your lab's SOP documents.

Each SOP captures:

- **SOP identity** — SOP number, title, version, effective date, author, approver (PI or safety officer)
- **Scope** — what activities the SOP covers; who must follow it
- **Purpose** — why the SOP exists; what risk or quality issue it addresses
- **Procedure** — numbered steps, decision points, forms to complete, records to keep; reference to equipment settings or [[protocols]] as needed
- **Training requirement** — who must be trained before performing the activity, how training is documented
- **Review cycle** — how often the SOP is reviewed, who reviews it, version history
- **Regulatory basis** — which regulatory requirement, accreditation standard, or institutional policy the SOP satisfies (e.g. OSHA, EPA, IACUC, institutional biosafety)

SOP categories to cover: chemical waste disposal, instrument calibration, cryogenic material handling, biological waste decontamination, emergency procedures (spill, fire, injury), equipment authorization.

**How to populate:**

1. Ingest SOP documents:
   ```
   synthadoc ingest docs/sops/ --batch -w <wiki>
   ```

Cross-link to [[protocols]], [[instruments]], [[reagents]], and [[experiments]].

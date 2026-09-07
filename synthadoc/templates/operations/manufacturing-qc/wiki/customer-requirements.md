---
title: Customer Requirements
status: draft
confidence: low
type: concept
sources: []
---

# Customer Requirements

Specific quality, delivery, and documentation requirements imposed by customers. Each customer requirement record captures:

- **Customer identity** — customer name, DUNS number, major program or platform
- **Requirement category** — quality system (IATF 16949, AS9100, NADCAP), product specifications, test requirements, documentation (PPAP, FAIR, CoC), packaging, labeling, EDI, portal requirements
- **Specific requirements** — the exact requirement text or a close paraphrase; reference to the Customer Specific Requirements (CSR) document and version
- **Applicability** — which part numbers, product families, or programs this requirement applies to
- **Impact on our QMS** — which of our processes, procedures, or controls must be updated to satisfy the requirement; how we demonstrate compliance
- **Current compliance status** — Compliant / Gap identified / Waiver in place
- **Audit or review history** — customer audits or PPAP approvals confirming compliance; date of most recent approval

**How to populate:**

1. Ingest Customer Specific Requirements documents:
   ```
   synthadoc ingest docs/manufacturing/customer-requirements/ --batch -w <wiki>
   ```
2. Ingest IATF 16949 customer specific requirements from AIAG:
   ```
   synthadoc ingest "https://www.aiag.org/training-and-resources/manuals" -w <wiki>
   ```

Cross-link to [[quality-standards]] for the base standard each customer requirement extends, [[control-plans]] for how the CTQ is controlled, and [[inspection-procedures]] for the testing methods required.

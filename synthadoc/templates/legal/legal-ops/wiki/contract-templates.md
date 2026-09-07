---
title: Contract Templates
status: draft
confidence: low
type: concept
sources: []
---

# Contract Templates

Library of standard form agreements and playbooks used by the legal department. Each template record captures:

- **Template identity** — document title, version number, effective date, owner (legal function responsible for maintenance)
- **Agreement type** — NDA, MSA, SOW, EULA, SaaS subscription, employment offer letter, IP assignment, partnership agreement, etc.
- **Intended use** — which transactions or counterparty types this template is designed for
- **Fallback positions** — approved deviations from standard terms that may be accepted without escalation (documented in the playbook)
- **Escalation triggers** — which deviations require review by senior counsel or a specific practice group
- **Last review date** — when the template was last reviewed for legal accuracy and business alignment
- **Related templates** — forms that are typically used together (e.g., NDA before MSA; MSA before SOW)

**How to populate:**

1. Ingest your master form agreements:
   ```
   synthadoc ingest docs/legal/templates/ --batch -w <wiki>
   ```
2. Ingest a specific template with its playbook:
   ```
   synthadoc ingest docs/legal/templates/msa-template.docx -w <wiki>
   synthadoc ingest docs/legal/templates/msa-playbook.pdf -w <wiki>
   ```

Cross-link to [[contracts]] for executed agreements based on each template and [[outside-counsel]] for negotiation guidance.

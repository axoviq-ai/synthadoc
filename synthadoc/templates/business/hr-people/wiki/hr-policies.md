---
title: HR Policies
status: draft
confidence: low
type: concept
sources: []
---

# HR Policies

Core HR policies and their current status. Populate by ingesting your employee handbook and standalone policy documents.

Each HR policy record captures:

- **Policy identity** — policy name, policy number, effective date, last reviewed date, next review date, policy owner
- **Policy scope** — who the policy applies to (all employees / full-time / contractors / specific geographies)
- **Policy summary** — key rules and requirements; what is allowed, what is prohibited, what the process is
- **Compliance basis** — federal/state/local law that the policy satisfies (FMLA, ADA, EEOC, Title VII, FLSA, etc.)
- **Acknowledgment requirements** — whether employees must sign/acknowledge the policy, when (hire / annual refresh)
- **Exception process** — who approves exceptions, how exceptions are documented

Policy categories to cover: code of conduct, anti-harassment and discrimination, leave (FMLA, parental, PTO, sick), remote work, expense reimbursement, acceptable use of company technology, conflicts of interest, data privacy.

**How to populate:**

1. Ingest your employee handbook:
   ```
   synthadoc ingest docs/employee-handbook.pdf -w <wiki>
   ```
2. Ingest standalone policy documents

Cross-link to [[employee-handbook]], [[org-structure]], and [[compensation]].

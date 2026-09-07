---
title: Employee Handbook
status: draft
confidence: low
type: concept
sources: []
---

# Employee Handbook

Employee handbook structure and key provisions. Populate by ingesting your current employee handbook.

Each handbook section captures:

- **Welcome and culture** — company mission, values, culture description, leadership team introduction
- **Employment basics** — employment classifications (full-time / part-time / contractor), at-will employment statement, background check policy, I-9 / E-Verify
- **Compensation and benefits** — payroll schedule, direct deposit, benefits overview (health / dental / vision / 401k), open enrollment period, link to [[compensation]] for detail
- **Time off** — PTO accrual policy, sick leave, company holidays, parental leave, bereavement leave, FMLA
- **Workplace conduct** — code of conduct, anti-harassment, workplace safety, drug-free workplace, social media policy
- **Remote and hybrid work** — eligibility, equipment policy, home office stipend, core hours requirements
- **Offboarding** — notice period, final pay, COBRA, equipment return, data access termination

**How to populate:**

1. Ingest your employee handbook:
   ```
   synthadoc ingest docs/employee-handbook.pdf -w <wiki>
   ```

Cross-link to [[hr-policies]], [[compensation]], and [[org-structure]].

---
title: Risk Register
status: draft
confidence: low
type: concept
sources: []
---

# Risk Register

Compliance risk register. Each risk entry records:

- **Risk identity** — risk ID, risk description (what could go wrong, and why), regulatory area, risk owner
- **Inherent risk** — likelihood (1–5) and impact (1–5) before any controls; inherent risk score = likelihood × impact
- **Current controls** — controls in place that reduce likelihood or impact (link to [[controls]])
- **Residual risk** — likelihood and impact after controls; residual risk score
- **Risk treatment** — Accept / Mitigate / Transfer (insurance or contract) / Avoid; rationale for chosen treatment
- **Mitigation plan** — specific actions to reduce the risk further; owners; target dates
- **Target residual** — target risk level after mitigation plan is complete; target completion date
- **Status** — current status of mitigation (Not Started / In Progress / Complete)
- **Last reviewed** — date the entry was last reviewed and updated

**How to populate:**

1. Document risks identified during regulatory gap assessments or audits:
   ```
   synthadoc ingest docs/compliance/risk-register.xlsx -w <wiki>
   ```
2. Ingest risk assessment outputs from your GRC system:
   ```
   synthadoc ingest docs/compliance/risk-assessments/ --batch -w <wiki>
   ```

Cross-link to [[controls]] for mitigation controls, [[audit-findings]] for findings that revealed the risk, and [[regulatory-requirements]] for the obligation at risk of not being met.

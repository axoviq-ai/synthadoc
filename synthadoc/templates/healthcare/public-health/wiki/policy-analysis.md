---
title: Policy Analysis
status: draft
confidence: low
type: concept
sources: []
---

# Policy Analysis

Analysis of public health policies, legislation, and regulations. Each policy analysis record captures:

- **Policy identity** — policy or legislation name, jurisdiction (federal / state / local), enacting authority, date enacted or effective
- **Health issue addressed** — the public health problem the policy targets (link to [[disease-burden]])
- **Policy mechanism** — how the policy works: mandate, incentive, tax, information disclosure, environmental change, system change
- **Target population** — who the policy applies to (individuals, providers, employers, food manufacturers, insurers, etc.)
- **Evidence of effectiveness** — what the research literature says about effectiveness of this policy type; quality of evidence (RCT / quasi-experimental / observational)
- **Implementation status** — current implementation level; compliance rates; enforcement activity
- **Equity implications** — how the policy affects disparate populations; whether it reduces or widens disparities
- **Opposition and barriers** — major political or logistical barriers to the policy; interest group opposition
- **Estimated health impact** — projected or observed reduction in incidence, mortality, or cost

**How to populate:**

1. Ingest legislative summaries or policy briefs:
   ```
   synthadoc ingest docs/public-health/policy/ --batch -w <wiki>
   ```
2. Ingest Robert Wood Johnson Foundation or Milbank Memorial Fund policy analyses:
   ```
   synthadoc ingest "https://www.milbank.org/publications/" -w <wiki>
   ```

Cross-link to [[disease-burden]] for the problem context, [[health-programs]] for programs implementing the policy, and [[health-equity]] for equity impact.

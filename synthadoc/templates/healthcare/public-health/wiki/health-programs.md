---
title: Health Programs
status: draft
confidence: low
type: concept
sources: []
---

# Health Programs

Registry of active and completed public health programs. Each program record captures:

- **Program identity** — name, administering agency, geographic scope, start date, status (active / completed / planned)
- **Health problem addressed** — target condition and population; magnitude of the problem (link to [[disease-burden]])
- **Program objectives** — measurable goals with baseline and target values; target date
- **Intervention model** — type of intervention (screening, education, treatment access, policy, environmental change); evidence base (link to [[public-health-interventions]])
- **Implementation** — delivery channels, key partners, target and actual reach
- **Evaluation results** — process metrics (reach, fidelity) and outcome metrics (health behavior change, condition rates); most recent evaluation date
- **Budget** — annual budget; funding source (federal grant, state, local, foundation)
- **Equity focus** — priority subpopulations; barriers addressed; equity metrics tracked

**How to populate:**

1. Copy `raw_sources/programs/template-program-profile.md`, fill in all fields for each program, then:
   ```
   synthadoc ingest raw_sources/programs/<program-code>-<name>.md -w <wiki>
   ```
2. Ingest program evaluation reports:
   ```
   synthadoc ingest docs/public-health/programs/ --batch -w <wiki>
   ```

Cross-link to [[disease-burden]] for the health problem, [[public-health-interventions]] for the evidence base, [[surveillance]] for the data system tracking outcomes, and [[health-equity]] for equity metrics.

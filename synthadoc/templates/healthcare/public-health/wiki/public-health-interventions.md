---
title: Public Health Interventions
status: draft
confidence: low
type: concept
sources: []
---

# Public Health Interventions

Evidence-based interventions recommended by the Community Preventive Services Task Force, WHO, and other authoritative bodies. Each intervention record captures:

- **Intervention identity** — intervention name, health topic, target population
- **Recommendation source** — issuing body (CPSTF, WHO, USPSTF, CDC, Cochrane); recommendation strength (Strongly Recommended / Recommended / Insufficient Evidence); date of recommendation
- **Mechanism** — how the intervention achieves its effect (behavior change, access improvement, environmental change, etc.)
- **Evidence summary** — number and type of studies reviewed; findings on effectiveness; effect size if available
- **Implementation components** — the essential elements that must be present for the intervention to work as studied
- **Equity considerations** — whether the intervention has been evaluated in disparity populations; differential effectiveness
- **Implementation resources** — toolkits, training materials, fidelity checklists available from the recommending body
- **Cost-effectiveness** — cost per QALY or DALY averted if available; return on investment estimates

**How to populate:**

1. Ingest CPSTF recommendations:
   ```
   synthadoc ingest "https://www.thecommunityguide.org/resources/community-preventive-services-task-force-recommendations" -w <wiki>
   ```
2. Ingest WHO evidence-based intervention guides:
   ```
   synthadoc ingest "https://www.who.int/health-topics/interventions" -w <wiki>
   ```

Cross-link to [[health-programs]] for programs implementing each intervention, [[disease-burden]] for the health problem targeted, [[health-equity]] for equity evidence, and [[policy-analysis]] for policy levers that enable the intervention.

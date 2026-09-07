---
title: Clinical Procedures
status: draft
confidence: low
type: concept
sources: []
---

# Clinical Procedures

Procedure reference library for diagnostic and therapeutic interventions. Each procedure record captures:

- **Procedure identity** — name, CPT code(s), common abbreviations, procedure category (diagnostic / therapeutic / surgical / interventional)
- **Indications** — the clinical situations in which the procedure is indicated; specific criteria for patient selection
- **Contraindications** — absolute and relative contraindications; conditions requiring modified technique
- **Pre-procedure requirements** — patient preparation (fasting, bowel prep, anticoagulation hold), required labs or imaging, consent elements
- **Technique overview** — key steps; patient positioning; equipment required; sedation or anesthesia type
- **Complications** — major complications with approximate incidence; warning signs; management approach
- **Post-procedure monitoring** — observation period; discharge criteria; follow-up required
- **Competency requirements** — training requirements; number of supervised procedures before independent practice

**How to populate:**

1. Ingest procedure manuals or department protocols:
   ```
   synthadoc ingest docs/clinical/procedures/ --batch -w <wiki>
   ```
2. Ingest published procedure guides from clinical societies:
   ```
   synthadoc ingest "https://www.acog.org/clinical/clinical-guidance" -w <wiki>
   ```

Cross-link to [[conditions]] for indications, [[clinical-guidelines]] for the guideline supporting the procedure, and [[medications]] for anesthetic or procedural drugs used.

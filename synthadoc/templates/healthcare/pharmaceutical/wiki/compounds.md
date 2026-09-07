---
title: Compounds
status: draft
confidence: low
type: concept
sources: []
---

# Compounds

Drug compound and biologic asset registry. Each compound page records:

- **Compound identity** — internal code, INN or generic name, brand name (if any), modality (small molecule, biologic, antibody, ADC, gene therapy, cell therapy)
- **Mechanism of action** — how the compound works; the molecular target(s)
- **Therapeutic profile** — primary indication(s) and target patient population; the unmet need addressed
- **Development stage** — current phase (discovery, preclinical, Phase 1–3, regulatory review, approved)
- **Key efficacy data** — most advanced clinical data readout: primary endpoint result, trial name or NCT number
- **Safety summary** — dose-limiting toxicities, most common adverse events, any serious adverse events of note
- **CMC overview** — formulation, route of administration, manufacturing partner
- **IP position** — patent coverage type (composition of matter, method of use), approximate expiry, orphan or breakthrough designation

**How to populate:**

1. Copy `raw_sources/compounds/template-compound-profile.md`, fill in all fields, then:
   ```
   synthadoc ingest raw_sources/compounds/<compound-code>-<name>.md -w <wiki>
   ```
2. Ingest FDA drug approval packages:
   ```
   synthadoc ingest "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo=<NDA>" -w <wiki>
   ```

Cross-link to [[pipeline]] for the program's development stage, [[clinical-trials]] for active or completed studies, [[cmc]] for manufacturing detail, and [[safety]] for expanded pharmacovigilance data.

---
title: Medications
status: draft
confidence: low
type: concept
sources: []
---

# Medications

Drug reference library for formulary and practice-relevant medications. Each medication record captures:

- **Drug identity** — generic name, brand name(s), drug class, mechanism of action (one sentence)
- **Indications** — FDA-approved indications and any significant off-label uses with evidence basis
- **Dosing** — standard dose range by indication and patient population (adult, pediatric, renal/hepatic adjustment); route of administration
- **Contraindications** — absolute and relative contraindications; required pre-treatment testing (e.g., G6PD, CYP2D6)
- **Key adverse effects** — top three to five clinically significant adverse effects with incidence and monitoring parameters
- **Drug interactions** — major drug–drug interactions; interaction mechanism and clinical significance
- **Monitoring** — required laboratory monitoring (type, frequency); therapeutic drug monitoring if applicable
- **Pregnancy / lactation category** — FDA category (older) or prescribing information label (newer format)
- **Key counseling points** — the two or three things patients must understand

**How to populate:**

1. Ingest FDA prescribing information (package inserts):
   ```
   synthadoc ingest "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo=<NDA-number>" -w <wiki>
   ```
2. Ingest formulary or drug monograph exports:
   ```
   synthadoc ingest docs/clinical/formulary/ --batch -w <wiki>
   ```
3. Ingest NLM DailyMed summaries:
   ```
   synthadoc ingest "https://dailymed.nlm.nih.gov/dailymed/search.cfm?query=<drug-name>" -w <wiki>
   ```

Cross-link to [[conditions]] for the indications, [[treatment-protocols]] for the protocol context, and [[clinical-guidelines]] for the guideline recommendation.

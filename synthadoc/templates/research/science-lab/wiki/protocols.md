---
title: Protocols
status: draft
confidence: low
type: concept
sources: []
---

# Protocols

Experimental protocols indexed by technique. Populate by ingesting protocol documents and SOPs.

Each protocol captures:

- **Protocol identity** — protocol name, version, technique category, author, date created, date last validated
- **Purpose** — what this protocol is used for; which experiments or assay types use it
- **Required materials** — equipment list (link to [[instruments]]), reagents list with concentrations and lot number recommendation (link to [[reagents]]), consumables
- **Step-by-step procedure** — numbered steps, each a concrete action with parameters; decision points clearly marked; timing and temperature for each step
- **Safety considerations** — hazardous materials involved, required PPE, waste disposal procedure
- **Expected output** — what a successful run produces; quality control criteria for accepting results
- **Troubleshooting** — common failure modes, their likely causes, and corrective actions
- **Validation history** — who has run this protocol, with what outcomes; known edge cases

**How to populate:**

1. Ingest protocol documents:
   ```
   synthadoc ingest docs/protocols/ --batch -w <wiki>
   ```

Cross-link to [[experiments]], [[instruments]], [[reagents]], and [[standard-operating-procedures]].

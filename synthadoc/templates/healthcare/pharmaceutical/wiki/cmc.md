---
title: CMC
status: draft
confidence: low
type: concept
sources: []
---

# CMC (Chemistry, Manufacturing, and Controls)

Technical documentation covering drug substance and drug product manufacturing. Each CMC record captures:

- **Drug substance** — chemical or biological structure; synthesis route or expression system; critical quality attributes (CQAs); specification table (assay, purity, impurities, identity)
- **Drug product** — formulation composition; manufacturing process (unit operations); container-closure system; label claim and batch size
- **Analytical methods** — methods used for release testing and stability; whether methods are compendial or proprietary; validation status
- **Stability** — stability protocols by storage condition (25°C/60% RH, 40°C/75% RH, etc.); shelf-life supported and proposed; degradation pathways observed
- **Manufacturing sites** — drug substance site and drug product site; regulatory filings at each site (site master file, DMF, QP declaration)
- **Critical process parameters (CPPs)** — the parameters that most affect CQAs; acceptable ranges; how they are controlled
- **Supply chain** — key starting materials and their supply risk; qualified vendors; sole-source dependencies

**How to populate:**

1. Ingest CMC sections from regulatory submission dossiers:
   ```
   synthadoc ingest docs/pharma/cmc/ --batch -w <wiki>
   ```
2. Ingest drug master file summaries:
   ```
   synthadoc ingest docs/pharma/cmc/<compound>-dmf-summary.pdf -w <wiki>
   ```

Cross-link to [[compounds]] for the asset overview, [[regulatory-submissions]] for the CTD Module 3 filing, and [[protocols]] for the manufacturing processes validated.

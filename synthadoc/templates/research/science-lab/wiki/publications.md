---
title: Publications
status: draft
confidence: low
type: concept
sources: []
---

# Publications

Lab publications and manuscripts in preparation. Populate by ingesting published papers and manuscript drafts.

Each publication record captures:

- **Publication identity** — title, authors (lab members listed), venue (journal/conference), status (in prep / submitted / under revision / accepted / published), date
- **DOI / URL** — permanent identifier once published
- **Abstract** — brief summary of the paper's contribution
- **Key experiments** — which lab experiments (link to [[experiments]]) supported this paper; which datasets (link to [[raw-data]])
- **Data availability** — where the data is deposited (GEO, Zenodo, Dryad, etc.) and the accession number
- **Impact** — citation count (update periodically), Altmetric score, press coverage

**How to populate:**

1. Ingest papers directly from PubMed or bioRxiv:
   ```
   synthadoc ingest "https://pubmed.ncbi.nlm.nih.gov/<PMID>/" -w <wiki>
   ```

Cross-link to [[findings]], [[experiments]], [[raw-data]], and the lab [[researchers]].

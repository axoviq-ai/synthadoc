---
title: Getting Started — Academic Research
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Academic Research

## Recommended first ingests

**arXiv preprints for your field (public)**
```
synthadoc ingest "https://arxiv.org/search/?query=<topic>&searchtype=all&start=0" -w <wiki>
```

**Semantic Scholar paper search (free API)**
```
synthadoc ingest "https://api.semanticscholar.org/graph/v1/paper/search?query=<topic>" -w <wiki>
```

## Recommended web searches

- `"<research topic>" survey review 2023 2024 arxiv` — recent survey papers
- `"<your field>" seminal papers citation classics` — foundational works
- `PubMed "<topic>" systematic review meta-analysis` — medical research
- `Google Scholar "<topic>" cited by >100 2020` — high-impact recent work
- `"<research question>" replication study reproducibility` — replication status

## First steps checklist

- [ ] Ingest the 3-5 most important papers in your research area
- [ ] Create a literature review page for your primary research question
- [ ] Ingest a recent survey or review paper
- [ ] Document your primary research hypothesis in [[hypotheses]]
- [ ] Run scaffold to build the index

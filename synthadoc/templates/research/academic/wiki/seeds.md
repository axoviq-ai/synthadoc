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

**Semantic Scholar paper search (free)**
```
synthadoc ingest "https://www.semanticscholar.org/search?q=<topic>&sort=Relevance" -w <wiki>
```

## Recommended web searches

- `"<research topic>" survey review latest arxiv` — recent survey papers
- `"<your field>" seminal papers citation classics` — foundational works
- `PubMed "<topic>" systematic review meta-analysis` — medical research
- `Google Scholar "<topic>" cited by >100 latest` — high-impact recent work
- `"<research question>" replication study reproducibility` — replication status

## First steps checklist

- [ ] **Ingest the 3–5 most important papers in your field** — direct arXiv/PubMed ingest or annotated form:
  ```
  synthadoc ingest "https://arxiv.org/abs/<paper-id>" -w <wiki>
  ```
  Or copy `raw_sources/papers/template-paper-notes.md`, fill in your notes, then:
  ```
  synthadoc ingest raw_sources/papers/<author>-<year>-<keyword>.md -w <wiki>
  ```
  Populates [[papers]] and [[literature-review]].

- [ ] **Document your primary hypothesis**:
  ```
  synthadoc ingest docs/research-plan.md -w <wiki>
  ```
  Populates [[hypotheses]] and [[methodology]].

- [ ] **Ingest a recent survey or review paper**:
  ```
  synthadoc ingest "https://arxiv.org/abs/<survey-paper>" -w <wiki>
  ```

- [ ] **Ingest dataset documentation**:
  ```
  synthadoc ingest docs/datasets/<dataset>-codebook.pdf -w <wiki>
  ```
  Populates [[datasets]].

- [ ] **Run scaffold to build the index**
  ```
  synthadoc scaffold -w <wiki>
  ```

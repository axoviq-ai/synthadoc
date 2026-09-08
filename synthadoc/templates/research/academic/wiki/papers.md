---
title: Papers
status: draft
confidence: low
type: concept
sources: []
---

# Papers

Library of academic papers relevant to this research domain. Populate by ingesting papers and reading notes from `raw_sources/papers/`.

Each paper record captures:

- **Citation** — authors, title, venue (journal/conference/preprint), year, DOI or arXiv ID
- **Key contributions** — what is genuinely novel in this paper; what problem it solves
- **Methodology** — study type (empirical/theoretical/survey), dataset(s), evaluation metrics, baselines
- **Results summary** — main result, comparison to baseline, author-acknowledged limitations
- **Critical reading notes** — strengths, weaknesses, replication status, relevance to your work
- **Downstream links** — papers that cite this work (link to [[literature-review]] section); papers this work builds on

**How to add a paper:**

Two methods — direct ingest or annotated form:

Direct ingest from arXiv:
```
synthadoc ingest "https://arxiv.org/abs/<paper-id>" -w <wiki>
```

Annotated notes form:
1. Copy `raw_sources/papers/template-paper-notes.md`, fill in your reading notes, then:
   ```
   synthadoc ingest raw_sources/papers/<author>-<year>-<keyword>.md -w <wiki>
   ```

Cross-link to [[literature-review]], [[hypotheses]], [[methodology]], and [[findings]].

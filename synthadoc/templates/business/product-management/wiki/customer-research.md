---
title: Customer Research
status: draft
confidence: low
type: concept
sources: []
---

# Customer Research

Customer discovery research, user interviews, and Jobs to Be Done insights. Populate by ingesting research summaries and interview notes.

Each research record captures:

- **Research identity** — study name, research type (user interview / usability test / survey / diary study / analytics analysis / competitive analysis), researcher, date, scope
- **Research question** — specific question(s) the research was designed to answer
- **Methodology** — sample selection (n=X, segment, recruiting criteria), research format, interview guide summary, data collection method
- **Key findings** — numbered insights, each supported by evidence (quotes, frequency, behavioral patterns); distinguish what customers say vs. what they do
- **Jobs to Be Done** — functional, emotional, and social jobs customers are trying to accomplish; current solutions and their shortcomings
- **Implications for roadmap** — specific product implications from the findings; which hypotheses were confirmed or disproved
- **Confidence level** — how representative the sample is, known limitations of the research

**How to populate:**

1. Ingest research summaries or interview transcripts:
   ```
   synthadoc ingest docs/research/ --batch -w <wiki>
   ```

Cross-link to [[user-feedback]], [[prds]], [[roadmap]], and [[product-metrics]].

---
title: OKRs
status: draft
confidence: low
type: concept
sources: []
---

# OKRs — Objectives and Key Results

Quarterly and annual OKRs by team. Populate by ingesting OKR planning documents.

Each OKR set captures:

- **OKR identity** — team/company, planning period (Q1 YYYY / Annual YYYY), OKR owner, date set
- **Objective** — one aspirational, qualitative statement of what to achieve; why it matters; aligned to which company objective
- **Key results** — 2–5 measurable outcomes that define success for the objective; each KR has: metric name, baseline, target, owner, how it will be measured
- **Progress tracking** — current value, progress %, confidence level (High / Medium / Low — will we hit the target?), last updated date
- **Initiatives and projects** — specific work initiatives that will drive progress on this KR (link to [[roadmap]])
- **Grading** — final grade (0.0–1.0 or percentage), assessment of why the grade was achieved, lessons for next cycle

**How to populate:**

1. Ingest your OKR planning document or spreadsheet:
   ```
   synthadoc ingest docs/okrs/ --batch -w <wiki>
   ```

Cross-link to [[product-metrics]], [[roadmap]], and [[prds]].

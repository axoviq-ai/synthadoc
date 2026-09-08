---
title: Research Reports
status: draft
confidence: low
type: concept
sources: []
---

# Research Reports

Library of market research reports from analysts, industry associations, and internal studies. Populate by ingesting report documents and summaries.

Each report record captures:

- **Report identity** — title, publisher (Gartner / Forrester / IDC / McKinsey / internal), publication date, report type (Market Guide / Magic Quadrant / Forecast / Survey)
- **Market covered** — market definition, geographic scope, time period analyzed
- **Key takeaways** — top 3–5 findings most relevant to your business
- **Data highlights** — specific statistics, market sizes, growth rates, or customer data from the report
- **Methodology** — how the data was collected (survey n, interview n, secondary research), limitations
- **How it applies** — what decisions or analyses this report informs

**How to populate:**

1. Ingest analyst reports:
   ```
   synthadoc ingest <path/to/analyst-report.pdf> -w <wiki>
   ```

Cross-link to [[market-overview]], [[competitive-landscape]], [[market-sizing]], and [[consumer-segments]].

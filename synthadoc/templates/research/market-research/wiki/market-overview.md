---
title: Market Overview
status: draft
confidence: low
type: concept
sources: []
---

# Market Overview

High-level market description, dynamics, and trends. Populate by ingesting industry reports and market analyses.

Each market overview record captures:

- **Market definition** — precise definition of the market (what is included/excluded), geographic scope, time period
- **Market size and growth** — TAM (Total Addressable Market), SAM (Serviceable Addressable Market), SOM (Serviceable Obtainable Market); historical growth rate; growth forecast for next 3–5 years; source and date
- **Market drivers** — top 3–5 forces growing the market (regulatory change, technology shift, demographic trend, macroeconomic factor)
- **Market headwinds** — barriers to growth, risks, market-shrinking forces
- **Industry structure** — key market segments, dominant customer types, primary distribution channels, typical sales cycle length
- **Regulatory and macro environment** — key regulations affecting the market; macro factors (interest rates, GDP, commodity prices — as relevant)
- **Market maturity** — Gartner Hype Cycle position, Rogers adoption curve stage

**How to populate:**

1. Ingest industry reports:
   ```
   synthadoc ingest <path/to/industry-report.pdf> -w <wiki>
   ```
2. Ingest SBA / US Census / IBISWorld / Statista data pages

Cross-link to [[market-sizing]], [[competitive-landscape]], and [[consumer-segments]].

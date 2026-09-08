---
title: Competitive Landscape
status: draft
confidence: low
type: concept
sources: []
---

# Competitive Landscape

Structured overview of the competitive environment. Populate by synthesizing [[competitor-profiles]] and analyst reports.

Each landscape record captures:

- **Market structure** — number of significant competitors, market concentration (fragmented / oligopolistic), primary competitive vectors (price / features / vertical focus / go-to-market)
- **Competitor groupings** — direct competitors (same segment, same use case), indirect competitors (different approach to same job-to-be-done), substitute products (different category, same customer budget)
- **Competitive matrix** — comparison across key buyer criteria (feature set, pricing, integration depth, support quality, vertical coverage)

| Competitor | Price | Feature A | Feature B | Market focus | Notable weakness |
|------------|-------|-----------|-----------|-------------|-----------------|
| Us | | | | | |
| Competitor 1 | | | | | |

- **Differentiation map** — where you are uniquely positioned vs. where you compete head-to-head
- **Competitive dynamics** — how the landscape is changing (new entrants, consolidation, commoditization pressure, emerging disruptors)
- **Win/loss patterns** — segments where you typically win and why; segments where you lose and why

**How to populate:**

1. Synthesize after ingesting each competitor (link to [[competitor-profiles]])
2. Ingest analyst landscape reports:
   ```
   synthadoc ingest <path/to/analyst-report.pdf> -w <wiki>
   ```

Cross-link to [[competitor-profiles]], [[market-overview]], [[consumer-segments]], and [[market-sizing]].

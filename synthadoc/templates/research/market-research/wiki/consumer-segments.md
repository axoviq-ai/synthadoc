---
title: Consumer Segments
status: draft
confidence: low
type: concept
sources: []
---

# Consumer Segments

Customer and consumer segment profiles. Populate by ingesting segmentation analysis, survey data, and customer interview synthesis.

Each segment record captures:

- **Segment name and size** — segment label, estimated number of accounts or individuals, % of TAM
- **Firmographic / demographic profile** — company size, industry (B2B) or age/income/geography (B2C); technographic or behavioral attributes
- **Jobs to Be Done** — functional, emotional, and social jobs this segment is trying to accomplish; current solutions they use
- **Key pain points** — top 3 pain points; severity and frequency of each; what they've tried and why it failed
- **Decision-making** — who is the economic buyer, who is the champion, who is the gatekeeper, how long is the decision cycle
- **Value drivers** — what they care most about when evaluating solutions (price / ease of use / integrations / support / brand trust)
- **Willingness to pay** — price sensitivity, typical budget range, preferred pricing model
- **Segment attractiveness** — growth rate, profitability potential, competitive intensity for this segment

**How to populate:**

1. Ingest segmentation analysis or persona documents:
   ```
   synthadoc ingest docs/customer-segments/ --batch -w <wiki>
   ```

Cross-link to [[market-overview]], [[competitive-landscape]], [[customer-insights]], and [[surveys]].

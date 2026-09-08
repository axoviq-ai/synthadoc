---
title: Competitor Profiles
status: draft
confidence: low
type: concept
sources: []
---

# Competitor Profiles

Detailed profiles for each tracked competitor. Populate by ingesting competitor profiles from `raw_sources/competitors/`.

Each competitor profile captures:

- **Company identity** — name, website, founded, HQ, funding stage, total funding, employee count, key investors
- **Product and positioning** — core product, target customer, claimed USP, primary use case, product tiers
- **Pricing** — pricing tiers, prices, key inclusions; pricing model (seat-based / usage-based / flat / enterprise)
- **Strengths** — what they do well; where customers praise them
- **Weaknesses and gaps** — where customers complain; feature gaps; market segments they don't serve
- **Market position** — estimated market share, customer count, notable customers, G2/Capterra score
- **Recent moves** — product launches, pricing changes, funding rounds, partnership announcements, executive hires — and implications for your strategy

**How to add a competitor:**

1. Ingest the competitor's website directly:
   ```
   synthadoc ingest "https://www.<competitor>.com" -w <wiki>
   ```
2. Or copy `raw_sources/competitors/template-competitor-profile.md`, fill it in, then:
   ```
   synthadoc ingest raw_sources/competitors/<competitor>.md -w <wiki>
   ```

Cross-link to [[competitive-landscape]], [[market-overview]], and [[consumer-segments]].

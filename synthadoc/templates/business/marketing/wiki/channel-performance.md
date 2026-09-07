---
title: Channel Performance
status: draft
confidence: low
type: concept
sources: []
---

# Channel Performance

Performance metrics by marketing channel. Populate by ingesting analytics reports and channel dashboards.

Each channel performance record captures:

- **Channel identity** — channel name (paid search / paid social / organic social / email / SEO / events / partnerships / referral), reporting period
- **Volume metrics** — impressions, clicks, sessions, new visitors
- **Conversion metrics** — leads/MQLs, conversion rate (visit-to-lead), cost per lead (CPL), cost per MQL
- **Pipeline contribution** — pipeline influenced (first touch / last touch / multi-touch), revenue attributed, CAC for channel
- **Quality metrics** — average lead score, SQL conversion rate, average deal size for channel-sourced deals
- **Efficiency benchmarks** — budget spent, ROAS (for paid channels), CPM (for brand channels)
- **Trend vs. prior period** — month-over-month and quarter-over-quarter change for key metrics

**How to populate:**

1. Ingest your marketing analytics report or UTM-tagged conversion data:
   ```
   synthadoc ingest docs/analytics/channel-report-<YYYY-MM>.pdf -w <wiki>
   ```

Cross-link to [[campaigns]], [[seo]], and [[content-assets]].

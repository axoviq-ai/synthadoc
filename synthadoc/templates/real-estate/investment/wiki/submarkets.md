---
title: Submarkets
status: draft
confidence: low
type: concept
sources: []
---

# Submarkets

Index of all submarkets being tracked for acquisition analysis or active portfolio monitoring. Each entry links to a dedicated submarket analysis page populated by ingesting market reports.

| Submarket | Type | Vacancy | Avg Rent | Cap Rate | Last Updated |
|-----------|------|---------|----------|----------|--------------|
| *(ingest a market report to populate)* | | | | | |

**How to add a submarket:**

1. Find the most recent market report for your target area:
   - [Zillow Research](https://www.zillow.com/research/) — city and zip-level data
   - [Redfin Data Center](https://www.redfin.com/news/data-center/) — metro and neighbourhood trends
   - [Realtor.com Research](https://www.realtor.com/research/) — national and metro reports
   - Local MLS board quarterly publications
   - Broker reports (JLL, CBRE, Marcus & Millichap, Savills)
2. Ingest it: `synthadoc ingest "https://..." -w <wiki>`
3. The generated page cross-links here automatically via [[submarkets]].

See [[market-analysis]] for the full list of fields captured per submarket. See [[properties]] to match assets to their submarket.

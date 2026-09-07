---
title: Campaign Calendar
status: draft
confidence: low
type: concept
sources: []
---

# Campaign Calendar

Editorial and campaign calendar. Populate by ingesting your campaign calendar export or content planning document.

Each calendar record captures:

- **Period** — planning horizon (quarter, month, week)
- **Campaigns scheduled** — campaign name, type, channel(s), owner, start/end date, status
- **Content pieces scheduled** — content type (blog / webinar / ebook / social / email), title, target keyword, owner, draft due, publish date
- **Events and product moments** — product releases, company events, seasonal moments, industry events driving content themes
- **Capacity plan** — content units planned per week, production capacity (in-house vs. agency), bottleneck identification
- **Approval workflow** — draft → review → legal/brand approval → scheduling → publish; who approves each step

**How to populate:**

1. Ingest your campaign or editorial calendar export:
   ```
   synthadoc ingest docs/campaign-calendar.xlsx -w <wiki>
   ```

Cross-link to [[campaigns]], [[content-strategy]], and [[content-assets]].

---
title: Content Assets
status: draft
confidence: low
type: concept
sources: []
---

# Content Assets

Library of published and in-progress content assets. Populate by ingesting your content inventory or asset library index.

Each content asset record captures:

- **Asset identity** — title, content type (blog post / ebook / whitepaper / webinar / case study / video / infographic), author, publish date, URL
- **Audience and stage** — target persona, buying stage (TOFU / MOFU / BOFU), topic pillar
- **SEO attributes** — primary keyword, secondary keywords, current ranking position, organic traffic (monthly)
- **Performance** — views, downloads, leads generated, backlinks earned, time on page
- **Status** — published / in review / draft / scheduled / needs refresh (with last-refreshed date)
- **Distribution record** — which email sends, social posts, or paid promotions have featured this asset

**How to populate:**

1. Ingest your content inventory spreadsheet:
   ```
   synthadoc ingest docs/content-inventory.xlsx -w <wiki>
   ```

Cross-link to [[content-strategy]], [[campaign-calendar]], and [[seo]].

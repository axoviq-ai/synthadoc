---
title: Campaigns
status: draft
confidence: low
type: concept
sources: []
---

# Campaigns

Campaign library for all marketing campaigns. Populate by ingesting campaign briefs from `raw_sources/campaigns/`.

Each campaign record captures:

- **Campaign identity** — name, type (product launch / brand awareness / lead gen / retargeting / ABM), owner, dates, status
- **Objective and goal** — primary goal (MQL volume / pipeline / revenue / retention), target metric and value, secondary metrics
- **Target audience** — persona or ICP, segment (industry/company size/geography/title), audience size, buying stage
- **Messaging** — core message/hook, value proposition emphasis, CTA, tone
- **Channels and budget** — channel breakdown (paid search, paid social, email, content, events), budget per channel, channel owner
- **Creative assets** — landing page, email copy, ad creative specs, social copy
- **Results** — post-campaign actuals vs. targets: impressions, clicks/CTR, leads/MQLs, pipeline influenced, cost per MQL

**How to add a campaign:**

1. Copy `raw_sources/campaigns/template-campaign-brief.md` and rename it after the campaign
2. Fill in the brief before execution; add results after
3. Run `synthadoc ingest raw_sources/campaigns/<campaign>.md -w <wiki>`

Cross-link to [[campaign-calendar]], [[channel-performance]], and [[messaging]].

---
title: Product Metrics
status: draft
confidence: low
type: concept
sources: []
---

# Product Metrics

Product analytics framework, north star metric, and instrumentation standards. Populate by ingesting your metrics framework and analytics documentation.

Each product metrics record captures:

- **North star metric** — the single metric that best captures long-term value delivered to customers; definition, how it is calculated, current value, trend
- **Input metrics** — the 2–4 leading indicators that drive the north star; owner, current value, target, trend
- **Health metrics** — monitoring metrics that must not regress (retention, reliability, support volume)
- **Feature-level metrics** — adoption rate, activation rate, feature engagement depth, retention impact for each major feature (link to [[prds]])
- **Funnel metrics** — acquisition, activation, retention, revenue, referral (AARRR) by segment; funnel conversion rates
- **Instrumentation standard** — which events are tracked, event naming convention, property naming convention, how to add new tracking
- **Dashboards** — links to analytics dashboards (Amplitude / Mixpanel / Heap / Looker) for each metric category

**How to populate:**

1. Ingest your metrics framework or analytics spec:
   ```
   synthadoc ingest docs/product-metrics.md -w <wiki>
   ```

Cross-link to [[okrs]], [[roadmap]], [[customer-research]], and [[user-feedback]].

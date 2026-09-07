---
title: Messaging
status: draft
confidence: low
type: concept
sources: []
---

# Messaging

Core messaging framework and value proposition library. Populate by ingesting your messaging framework document and positioning work.

Each messaging record captures:

- **Positioning statement** — "For [target customer] who [need], [product] is the [category] that [key benefit], unlike [alternative]."
- **Value proposition** — primary value prop (one sentence), supporting proof points (3–5 bullets with evidence)
- **Audience-specific messaging** — how the core message translates for each persona/ICP; which benefits to lead with for each
- **Pain-to-gain map** — top pains customers experience → how the product resolves each → quantified outcomes where available
- **Competitive differentiation** — how the message is distinct from each top competitor's message; claims to avoid (too close to competitor positioning)
- **Message hierarchy** — which messages to lead with in each context (homepage, sales deck, ads, email, cold outreach)
- **Proof elements** — customer quotes, data points, case study results available to support each key claim

**How to populate:**

1. Ingest your messaging framework or positioning doc:
   ```
   synthadoc ingest docs/messaging-framework.md -w <wiki>
   ```

Cross-link to [[brand-guidelines]], [[content-strategy]], and [[campaigns]].

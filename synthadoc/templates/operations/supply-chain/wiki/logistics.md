---
title: Logistics
status: draft
confidence: low
type: concept
sources: []
---

# Logistics

Inbound and outbound logistics processes, carrier network, and transportation management. Each logistics process record captures:

- **Process identity** — logistics activity (inbound receiving, outbound shipping, returns, cross-docking, warehouse pick-pack-ship, customs clearance)
- **Flow description** — step-by-step process from order to delivery; handoff points between teams
- **Carrier network** — which carriers serve each lane or mode; carrier selection criteria; backup carrier for primary outages (link to [[freight-contracts]])
- **Lead times** — standard transit times by lane and mode; expedite option availability and cost
- **Documentation** — required shipping documents (BOL, commercial invoice, packing list, certificate of origin, export license); who prepares each
- **Customs and trade compliance** — HTS codes for key materials; import/export restrictions; denied parties screening; CITES or other permit requirements
- **KPIs** — on-time delivery rate; freight cost per unit; damage rate; customs clearance cycle time; target and actual for each
- **Escalation** — late shipment escalation path; carrier claim process

**How to populate:**

1. Ingest freight policies and logistics SOPs:
   ```
   synthadoc ingest docs/supply-chain/logistics/ --batch -w <wiki>
   ```
2. Ingest US trade and Incoterms reference:
   ```
   synthadoc ingest "https://www.trade.gov/" -w <wiki>
   ```

Cross-link to [[freight-contracts]] for the carrier agreements, [[suppliers]] for supplier-managed inbound logistics, [[inventory-management]] for the receiving and stocking process, and [[procurement-procedures]] for the purchase order process that triggers shipments.

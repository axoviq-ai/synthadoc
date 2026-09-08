---
title: Inventory Management
status: draft
confidence: low
type: concept
sources: []
---

# Inventory Management

Inventory policy, safety stock, and replenishment rules by material. Each inventory policy record captures:

- **Material identity** — part number, description, unit of measure (link to [[materials]] for the full material profile)
- **Inventory classification** — ABC classification (A: high-value/high-velocity, B: medium, C: low); criticality (critical-to-production vs. non-critical)
- **Replenishment method** — Min-max / EOQ (economic order quantity) / Kanban / MRP-driven / Consigned
- **Safety stock** — safety stock quantity and the formula or risk basis for setting it; service level target (e.g., 98%)
- **Reorder point** — the inventory level that triggers a replenishment order; formula: safety stock + (average daily usage × supplier lead time)
- **Order quantity** — standard order quantity or EOQ; minimum order quantity from supplier; lot size multiples
- **Current inventory performance** — current on-hand quantity; days of supply; stockout events in the last 90 days; excess and obsolete reserve amount

**How to populate:**

1. Export inventory data from your ERP and ingest:
   ```
   synthadoc ingest docs/supply-chain/inventory-policy.xlsx -w <wiki>
   ```
2. Ingest EOQ and safety stock methodology reference:
   ```
   synthadoc ingest "https://www.precoro.com/blog/single-source-vs-sole-source-what-is-the-difference" -w <wiki>
   ```

Cross-link to [[materials]] for the material profile, [[suppliers]] for the supply lead time, [[procurement-procedures]] for the order approval process, and [[logistics]] for the receiving process.

---
title: Nonconformances
status: draft
confidence: low
type: concept
sources: []
---

# Nonconformances

Nonconformance report (NCR) log with containment, disposition, and corrective action. Each NCR record captures:

- **NCR identity** — NCR number, date opened, status (Open / Disposition Pending / Rework / Closed)
- **Nonconformance** — part number, quantity, detection stage; specific deviation from the requirement (dimension, function, appearance, documentation)
- **Containment** — immediate steps taken to prevent the suspect product from reaching the next operation or the customer; hold quantity; customer notification if required
- **Disposition** — decision: Use-as-is (with engineering deviation if required) / Rework / Scrap / Return to Supplier; disposition authority
- **Root cause** — the specific underlying cause identified; root cause category (material, process, equipment, human error, design, supplier); analysis method used (5-Why, 8D, fishbone)
- **Corrective actions** — actions taken to prevent recurrence; owner and due date for each action; verification of effectiveness date and method

Cross-link to [[defect-tracker]] for the aggregate defect data, [[control-plans]] for the control that should have prevented the nonconformance, [[inspection-procedures]] for the inspection that detected it, and [[gauges]] if a gauge failure contributed to the event.

---
title: Cloud Resources
status: draft
confidence: low
type: concept
sources: []
---

# Cloud Resources

Cloud resource inventory with cost, ownership, and tagging compliance. Populate by ingesting cloud resource exports and cost reports.

Each cloud resource record captures:

- **Resource identity** — resource type, resource ID/ARN, cloud provider (AWS / GCP / Azure), region, account/project ID, environment tag (prod / staging / dev)
- **Ownership** — team owner, cost center, business unit; tagging compliance status (required tags present: yes/no)
- **Cost** — monthly cost (from cost explorer or billing export), month-over-month trend, budget alert threshold
- **Utilization** — CPU/memory utilization (for compute), storage used vs. allocated (for storage), request volume (for managed services)
- **Security and compliance** — public exposure (yes/no), encryption at rest (yes/no), encryption in transit (yes/no), compliance labels (PCI / HIPAA / SOC2 scope)
- **Lifecycle** — provisioned date, last modified, scheduled for decommission (date)

**How to populate:**

1. Ingest cloud resource inventory exports (AWS Resource Explorer, GCP Asset Inventory):
   ```
   synthadoc ingest docs/cloud-inventory.json -w <wiki>
   ```
2. Ingest cloud cost reports (AWS Cost Explorer CSV, GCP Billing export)

Cross-link to [[infrastructure]], [[deployments]], and [[slos]].

---
title: Infrastructure
status: draft
confidence: low
type: concept
sources: []
---

# Infrastructure

Infrastructure inventory and IaC documentation. Populate by ingesting Terraform modules, cloud architecture diagrams, and infrastructure READMEs.

Each infrastructure record captures:

- **Resource identity** — resource type (VPC / EKS cluster / RDS / S3 / CloudFront / Load Balancer), name/ID, cloud provider and region, environment
- **IaC reference** — Terraform module path, last apply date, last plan diff; drift detection status
- **Configuration** — key settings (instance type, disk size, replication factor, autoscaling min/max)
- **Network** — VPC, subnets, security groups, NACLs, peering; private vs. public exposure
- **Cost** — monthly cost estimate, cost allocation tag(s), cost optimization opportunities
- **Dependency map** — which services run on this resource (link to [[services]]); what breaks if this resource is unavailable
- **Backup and DR** — backup schedule, retention period, cross-region replication, RTO/RPO targets

**How to populate:**

1. Ingest your Terraform modules README:
   ```
   synthadoc ingest infrastructure/ --batch -w <wiki>
   ```
2. Ingest your cloud architecture diagram or AWS/GCP/Azure architecture decision doc

Cross-link to [[cloud-resources]], [[deployments]], [[slos]], and [[services]].

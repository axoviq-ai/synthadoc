---
title: Data Governance
status: draft
confidence: low
type: concept
sources: []
---

# Data Governance

Data governance policies, data ownership, and classification framework. Populate by ingesting your data governance policy, data dictionary, and classification documentation.

Each governance record captures:

- **Data classification** — classification tiers (Public / Internal / Confidential / Restricted); definition, examples, and handling requirements per tier; who classifies datasets and when
- **Data ownership model** — domain ownership definitions, data owner vs. data steward responsibilities, escalation path for governance disputes
- **Access control** — how access to each classification tier is granted (self-service / approval-required / executives-only), review cadence for access grants, audit logging requirements
- **Retention and deletion** — retention schedule by data type, deletion procedure (hard delete vs. anonymization), legal hold process
- **Privacy and compliance** — PII identification procedure, GDPR/CCPA applicability, data subject rights fulfillment process (right to access, right to deletion)
- **Data quality standards** — minimum quality bar for promotion from raw to mart, quality SLA (completeness, timeliness, accuracy targets)
- **Governance committee** — members, meeting cadence, scope of decisions

Cross-link to [[data-quality]], [[datasets]], [[lineage]], and [[schema-registry]].

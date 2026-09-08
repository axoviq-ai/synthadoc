---
title: Model Registry
status: draft
confidence: low
type: concept
sources: []
---

# Model Registry

Versioned model registry: promoted models, staging candidates, and retired models. Complements [[models]] (which covers model documentation) with the lifecycle and promotion workflow.

Each registry entry captures:

- **Registry entry** — model name, version tag (semantic version or hash), registry stage (Staging / Production / Archived), promoted by, promotion date
- **Promotion criteria** — benchmark thresholds that must be met before moving to Production, A/B test win criteria, safety evaluation pass, stakeholder approval
- **Serving configuration** — hardware requirements (GPU type and count, VRAM), deployment target (link to [[serving-infrastructure]]), replica count, autoscaling policy
- **Rollout plan** — traffic percentage, canary duration, rollback trigger criteria
- **Comparison to previous production model** — delta on key metrics, any regressions in known-important subsets
- **Retirement record** — why the model was retired, when, replacement version

Cross-link to [[models]], [[experiments]], [[serving-infrastructure]], and [[benchmarks]].

---
title: Modules
status: draft
confidence: low
type: concept
sources: []
---

# Modules

Module library for this course or curriculum. Each module page records:

- **Module identity** — module number, title, estimated duration, level (introductory / intermediate / advanced), delivery format (synchronous / asynchronous / blended)
- **Learning objectives** — three to five measurable objectives using Bloom's Taxonomy action verbs; Bloom's level for each
- **Prerequisite modules** — which modules must be completed before this one; what prerequisite knowledge is assumed
- **Content outline** — section-by-section overview of what is covered
- **Learning activities** — active learning components: discussion prompts, case studies, simulations, practice exercises
- **Required materials** — readings, videos, or tools learners need (link to [[learning-materials]])
- **Assessment methods** — formative checks and summative assessment for this module (link to [[assessments]])

**How to populate:**

1. Copy `raw_sources/modules/template-module-design.md`, fill in all fields for each module, then:
   ```
   synthadoc ingest raw_sources/modules/<module-number>-<title>.md -w <wiki>
   ```
2. Ingest existing module design documents or syllabi:
   ```
   synthadoc ingest docs/course-design/modules/ --batch -w <wiki>
   ```

Cross-link to [[learner-outcomes]] for the program objectives each module addresses, [[learning-materials]] for the materials used, [[assessments]] for the assessments included, and [[facilitation-guides]] for instructor delivery guidance.

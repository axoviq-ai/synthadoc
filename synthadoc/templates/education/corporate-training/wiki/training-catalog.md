---
title: Training Catalog
status: draft
confidence: low
type: concept
sources: []
---

# Training Catalog

Complete catalog of all training courses and programs offered by the organization. Each catalog entry captures:

- **Course identity** — course code, title, category (compliance, technical, leadership, onboarding, role-specific), owner or SME
- **Description** — what the course covers in two to three sentences; the problem it solves
- **Target audience** — who should take this course (all employees, specific roles, managers, senior leaders)
- **Format and delivery** — eLearning / ILT / Virtual ILT / Blended; synchronous or self-paced
- **Duration** — total estimated time commitment
- **Prerequisites** — courses or experience required before enrollment
- **Completion requirements** — assessment, quiz score, attestation, or demonstration required for credit
- **Frequency** — at hire / annual / one-time / as-needed
- **LMS enrollment link** — where to enroll; any approval workflow required

**How to populate:**

1. Copy `raw_sources/training/template-training-course.md` for each course, fill in all fields, then:
   ```
   synthadoc ingest raw_sources/training/<course-code>-<title>.md -w <wiki>
   ```
2. Export your LMS course catalog and ingest:
   ```
   synthadoc ingest docs/training/course-catalog-export.csv -w <wiki>
   ```

Cross-link to [[sops]] for courses that teach procedural skills, [[compliance-training]] for the regulatory basis of required courses, [[competency-frameworks]] for competencies each course develops, and [[onboarding-program]] for courses included in new-hire onboarding.

---
title: Assessments
status: draft
confidence: low
type: concept
sources: []
---

# Assessments

Assessment item bank and strategy documentation. Each assessment entry records:

- **Assessment identity** — assessment name or ID, aligned course or module, type (MCQ, written response, performance task, project, peer review, simulation)
- **Aligned learning objective** — which learning objective from [[learner-outcomes]] this assessment measures; the Bloom's cognitive level tested
- **Cognitive level** — Remember / Understand / Apply / Analyze / Evaluate / Create (Bloom's Taxonomy)
- **Scoring** — rubric reference or answer key; maximum points; grading criteria (link to rubric file in [[learning-materials]])
- **Validity evidence** — how item validity was established (content review, expert panel, pilot data, discrimination index)
- **Accessibility accommodations** — extended time, alternative format, assistive technology compatibility
- **Item history** — revision notes; when item was last reviewed; any known issues with distractors or scoring

**How to populate:**

1. Ingest assessment design documents or item banks:
   ```
   synthadoc ingest docs/course-design/assessments/ --batch -w <wiki>
   ```
2. Ingest assessment frameworks as reference:
   ```
   synthadoc ingest "https://www.nwea.org/blog/2026/formative-vs-summative-assessment" -w <wiki>
   ```

Cross-link to [[modules]] for the module where each assessment is used, [[learner-outcomes]] for the objectives being assessed, and [[course-evaluations]] for end-of-course feedback related to assessment difficulty.

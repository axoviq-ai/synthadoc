---
title: Course Evaluations
status: draft
confidence: low
type: concept
sources: []
---

# Course Evaluations

Learner feedback and course effectiveness data. Each evaluation record captures:

- **Evaluation identity** — course name, cohort or session date, evaluation instrument used (Kirkpatrick Level 1 satisfaction survey, knowledge check, behavior observation)
- **Kirkpatrick levels measured**:
  - Level 1 (Reaction) — learner satisfaction rating; top 3 positive comments; top 3 improvement suggestions
  - Level 2 (Learning) — pre/post knowledge assessment scores; mean gain; pass rate
  - Level 3 (Behavior) — follow-up survey or observation data on on-the-job behavior change; timeline for measurement
  - Level 4 (Results) — business outcomes attributable to the training; metrics tracked; time to impact
- **Net Promoter Score** — likelihood to recommend rating and comment summary
- **Facilitator effectiveness** — facilitator-specific ratings; standout feedback
- **Completion rate** — % of enrolled learners who completed the course on time
- **Action items** — specific content, pacing, or design changes the evaluation identified

**How to populate:**

1. Ingest evaluation reports or LMS completion exports:
   ```
   synthadoc ingest docs/course-design/evaluations/ --batch -w <wiki>
   ```
2. Ingest Kirkpatrick framework reference:
   ```
   synthadoc ingest "https://www.kirkpatrickpartners.com/the-kirkpatrick-model" -w <wiki>
   ```

Cross-link to [[modules]] for specific modules that need revision, [[assessments]] for items with poor discrimination data, and [[learner-outcomes]] for objectives where learners consistently underperform.

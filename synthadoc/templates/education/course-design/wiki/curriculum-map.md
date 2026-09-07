---
title: Curriculum Map
status: draft
confidence: low
type: concept
sources: []
---

# Curriculum Map

Visual and tabular map of the curriculum showing scope, sequence, and alignment. Each curriculum map record captures:

- **Curriculum identity** — program or course name, level, target audience, total duration
- **Learning objectives alignment** — table mapping each learning objective to the module(s) and assessment(s) that address it; Bloom's level for each objective
- **Scope** — all topics included; explicitly noted topics that are out of scope
- **Sequence** — the rationale for the order of instruction; prerequisite relationships between modules (link to [[modules]] for each)
- **Vertical alignment** — how this course connects to prerequisite courses and courses that follow in the program
- **Horizontal alignment** — cross-course alignment of shared topics or competencies; how similar topics are taught across parallel courses
- **Coverage gaps** — learning objectives that are currently under-addressed or unaddressed in the curriculum

**How to populate:**

1. Ingest curriculum design documents or program syllabi:
   ```
   synthadoc ingest docs/course-design/curriculum/ --batch -w <wiki>
   ```
2. Ingest backward design references:
   ```
   synthadoc ingest "https://vanguardteachingandlearning.com/resources/align-and-establish-assessments" -w <wiki>
   ```

Cross-link to [[modules]] for each module in the sequence, [[learner-outcomes]] for the program-level objectives, and [[assessments]] for the summative assessments that verify learning.

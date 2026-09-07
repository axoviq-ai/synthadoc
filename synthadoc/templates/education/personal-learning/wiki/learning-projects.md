---
title: Learning Projects
status: draft
confidence: low
type: concept
sources: []
---

# Learning Projects

Projects built or undertaken to learn by doing. Each project record captures:

- **Project identity** — project name, goal in one sentence, status (planned / in progress / completed / abandoned)
- **Learning objective** — what skill, concept, or domain the project is designed to teach; why you chose this project over other learning methods
- **Motivation** — the specific question or curiosity that drove this project
- **What you built or produced** — tangible output (code, writing, prototype, presentation, model, dataset)
- **Key learning moments** — the three to five most important things you learned while doing the project; include mistakes and surprises
- **Techniques and tools used** — languages, frameworks, methods, instruments
- **Resources that helped** — courses, books, tutorials, mentors that were most useful (link to [[courses-taken]], [[books]])
- **What I would do differently** — what you learned about how to learn, not just what you learned about the subject

**How to populate:**

1. Ingest project documentation or README files:
   ```
   synthadoc ingest docs/projects/ --batch -w <wiki>
   ```
2. Create a project entry directly from notes:
   ```
   synthadoc ingest raw_sources/books/<project-notes>.md -w <wiki>
   ```

Cross-link to [[courses-taken]] for the course that inspired or accompanied the project, [[concepts]] for the ideas the project made concrete, and [[books]] for the resources most useful during the project.

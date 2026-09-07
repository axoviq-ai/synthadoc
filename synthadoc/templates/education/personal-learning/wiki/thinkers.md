---
title: Thinkers
status: draft
confidence: low
type: concept
sources: []
---

# Thinkers

Index of thinkers, intellectuals, and domain experts whose work you study. Each thinker page records:

- **Thinker identity** — name, primary domain (psychology, economics, philosophy, science, business, etc.), dates (birth–death or birth–present)
- **Core contribution** — what this person is known for; their single most important idea or work
- **Body of work** — key books, essays, lectures, or papers; which ones you have read (link to [[books]] and [[book-summaries]])
- **Core ideas and frameworks** — the three to five concepts this thinker is most associated with (link to [[mental-models]] and [[concepts]] for each)
- **Worldview or methodology** — how they approach their domain; what lens or method makes their work distinctive
- **Critiques and limitations** — where other scholars or your own reading pushes back on their ideas
- **Why I study this person** — what attracted you to their work; what question of yours they help answer

**How to populate:**

1. Ingest a thinker's primary work or a biography:
   ```
   synthadoc ingest raw_sources/books/<author-last>-<year>-<keyword>.md -w <wiki>
   ```
2. Ingest profiles and interviews:
   ```
   synthadoc ingest "https://www.edge.org/conversations/<thinker-name>" -w <wiki>
   ```

Cross-link to [[books]] for their works, [[mental-models]] for frameworks they introduced, and [[concepts]] for atomic ideas you extracted from their work.

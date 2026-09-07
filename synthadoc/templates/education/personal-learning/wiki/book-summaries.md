---
title: Book Summaries
status: draft
confidence: low
type: concept
sources: []
---

# Book Summaries

Long-form summaries and annotated notes on books read. Each summary page captures:

- **Book identity** — title, author, year (link to [[books]] entry)
- **Why this book matters** — what question it answers; why you read it now
- **Chapter-by-chapter outline** — brief summary of each chapter or major section (optional: detail level varies by book importance)
- **The best ideas from this book** — expanded notes on the 3–5 ideas you want to retain; in your own words with enough context to understand them six months later
- **Best quotes** — the five to ten quotes worth memorizing or revisiting; with page numbers
- **Connections** — ideas from this book that connect to other books, concepts, or mental models you already know (link to [[concepts]] and [[mental-models]])
- **How I changed my thinking** — what this book changed about how you see something

**How to populate:**

1. Copy `raw_sources/books/template-book-notes.md`, fill in chapter notes and extended commentary, then:
   ```
   synthadoc ingest raw_sources/books/<author-last>-<year>-<keyword>.md -w <wiki>
   ```
2. Ingest published book summaries as a starting point (then annotate with your own notes):
   ```
   synthadoc ingest "https://www.blinkist.com/en/books/<book-slug>" -w <wiki>
   ```

Cross-link to [[books]] for the brief entry, [[concepts]] for atomic ideas worth making into standalone notes, and [[thinkers]] for the author's broader work.

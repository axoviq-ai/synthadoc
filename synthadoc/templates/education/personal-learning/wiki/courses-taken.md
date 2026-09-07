---
title: Courses Taken
status: draft
confidence: low
type: concept
sources: []
---

# Courses Taken

Log of formal courses, MOOCs, workshops, and structured programs completed. Each course record captures:

- **Course identity** — title, provider (Coursera, edX, MIT OCW, university, workshop organizer), instructor, format (online / in-person / hybrid)
- **Subject area** — the domain or skill the course covered
- **Dates** — start date; completion date (or "in progress")
- **Effort** — approximate hours invested; course depth (beginner / intermediate / advanced)
- **Credential** — certificate, grade, or credential earned; where it is stored
- **Key takeaways** — the three to five most valuable things you learned
- **Projects or exercises completed** — notable assignments, projects, or labs (link to [[learning-projects]] if you built something)
- **What I would do differently** — honest reflection on how you studied and what you would change

**How to populate:**

1. Ingest course syllabi or completion certificates:
   ```
   synthadoc ingest docs/learning/courses/ --batch -w <wiki>
   ```
2. Ingest a specific course description from the provider's website:
   ```
   synthadoc ingest "https://www.coursera.org/learn/<course-slug>" -w <wiki>
   ```

Cross-link to [[concepts]] for atomic ideas from the course, [[learning-projects]] for projects built during the course, and [[books]] for the textbooks or readings assigned.

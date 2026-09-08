---
title: Surveys
status: draft
confidence: low
type: concept
sources: []
---

# Surveys

Survey studies conducted or commissioned. Populate by ingesting survey instruments, data, and topline reports.

Each survey record captures:

- **Survey identity** — survey name, date fielded, fielding method (online panel / customer email / intercept), tool used (Qualtrics / Typeform / SurveyMonkey)
- **Sample** — N complete responses, target population, sampling approach, response rate, demographic breakdown
- **Questionnaire summary** — major sections or question groups; scale types used (Likert / NPS / ranking / open-ended)
- **Key findings** — top 5 findings from the topline; verbatim themes from open-ended questions
- **Data availability** — where the raw data lives, access restrictions, whether the survey can be fielded again (tracking study)
- **Weighting and caveats** — any weighting applied, sample limitations, margin of error

**How to populate:**

1. Ingest your topline survey report:
   ```
   synthadoc ingest docs/surveys/<survey>-topline.pdf -w <wiki>
   ```

Cross-link to [[customer-insights]], [[consumer-segments]], and [[research-reports]].

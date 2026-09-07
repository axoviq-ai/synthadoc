---
title: Patent Prosecution
status: draft
confidence: low
type: concept
sources: []
---

# Patent Prosecution

Active prosecution log tracking the status of pending patent applications through examination. Each prosecution record captures:

- **Application identity** — application number, title, filing date, jurisdiction, prosecution counsel or agent
- **Current status** — awaiting examination / office action received / response filed / notice of allowance / abandoned
- **Examination history** — chronological log of examiner actions and applicant responses with dates and deadlines
- **Key office action issues** — rejection grounds raised by the examiner (prior art, obviousness, enablement, claim indefiniteness)
- **Response strategy** — planned arguments or claim amendments; whether to interview the examiner
- **Deadlines** — response deadline for current examiner action; extension fees if response will be late
- **Prosecution cost to date** — running total of official fees and attorney fees for this application
- **Related applications** — continuation, divisional, or continuation-in-part applications filed from the same parent

**How to populate:**

1. Ingest USPTO prosecution history (file wrapper) from Patent Center:
   ```
   synthadoc ingest "https://patentcenter.uspto.gov/applications/<application-number>/continuity" -w <wiki>
   ```
2. Ingest prosecution docket exports from your IP management system:
   ```
   synthadoc ingest docs/ip/prosecution/ --batch -w <wiki>
   ```

Cross-link to [[patent-portfolio]] for the eventual granted patent and [[ip-strategy]] for the filing criteria that justified the application.

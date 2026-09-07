---
title: Litigation
status: draft
confidence: low
type: concept
sources: []
---

# Litigation

Active and historical litigation docket. Each case page records:

- **Case identity** — case name, docket number, court / tribunal, jurisdiction
- **Parties** — plaintiff(s) and defendant(s); whether entity is plaintiff or defendant in this matter
- **Cause of action** — legal claims asserted; counterclaims if any
- **Damages** — amount in controversy (claimed by each side); any injunctive relief sought
- **Counsel** — lead internal attorney, external litigation counsel (firm + lead partner)
- **Case timeline** — complaint filed, answer due / filed, discovery open / close, dispositive motion deadlines, trial date
- **Litigation hold** — hold issued date, custodians covered, preservation scope
- **Current status** — active phase (pleadings, discovery, expert disclosure, summary judgment, trial, appeal, settlement discussions)
- **Risk assessment** — probability of adverse outcome; potential exposure range; reserve amount
- **Case strategy** — key arguments; anticipated motions; settlement posture

**How to populate:**

1. Create a matter record first using [[matters]], then ingest the complaint or key pleadings:
   ```
   synthadoc ingest docs/legal/litigation/<case-name>/complaint.pdf -w <wiki>
   ```
2. Ingest case status summaries:
   ```
   synthadoc ingest docs/legal/litigation/<case-name>/ --batch -w <wiki>
   ```

Cross-link to [[matters]], [[outside-counsel]], [[contracts]] (if dispute arises from a contract), and [[case-law]] for precedents cited.

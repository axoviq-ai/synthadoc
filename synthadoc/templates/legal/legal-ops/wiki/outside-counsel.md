---
title: Outside Counsel
status: draft
confidence: low
type: concept
sources: []
---

# Outside Counsel

Panel and directory of approved outside law firms and attorneys. Each firm page records:

- **Firm identity** — firm name, office location(s) used, firm size and Chambers / Legal 500 ranking if applicable
- **Practice areas** — which matters this firm handles for the organization (litigation, M&A, employment, IP, regulatory, etc.)
- **Relationship** — whether on preferred panel; primary relationship partner; relationship start date
- **Billing rates** — partner, associate, and paralegal hourly rates; any blended rate or alternative fee arrangement (AFA) in place
- **Outside counsel guidelines** — version of guidelines this firm is operating under; acknowledgment date
- **Diversity metrics** — diversity of staffing on organization matters (if tracked)
- **Active matters** — link to current [[matters]] assigned to this firm
- **Performance notes** — responsiveness, budget adherence, quality of work product

**How to populate:**

1. Ingest your outside counsel guidelines document:
   ```
   synthadoc ingest docs/legal/outside-counsel-guidelines.pdf -w <wiki>
   ```
2. Ingest firm engagement letters or rate confirmation agreements:
   ```
   synthadoc ingest docs/legal/firms/ --batch -w <wiki>
   ```
3. Ingest ACC model outside counsel guidelines as a reference:
   ```
   synthadoc ingest "https://tenthings.blog/2016/11/30/ten-things-preparing-outside-counsel-guidelines-the-keys" -w <wiki>
   ```

Cross-link to [[matters]] and [[contracts]] for engagements managed by each firm.

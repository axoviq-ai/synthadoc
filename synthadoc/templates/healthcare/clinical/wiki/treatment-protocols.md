---
title: Treatment Protocols
status: draft
confidence: low
type: concept
sources: []
---

# Treatment Protocols

Evidence-based treatment algorithms by condition. Each protocol page specifies:

- **Protocol identity** — protocol title, condition treated, setting (inpatient / outpatient / ICU), version, effective date, author and reviewer
- **Patient selection** — eligible patient criteria; inclusion and exclusion criteria
- **First-line therapy** — recommended initial treatment with dose, route, and duration; evidence grade (cite the supporting guideline with link to [[clinical-guidelines]])
- **Alternative agents** — options when first-line is contraindicated or fails; conditions for switching
- **Escalation criteria** — clinical or laboratory thresholds that trigger step-up therapy or specialist referral
- **Monitoring parameters** — what to monitor, how frequently, and target ranges
- **Treatment duration** — planned course length; criteria for extending or discontinuing treatment
- **Response endpoints** — clinical or laboratory criteria used to assess treatment response

**How to populate:**

1. Ingest department or institutional protocols:
   ```
   synthadoc ingest docs/clinical/protocols/ --batch -w <wiki>
   ```
2. Ingest treatment guidelines from professional societies:
   ```
   synthadoc ingest "https://www.idsociety.org/practice-guideline/<guideline>" -w <wiki>
   ```

Cross-link to [[conditions]] for the treated diagnosis, [[medications]] for drugs used in the protocol, [[clinical-guidelines]] for the supporting evidence, and [[clinical-procedures]] for any procedures the protocol includes.

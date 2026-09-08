# Post-Mortem: [Incident ID] — [Incident Title]

> **How to use this form**
>
> This template follows the **Google SRE Blameless Post-Mortem** format (Google SRE Book, Chapter 15) --
> the industry standard for systematic incident review focused on systemic improvement.
> If you already have a post-mortem in another format, skip this form and ingest your document directly.
>
> Reference: [Google SRE Book — Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)
>
> 1. Copy this file and rename it (e.g. `pm-inc-0123-api-gateway-timeout.md`)
> 2. Fill in within 48 hours of incident resolution; circulate for review within 5 business days
> 3. Run: `synthadoc ingest raw_sources/post-mortems/<filename>.md -w <wiki>`
>
> Blameless means: describe systemic causes, not individual fault.
> The goal is permanent prevention — not assigning blame.

---

## Post-Mortem Identity

- **Post-mortem ID:** PM-
- **Incident ID:** INC- (link to [[incidents]])
- **Title:**
- **Severity:** (SEV1 / SEV2)
- **Incident date:** YYYY-MM-DD
- **Post-mortem authors:**
- **Reviewers:**
- **Review meeting date:** YYYY-MM-DD

---

## Executive Summary

*(One paragraph: what happened, how long it lasted, which systems and users were affected,
and what was done to resolve it. Write for a non-technical executive audience.)*

---

## Impact

- **Incident duration:** HH:MM (from first alert to resolution)
- **Peak error rate:** %
- **Users affected:** (estimated count or %)
- **Revenue impact (estimate):** $
- **Business impact:** (e.g. "checkout unavailable in EU region; ~N orders could not be placed")
- **SLO impact:** (% of error budget consumed by this incident)

---

## Timeline

*All times in UTC. Include: when the alert fired, who noticed, what each person did,
when root cause was identified, when mitigation was applied, when service was restored.*

| UTC Timestamp | Event | Who | Action taken |
|---------------|-------|-----|--------------|
| | Alert fired | PagerDuty | Page sent to on-call |
| | IC assigned | | |
| | Initial investigation | | |
| | Root cause identified | | |
| | Mitigation applied | | |
| | Service restored | | |
| | Incident resolved | | |

---

## Root Cause Analysis

*Use the 5-Why technique: keep asking "Why did that happen?" until you reach a systemic
cause that, if fixed, would prevent the entire class of incident — not just this occurrence.*

- **Why did the incident occur?**
  Because: 

- **Why did that happen?**
  Because: 

- **Why did that happen?**
  Because: 

- **Why did that happen?**
  Because: 

- **Why did that happen? (root cause)**
  Because: 

**Root cause summary:** (one clear sentence naming the systemic cause)

---

## Contributing Factors

*Factors that made the incident worse, harder to detect, or slower to resolve —
distinct from the root cause.*

-
-
-

---

## What Went Well

*Things the team did effectively that are worth repeating.*

-
-
-

---

## What Went Poorly

*Process, tooling, or documentation gaps that slowed detection or resolution.*

-
-
-

---

## Action Items

*Concrete, assignable improvements. Each item must have an owner and a target date.
P0 = fix before next deploy; P1 = fix this sprint; P2 = fix this quarter.*

| Item | Owner | Priority | Target Date | Status |
|------|-------|----------|-------------|--------|
| | | P0/P1/P2 | YYYY-MM-DD | Open |
| | | | | |

---

## Lessons Learned

*What will the team do differently as a result of this incident?
Distill the action items into lasting behaviour changes.*

-

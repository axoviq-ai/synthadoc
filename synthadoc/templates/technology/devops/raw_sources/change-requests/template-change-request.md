# Change Request: [CR-NNNN] — [Change Title]

> **How to use this form**
>
> This template follows the **ITIL 4 Change Enablement practice** -- the widely adopted
> framework for managing changes to production systems in a controlled, risk-assessed manner.
> If you already have change requests in another format, skip this form and ingest them directly.
>
> Reference: [ITIL 4 Foundation — Change Enablement](https://www.axelos.com/certifications/itil-service-management/itil-4-foundation)
>
> 1. Copy this file and rename it (e.g. `cr-0042-database-index-addition.md`)
> 2. Fill in all sections and obtain CAB approval before the change window
> 3. Run: `synthadoc ingest raw_sources/change-requests/<filename>.md -w <wiki>`
>
> Emergency changes: obtain retrospective approval within 24 hours of the change.

---

## Change Identity

- **Change ID:** CR-
- **Title:**
- **Type:** (Standard — pre-approved low-risk / Normal — requires CAB approval / Emergency — immediate risk mitigation)
- **Requested by:**
- **Request date:** YYYY-MM-DD
- **Target change window:** YYYY-MM-DD HH:MM – HH:MM UTC
- **Services affected:** (link to [[services]])

---

## Change Description

**What is changing?**
*(Describe the change precisely — which systems, configurations, code versions, or data are being modified.)*

**Why is this change needed?**
*(Business or technical justification — ticket reference, incident prevention, compliance requirement.)*

---

## Risk Assessment

- **Risk level:** (Low / Medium / High)
- **Risk rationale:** (one sentence explaining the risk level)

| Risk | Likelihood (H/M/L) | Impact (H/M/L) | Mitigation |
|------|--------------------|----------------|------------|
| Service disruption during change | | | |
| Data loss or corruption | | | |
| Partial rollout leaving inconsistent state | | | |
| | | | |

---

## Impact Assessment

- **Services affected:** (list; mark as direct or indirect impact)
- **Expected downtime:** (none / N minutes of degraded performance / planned maintenance window)
- **Blast radius if change fails:** (e.g. "payments API unavailable for all users")
- **Dependent teams to notify:** (teams whose services may be affected)
- **Customer communication required?** (yes / no — if yes, draft notification text separately)

---

## Implementation Plan

*Numbered steps in execution order. Include exact commands, configuration values, and
the expected output after each step. Someone other than the author must be able to execute
this plan without asking questions.*

1. (Step 1 — what to do, expected output)
   ```
   # command if applicable
   ```

2. (Step 2)

3. (Verify health post-change)
   ```
   # health check command
   ```

**Estimated duration:** minutes / hours

---

## Rollback Plan

*Steps to fully reverse this change if the acceptance criteria are not met.
Include the decision criteria that trigger a rollback.*

**Rollback trigger criteria:**
- Error rate increases above N% after the change, OR
- P99 latency exceeds N ms for more than 5 minutes, OR
- Any step in the implementation plan cannot be completed

**Rollback steps:**

1.
2.

**Expected rollback duration:** minutes

---

## Test Plan

**How will you verify the change succeeded?**

| Test | Method | Acceptance Criterion |
|------|--------|----------------------|
| Health check | | `{"status": "ok"}` |
| Smoke test | | |
| Load test (if applicable) | | |

---

## Approval

- **CAB approval required?** (yes — Normal/Emergency / no — Standard)
- **Approved by:**
- **Approval date:** YYYY-MM-DD
- **Change window confirmed:** YYYY-MM-DD HH:MM – HH:MM UTC

---

## Outcome

*(Fill in after the change is complete.)*

- **Result:** (Successful / Rolled back / Partially completed)
- **Actual duration:** minutes
- **Deviations from plan:** (describe any steps that differed from the implementation plan)
- **Follow-up required:** (open tickets, monitoring period, retrospective scheduled)

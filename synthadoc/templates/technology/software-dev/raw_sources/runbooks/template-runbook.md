# Runbook: [Service Name] — [Procedure Title]

> **How to use this form**
>
> This template follows the **Google SRE Workbook, Chapter 9** -- the standard for
> operational runbooks used by Site Reliability Engineering teams.
> If you already have runbooks in another format, skip this form and ingest them directly.
>
> Reference: [Google SRE Workbook — On-Call](https://sre.google/workbook/on-call/)
>
> 1. Copy this file and rename it (e.g. `payments-service-high-error-rate.md`)
> 2. Fill in all sections; validate steps in a non-production environment before publishing
> 3. Run: `synthadoc ingest raw_sources/runbooks/<filename>.md -w <wiki>`
>
> Review this runbook after every incident where it was used — update steps that were unclear or wrong.

---

## Runbook Identity

- **Service:** (link to [[services]])
- **Title:** (e.g. "High error rate — payments service")
- **Version:** 1.0
- **Last reviewed:** YYYY-MM-DD
- **Owner team:**
- **Primary on-call contact:**
- **Alert that triggers this runbook:** (alert name or PagerDuty policy)

---

## Service Overview

- **What this service does:** (one sentence)
- **Criticality:** (P0 — customer-facing revenue / P1 — internal critical / P2 — non-critical)
- **SLO:** (e.g. "99.9% availability over 30-day rolling window")
- **Key dependencies:** (services this service calls; databases; external APIs)
- **Useful dashboards:** (links to Grafana / Datadog / CloudWatch)

---

## Alert / Trigger

- **Alert name:**
- **Condition:** (what threshold fires this alert — e.g. "error rate > 1% for 5 min")
- **Typical causes:** (brief list of the most common root causes for this alert)

---

## Prerequisites

*Confirm you have all of the following before starting:*

- [ ] Access to: (AWS console / kubectl / database read replica / PagerDuty)
- [ ] Tools installed: (kubectl, aws-cli, psql, jq — version requirements if any)
- [ ] Environment variables set: (`AWS_REGION`, `KUBECONFIG`, etc.)
- [ ] Slack channel for incident coordination: `#incidents`

---

## Diagnosis Steps

*Work through these steps in order. Each step has a command and an expected outcome.
Branch to the indicated step when you see the outcome described.*

1. **Verify the alert is real (not a false positive)**

   ```
   # Check current error rate
   kubectl top pods -n <namespace>
   ```

   Expected: pods are running normally.
   If pods are crash-looping → go to Step 3.
   If pods look healthy → go to Step 2 (check upstream dependencies).

2. **Check upstream dependencies**

   ```
   # Check dependency health
   curl -s https://<dependency-host>/health | jq .
   ```

   Expected: `{"status": "ok"}`.
   If dependency is down → escalate to the owning team; see [Escalation](#escalation).

3. **Check recent deployments**

   ```
   kubectl rollout history deployment/<service> -n <namespace>
   ```

   If a deploy occurred in the last 30 minutes → proceed to Resolution Step 1 (rollback).

4. **Examine pod logs for error patterns**

   ```
   kubectl logs -l app=<service> -n <namespace> --tail=100 | grep -i error
   ```

   Expected: no critical errors.
   If you see `connection refused` → check database connectivity (Step 5).
   If you see `OOMKilled` → check memory limits (Step 6).

5. **Check database connectivity**

   ```
   # From a pod in the cluster:
   kubectl exec -it <pod-name> -n <namespace> -- psql -h <db-host> -U <user> -c "SELECT 1;"
   ```

6. **Check resource limits**

   ```
   kubectl describe pod <pod-name> -n <namespace> | grep -A5 Limits
   ```

---

## Resolution Steps

*Apply fixes in order. Verify the success criterion before moving to the next step.*

1. **Rollback to previous version** (if a recent deploy caused the issue)

   ```
   kubectl rollout undo deployment/<service> -n <namespace>
   kubectl rollout status deployment/<service> -n <namespace>
   ```

   Success criterion: error rate drops below 0.1% within 5 minutes.

2. **Restart unhealthy pods** (if no recent deploy, and pods are stuck)

   ```
   kubectl rollout restart deployment/<service> -n <namespace>
   ```

   Success criterion: all pods reach `Running` state; error rate normalises.

3. **Scale out replicas** (if load spike is the cause)

   ```
   kubectl scale deployment/<service> --replicas=<N> -n <namespace>
   ```

   Success criterion: CPU utilisation per pod drops below 70%; latency recovers.

---

## Rollback Procedure

*Use this if Resolution Steps make the situation worse.*

```
kubectl rollout undo deployment/<service> -n <namespace>
```

**Decision criteria for rollback:** error rate increases or P99 latency doubles after any resolution step.

**Expected time to rollback:** < 5 minutes.

---

## Escalation

Escalate if:
- You cannot identify the root cause within 30 minutes, OR
- The incident is SEV1 or SEV2 (customer-facing outage or significant degradation)

| Tier | Contact | How | What to provide |
|------|---------|-----|-----------------|
| Primary on-call | (name / PagerDuty rotation) | Page | Alert name, start time, error rate, steps tried |
| Service owner | (name / Slack handle) | Slack DM | Same as above + pod logs snippet |
| VP Engineering | (name) | Phone | Only if revenue impact > $X or duration > 60 min |

---

## Post-Incident

After the incident is resolved:

- [ ] Update the incident record in `raw_sources/incidents/` and re-ingest
- [ ] File a post-mortem if SEV1 or SEV2 (see `raw_sources/post-mortems/template-post-mortem.md`)
- [ ] Update this runbook if any steps were unclear or wrong
- [ ] Add a "Known issues" entry if a workaround was used that is not yet fixed

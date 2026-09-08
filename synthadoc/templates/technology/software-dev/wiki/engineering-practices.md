---
title: Engineering Practices
status: draft
confidence: low
type: concept
sources: []
---

# Engineering Practices

Team norms, coding standards, and development workflow. Populate by ingesting your engineering handbook, style guides, and onboarding docs.

Each engineering practice record captures:

- **Development workflow** — branching strategy (trunk-based / gitflow / feature branches), PR size conventions, review requirements (number of approvals, required reviewers)
- **Code review standards** — what reviewers check (correctness, readability, test coverage, security, performance), review SLA, blocking vs. non-blocking feedback conventions
- **Testing standards** — required test types (unit / integration / e2e / contract), minimum coverage thresholds, test pyramid target ratios, flaky test policy
- **Release process** — deploy frequency target, environment promotion path (dev → staging → prod), feature flags usage, rollback procedure
- **Observability standards** — required instrumentation (logs, metrics, traces), log format (structured JSON), metric naming conventions, trace sampling rate
- **Security practices** — secret management (no secrets in code, approved secret stores), dependency scanning, SAST/DAST tooling, vulnerability SLA by severity
- **On-call and incident response** — on-call rotation setup, alert ownership, severity definitions, link to [[incident-response]]

Cross-link to [[runbooks]], [[incident-response]], and [[tech-debt]].

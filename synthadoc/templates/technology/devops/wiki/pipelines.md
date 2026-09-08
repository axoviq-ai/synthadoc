---
title: Pipelines
status: draft
confidence: low
type: concept
sources: []
---

# Pipelines

CI/CD pipeline catalog for all services. Populate by ingesting CI pipeline configuration and pipeline run history.

Each pipeline record captures:

- **Pipeline identity** — pipeline name, service (link to [[services]]), CI platform (GitHub Actions / Jenkins / CircleCI / GitLab CI), trigger (push / PR / schedule / manual)
- **Stages** — ordered list of stages: lint → unit tests → build → integration tests → security scan → deploy to staging → smoke test → deploy to prod → post-deploy verification
- **Quality gates** — required pass rate for tests, code coverage floor, SAST/DAST scan pass required, performance regression threshold
- **Secrets and credentials** — secret store used (GitHub Secrets / AWS Secrets Manager / Vault), which secrets the pipeline consumes, rotation cadence
- **DORA metrics** — deployment frequency target, lead time for changes (P50), change failure rate, mean time to restore — compared to current team actuals
- **Flaky tests** — known flaky tests, their quarantine status, owner, remediation target date

Cross-link to [[deployments]], [[services]], [[alerts]], and [[slos]].

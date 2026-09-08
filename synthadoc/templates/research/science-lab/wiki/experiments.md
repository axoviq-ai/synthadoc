---
title: Experiments
status: draft
confidence: low
type: concept
sources: []
---

# Experiments

Lab experiment log. Populate by ingesting experiment summaries from `raw_sources/experiments/`.

Each experiment record captures:

- **Identity** — experiment ID, date, experimenter, PI, protocol used (link to [[protocols]])
- **Objective and hypothesis** — research question and specific hypothesis being tested (link to [[hypotheses]])
- **Materials** — reagents with lot numbers and amounts used (link to [[reagents]]), equipment with model and settings
- **Procedure summary** — reference to the full protocol; any deviations from the standard protocol documented
- **Results** — quantitative measurements (table), qualitative observations, raw data file locations
- **Interpretation** — whether the result supported the hypothesis, key observations, unexpected results
- **Next steps** — follow-up experiments, parameter adjustments, replication plans

**How to add an experiment:**

1. Copy `raw_sources/experiments/template-lab-experiment.md`, fill in before and after the run, then:
   ```
   synthadoc ingest raw_sources/experiments/<experiment>.md -w <wiki>
   ```

Your electronic lab notebook (ELN) remains the primary record.

Cross-link to [[protocols]], [[reagents]], [[instruments]], [[findings]], and [[raw-data]].

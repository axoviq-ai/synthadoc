---
title: Portfolio
status: draft
confidence: low
type: concept
sources: []
---

# Portfolio

Portfolio-level investment strategy and target return metrics. Populate by ingesting a completed portfolio goals form from `raw_sources/portfolio/`.

The portfolio page captures:

- **Identity** — investor or entity name, portfolio name, date of last revision
- **Investment strategy** — strategy type (core / value-add / opportunistic), asset classes, target markets, typical hold period, financing approach, reinvestment policy
- **Target return metrics** — minimum IRR, equity multiple (EM), average cash-on-cash, DSCR at acquisition, going-in cap rate, and GRM thresholds
- **Asset allocation targets** — target mix by property type and market, max single-asset concentration, target portfolio size
- **Risk tolerance & constraints** — vacancy and expense growth underwriting rates, sensitivity floor, max LTV, per-property cash reserve requirement

**How to set your portfolio goals:**

1. Copy `raw_sources/portfolio/template-portfolio-goals.md` and rename it
2. Fill in your strategy and target metrics
3. Run `synthadoc ingest raw_sources/portfolio/portfolio-goals.md -w <wiki>`
4. Re-ingest whenever strategy or thresholds change

These metrics become the benchmark when you query projected returns across [[financial-models]] and compare actuals in [[properties]].

# AquaFlow M&A Knowledge Base — Example

A private equity M&A knowledge base demonstrating multi-page wiki ingestion with cross-linked deal-specific and reference pages.

## What this example shows

Eight raw source documents covering **distinct entities** produce eight separate wiki pages:

| Source file | Expected wiki page |
|-------------|-------------------|
| `01_aquaflow_company_profile.md` | `aquaflow-systems` — company profile |
| `02_water_infrastructure_market.md` | `water-infrastructure-market` — sector analysis |
| `03_lbo_model_mechanics.md` | `lbo-model-structure` — LBO methodology |
| `04_covenant_analysis_framework.md` | `covenant-analysis` — financial covenants |
| `05_quality_of_earnings_guide.md` | `qoe-adjustments` — QoE methodology |
| `06_esg_due_diligence_standards.md` | `esg-due-diligence` — ESG framework |
| `07_legal_due_diligence_process.md` | `legal-due-diligence` — legal DD process |
| `08_exit_valuation_benchmarks.md` | `exit-multiples-and-valuation` — exit strategy |

## Quick start

```bash
synthadoc install aquaflow --target ~/wikis
cp raw_sources/* ~/wikis/aquaflow/raw_sources/

synthadoc ingest raw_sources/01_aquaflow_company_profile.md -w aquaflow
synthadoc ingest raw_sources/02_water_infrastructure_market.md -w aquaflow
synthadoc ingest raw_sources/03_lbo_model_mechanics.md -w aquaflow
synthadoc ingest raw_sources/04_covenant_analysis_framework.md -w aquaflow
synthadoc ingest raw_sources/05_quality_of_earnings_guide.md -w aquaflow
synthadoc ingest raw_sources/06_esg_due_diligence_standards.md -w aquaflow
synthadoc ingest raw_sources/07_legal_due_diligence_process.md -w aquaflow
synthadoc ingest raw_sources/08_exit_valuation_benchmarks.md -w aquaflow

synthadoc scaffold -w aquaflow
```

## Sample queries

- "What is AquaFlow's EBITDA margin and revenue breakdown?"
- "Explain the covenant headroom at entry and what happens in a downside scenario."
- "What ESG improvements should be prioritized post-close?"
- "How does the PFAS regulatory tailwind affect AquaFlow's exit multiple potential?"
- "What are the key risks in this LBO structure?"

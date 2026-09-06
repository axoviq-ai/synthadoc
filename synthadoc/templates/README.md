# Domain Templates

Domain templates give a freshly installed wiki a head start: pre-configured
agent guidelines, a query routing table, domain-specific purpose and index
pages, and 3–4 scaffold pages covering the most common concepts in that field.

Unlike the built-in demo wikis (which contain real ingested content), templates
are **structure-only** starting points. On first install the pages hold concise
descriptions and frontmatter; the substance comes from your own ingested sources.
A `wiki/seeds.md` page in each template recommends the best first URLs to ingest
and web searches to find them.

## Quick install

```bash
# Browse all 30 options
synthadoc templates list

# Install with a domain template
synthadoc install my-finance-wiki --target ~/wikis --template finance/investment

# Optional: override the domain name shown to the AI
synthadoc install my-wiki --target ~/wikis --template real-estate/investment \
  --domain "Acme Property Portfolio"
```

Staging is automatically enabled for all template installs so that every new
ingest lands in the review queue first.

---

## Finance

| Template | Domain | Install command |
|---|---|---|
| `investment` | Investment research, portfolio management, M&A analysis | `synthadoc install my-wiki --template finance/investment` |
| `mortgage` | Loan origination, underwriting, and servicing workflows | `synthadoc install my-wiki --template finance/mortgage` |
| `banking` | Retail and commercial banking operations and products | `synthadoc install my-wiki --template finance/banking` |
| `accounting` | Financial reporting, audit, and tax compliance | `synthadoc install my-wiki --template finance/accounting` |

## Technology

| Template | Domain | Install command |
|---|---|---|
| `software-dev` | Codebase docs, ADRs, runbooks, and engineering decisions | `synthadoc install my-wiki --template technology/software-dev` |
| `devops` | Infrastructure, CI/CD, SRE, and incident management | `synthadoc install my-wiki --template technology/devops` |
| `ai-ml` | ML research, model tracking, experiments, and benchmarks | `synthadoc install my-wiki --template technology/ai-ml` |
| `data-engineering` | Pipelines, data quality, schema registry, and lineage | `synthadoc install my-wiki --template technology/data-engineering` |

## Healthcare

| Template | Domain | Install command |
|---|---|---|
| `clinical` | Patient protocols, clinical guidelines, and evidence-based medicine | `synthadoc install my-wiki --template healthcare/clinical` |
| `pharmaceutical` | Drug development, regulatory submissions, and clinical trials | `synthadoc install my-wiki --template healthcare/pharmaceutical` |
| `public-health` | Epidemiology, population health, and policy research | `synthadoc install my-wiki --template healthcare/public-health` |

## Legal

| Template | Domain | Install command |
|---|---|---|
| `legal-ops` | Contracts, case law, legal research, and matter management | `synthadoc install my-wiki --template legal/legal-ops` |
| `compliance` | Regulatory requirements, audit trails, and risk register | `synthadoc install my-wiki --template legal/compliance` |
| `ip-management` | Patents, trademarks, and licensing agreements | `synthadoc install my-wiki --template legal/ip-management` |

## Research

| Template | Domain | Install command |
|---|---|---|
| `academic` | Academic papers, literature review, hypotheses, and experimental notes | `synthadoc install my-wiki --template research/academic` |
| `science-lab` | Lab protocols, experiments, instrument logs, and findings | `synthadoc install my-wiki --template research/science-lab` |
| `market-research` | Consumer insights, competitive intelligence, and survey research | `synthadoc install my-wiki --template research/market-research` |

## Operations

| Template | Domain | Install command |
|---|---|---|
| `manufacturing-qc` | Quality control, defect tracking, process specs, and standards | `synthadoc install my-wiki --template operations/manufacturing-qc` |
| `facility-management` | Equipment maintenance, work orders, and asset tracking | `synthadoc install my-wiki --template operations/facility-management` |
| `supply-chain` | Vendor management, logistics, procurement, and inventory | `synthadoc install my-wiki --template operations/supply-chain` |

## Education

| Template | Domain | Install command |
|---|---|---|
| `course-design` | Curriculum development, lesson plans, and learning objectives | `synthadoc install my-wiki --template education/course-design` |
| `personal-learning` | Study notes, Zettelkasten, book summaries, and learning progress | `synthadoc install my-wiki --template education/personal-learning` |
| `corporate-training` | Onboarding programs, SOPs, and employee skill development | `synthadoc install my-wiki --template education/corporate-training` |

## Real Estate

| Template | Domain | Install command |
|---|---|---|
| `investment` | Property underwriting, cap rates, NOI analysis, and portfolio management | `synthadoc install my-wiki --template real-estate/investment` |
| `property-management` | Lease management, tenant relations, maintenance, and work orders | `synthadoc install my-wiki --template real-estate/property-management` |
| `development` | Construction, permitting, zoning, and contractor management | `synthadoc install my-wiki --template real-estate/development` |

## Business

| Template | Domain | Install command |
|---|---|---|
| `product-management` | Product requirements, roadmaps, customer research, and feature specs | `synthadoc install my-wiki --template business/product-management` |
| `marketing` | Campaigns, content strategy, brand guidelines, and channel performance | `synthadoc install my-wiki --template business/marketing` |
| `hr-people` | HR policies, org design, job frameworks, and performance management | `synthadoc install my-wiki --template business/hr-people` |
| `project-management` | Project tracking, decisions, stakeholder updates, and post-project reviews | `synthadoc install my-wiki --template business/project-management` |

---

## Template structure

Each template folder contains:

| File | Purpose |
|---|---|
| `description.txt` | One-line description shown by `synthadoc templates list` |
| `guidelines.md` | Domain-specific agent guidelines injected into the agent skill files |
| `routing.md` | Query routing table — becomes `ROUTING.md` in the installed wiki |
| `wiki/purpose.md` | Domain include/exclude rules for the ingest agent |
| `wiki/index.md` | Pre-linked category index with links to all scaffold pages |
| `wiki/seeds.md` | Getting-started guide with recommended web searches and first ingest URLs |
| `wiki/<stub>.md` × 2–4 | Category scaffold pages with frontmatter and a descriptive body |

The agent skill files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) are not stored
in the template directory. They are generated automatically by combining the
template's `guidelines.md` with the standard skill file boilerplate, so
improvements to the boilerplate propagate to all templates without any template
file changes.

---

## Adding a new template

1. Create a folder: `synthadoc/templates/<category>/<domain>/`
2. Add all 7 required files listed in the table above
3. Run the completeness test: `pytest tests/test_template_completeness.py -k "<domain>" -v`
4. Commit. The template appears in `synthadoc templates list` automatically.

Pull requests adding new templates are welcome. The completeness test is the
quality gate — a template that passes it is ready to ship.

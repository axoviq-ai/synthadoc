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

Template installs set `staging_policy = all`, which routes every new ingest to
the `candidates/` review queue regardless of confidence score. Nothing is written
directly to the wiki until you promote it. (The alternative `threshold` policy
stages only pages whose confidence score falls below a configured level —
template installs use `all` so you can review all first-time content before it
becomes part of your knowledge base.)

---

## Adding your own content

A template gives you the structure; your sources give it substance. There are two
ways to bring content in, and you can use both together.

### Option 1 — Ingest web sources (seeds.md)

Open `wiki/seeds.md` in your installed wiki. Each template ships with a curated
list of public URLs and web-search queries to get you started quickly:

```bash
# Ingest a recommended URL
synthadoc ingest "https://www.fdic.gov/regulations/laws/rules/" -w <wiki>

# Ingest via web search
synthadoc ingest "search for: Bank of Canada rate outlook 2025" -w <wiki>
```

### Option 2 — Ingest your own local documents

Place your files in the `raw_sources/` folder inside the installed wiki directory.
This folder is the conventional home for local documents — the backup command
excludes it with `--no-sources`, and relative paths in ingest commands are resolved
from there automatically.

**Subfolders are supported** — organise files however makes sense for your domain:

```
my-finance-wiki/
├── raw_sources/
│   ├── reports/
│   │   ├── q1-2025-earnings.pdf
│   │   └── q2-2025-earnings.pdf
│   ├── policies/
│   │   └── investment-policy-statement.docx
│   └── market-data.xlsx
└── wiki/
    └── ...
```

Ingest a single file, a subfolder, or everything at once:

```bash
# Single file (vault-relative path — no need for the full absolute path)
synthadoc ingest raw_sources/reports/q1-2025-earnings.pdf -w <wiki>

# All files in a subfolder
synthadoc ingest raw_sources/reports/ --batch -w <wiki>

# Everything in raw_sources/ in one go
synthadoc ingest raw_sources/ --batch -w <wiki>
```

**Supported formats:** `.md`, `.txt`, `.pdf`, `.docx`, `.pptx`, `.xlsx`,
`.csv`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`

Because `staging_policy = all` is active on a fresh template install, every
ingest — whether from a URL or a local file — lands in the `candidates/` queue
for review before it is written to your wiki.

### Reviewing and promoting candidates

After ingesting, review what was staged and decide what to keep.

**CLI**

```bash
# See everything waiting for review
synthadoc candidates list -w <wiki>

# Promote a single page by its slug
synthadoc candidates promote investment-policy-statement -w <wiki>

# Promote everything at once (once you're satisfied with the batch)
synthadoc candidates promote --all -w <wiki>

# Discard a page that doesn't belong in this wiki
synthadoc candidates discard q1-2025-earnings -w <wiki>

# Discard everything and start fresh
synthadoc candidates discard --all -w <wiki>
```

**Obsidian plugin**

Open the command palette and run **"Candidates: review candidate pages..."**.
A modal opens with a paginated table showing every staged page alongside its
confidence badge (`high` / `medium` / `low`). Tick the checkboxes for the
pages you want to act on, then click **Promote Selected** or **Discard Selected**.
The modal also shows the current staging policy and links to the Staging settings
if you want to change it.

---

## Scheduled maintenance

Every template install pre-registers two recurring jobs that run automatically
while the server is up:

| Job | Default schedule | What it does |
|---|---|---|
| `lint run` | Weekly, Sunday 2:00 AM | Validates all wiki pages — checks for orphan links, citation presence, and contradictions; promotes clean draft pages to `active` |
| `scaffold` | Weekly, Sunday 3:00 AM | Fills in any missing scaffold stubs for pages that have grown beyond their initial structure |

### Viewing the current schedule

```bash
synthadoc schedule list -w <wiki>
```

The output shows each job's ID, cron expression, next scheduled run, last run
time, and last result — you need the ID to modify or remove a job.

### Changing a schedule

There is no edit-in-place command. The workflow is remove the existing entry,
then add a replacement:

```bash
# 1. Find the job ID
synthadoc schedule list -w <wiki>

# 2. Remove the existing entry
synthadoc schedule remove <id> -w <wiki>

# 3. Add a replacement with your preferred cron expression
#    Example: run lint at 9 AM every weekday instead of Sunday 2 AM
synthadoc schedule add --op "lint run" --cron "0 9 * * 1-5" -w <wiki>

#    Example: run scaffold every Sunday at midnight
synthadoc schedule add --op "scaffold" --cron "0 0 * * 0" -w <wiki>
```

### Disabling a job entirely

Run `schedule list` to get the ID, then `schedule remove <id> -w <wiki>`.
The job will not be recreated automatically — it only returns if you run
`schedule add` again or reinstall the wiki from the template.

### Running a job on demand

```bash
# Trigger lint immediately, outside the schedule
synthadoc schedule run --op "lint run" -w <wiki>

# Trigger scaffold immediately
synthadoc schedule run --op "scaffold" -w <wiki>
```

### Viewing run history

```bash
synthadoc schedule history -w <wiki>        # last 20 runs
synthadoc schedule history -w <wiki> -n 50  # last 50 runs
```

Each row shows the run ID, operation, start time, duration, and status
(`success` / `failed`). Failed runs include the error detail.

### How scaffold updates work

Every template file that scaffold can regenerate contains a
`<!-- synthadoc:scaffold -->` HTML comment that acts as a zone boundary.
The weekly scaffold job never overwrites content you wrote above a marker —
only content below the marker is refreshed with new LLM output.

**`index.md` — single marker**

The marker appears once, below the H1 title. Write your own links, notes, or
introductory text *above* the marker line; scaffold will not touch them on
any future run. Content below the marker (the auto-generated category list)
is regenerated each time.

```markdown
# Index

My pinned links and notes go here — scaffold never touches this.
Any number of paragraphs and links are fine.

<!-- synthadoc:scaffold -->

[[credit-risk]] — ...   ← regenerated each run
[[deposit-products]] — ...
```

**`purpose.md` — one marker per section**

The marker appears once inside each `##` section. Write your own text *above*
the marker in any section; scaffold preserves it and refreshes only the content
below. Sections you add yourself (any `##` heading with *no* marker) are
kept entirely as-is — scaffold treats them as user-owned.

```markdown
## Overview

Our internal compliance and risk management knowledge base.  ← preserved

<!-- synthadoc:scaffold -->

This wiki captures...   ← regenerated each run

## My Custom Section    ← no marker → never touched by scaffold

Notes only I maintain go here.
```

**In summary:** write your persistent content above the marker. Add new
sections with no marker if you want scaffold to leave them entirely alone.

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

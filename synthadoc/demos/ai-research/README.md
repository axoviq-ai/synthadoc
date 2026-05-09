# AI Research Tracker — Demo Wiki

A pre-built Synthadoc wiki covering foundational AI/ML research: architectures, training
techniques, benchmarks, and key researchers.

## What's included

**Pre-built wiki pages (12):** transformer architecture, attention mechanisms, large language
models, training techniques, RLHF, scaling laws, LLM benchmarks, and researcher profiles
for Geoffrey Hinton and Andrej Karpathy.

**Raw sources (5):** a mix of formats — Markdown overview, PDF benchmark report, Excel model
comparison, PowerPoint concepts deck, and a PNG diagram — covering the demo scenarios:
clean merge, contradiction detection, and orphan creation.

## Demo scenarios

| Scenario            | Trigger                                    | Pages affected          |
|---------------------|--------------------------------------------|-------------------------|
| Clean merge         | Ingest `ai-fundamentals-overview.md`       | Multiple pages updated  |
| Contradiction       | Ingest `llm-benchmarks-q1-2026.pdf`        | `llm-benchmarks`        |
| Orphan              | Ingest `neural-network-architecture.png`   | New orphan page created |

## Quick start

```bash
synthadoc install ai-research --target ~/wikis --demo
synthadoc use ai-research
synthadoc serve
synthadoc plugin install ai-research
```

Then open `~/wikis/ai-research` as an Obsidian vault.

See the [Quick-Start Guide](../../../docs/user-quick-start-guide.md) for the full walkthrough.

# AI Research Tracker — Demo Wiki

A pre-built Synthadoc wiki covering foundational AI/ML research: architectures, training
techniques, benchmarks, and key researchers.

## What's included

**Pre-built wiki pages (12):** transformer architecture, attention mechanisms, large language
models, training techniques, RLHF, scaling laws, LLM benchmarks, and researcher profiles
for Geoffrey Hinton and Andrej Karpathy.

**Raw sources (5 generated + 8 public-domain):** generated binary formats (Markdown overview,
PDF benchmark report, Excel model comparison, PowerPoint concepts deck, PNG diagram) plus
eight public-domain CC0 text files covering every wiki topic — for rich, ingestable content
without API calls.

## Demo scenarios

| Scenario            | Trigger                                    | Pages affected          |
|---------------------|--------------------------------------------|-------------------------|
| Clean merge         | Ingest public-domain text files            | All core pages enriched |
| Contradiction       | Ingest `llm-benchmarks-q1-2026.pdf`        | `llm-benchmarks`        |
| Orphan              | Ingest `neural-network-architecture.png`   | New orphan page created |

## Quick start

```bash
synthadoc install ai-research --target ~/wikis --demo
synthadoc use ai-research
synthadoc demo sync ai-research
synthadoc serve
synthadoc plugin install ai-research
```

Then open `~/wikis/ai-research` as an Obsidian vault.

---

## Set your active wiki

After installing, run this once so you don't need `-w ai-research` on every command:

```bash
synthadoc use ai-research
```

To confirm which wiki is active: `synthadoc use`

---

## Source documents

### Public-domain sources (sync first)

Run `synthadoc demo sync ai-research` to copy these into your installed wiki. They cover
every pre-built page topic and are designed to demonstrate clean-merge enrichment.

| File | Covers |
|------|--------|
| `transformer-architecture.txt` | Transformer model, self-attention, variants |
| `attention-mechanisms.txt` | Scaled dot-product, multi-head, Flash Attention |
| `large-language-models.txt` | GPT series, BERT, LLaMA, instruction tuning |
| `reinforcement-learning-from-human-feedback.txt` | RLHF pipeline, InstructGPT, DPO |
| `scaling-laws.txt` | Kaplan et al., Chinchilla, compute-optimal training |
| `training-techniques.txt` | Pre-training, mixed precision, LoRA, tokenisation |
| `geoffrey-hinton-biography.txt` | Career, backpropagation, AlexNet, Turing Award |
| `andrej-karpathy-biography.txt` | Stanford PhD, Tesla AI, nanoGPT, Eureka Labs |

### Generated binary sources

These are included in `raw_sources/` from the initial install and cover the demo scenarios:

| File | Format | Scenario |
|------|--------|----------|
| `ai-fundamentals-overview.md` | Markdown | **Clean merge** — enriches multiple pages |
| `model-capabilities-comparison.xlsx` | XLSX | **Clean merge** — structured model data |
| `deep-learning-concepts.pptx` | PowerPoint | **Clean merge** — concepts deck |
| `llm-benchmarks-q1-2026.pdf` | PDF | **Contradiction** — contradicts `llm-benchmarks` |
| `neural-network-architecture.png` | PNG | **Orphan** — new topic, no existing page links to it |

To regenerate the binary files: `python _generate_raw_sources.py`

---

## Step 1 — Start the server

```
synthadoc serve
```

Expected output:
```
HTTP API running on http://127.0.0.1:7070
```

Use a second terminal for all commands below.

---

## Step 2 — Scenario A: Clean merge (public-domain sources)

Ingest the public-domain text files. They enrich each pre-built page with additional depth
without contradicting any existing content.

```
synthadoc ingest --batch sources.txt
```

Or ingest individual topics:

```
synthadoc ingest raw_sources/public-domain/transformer-architecture.txt
synthadoc ingest raw_sources/public-domain/scaling-laws.txt
```

**Expected result:** jobs complete with status `updated`. Open wiki pages in Obsidian — they
gain new sections from the ingested text. All pages remain `active`.

---

## Step 3 — Scenario B: Contradiction

Ingest the benchmark PDF. It argues that the Gemini Ultra 90.0% MMLU figure is not
comparable to GPT-4's 86.4% because different evaluation protocols were used — directly
contradicting the existing `llm-benchmarks` page.

```
synthadoc ingest raw_sources/llm-benchmarks-q1-2026.pdf
```

**Expected result:** `llm-benchmarks.md` transitions to `status: contradicted`. In Obsidian,
open `wiki/dashboard.md` — it appears in the **Contradicted pages** table.

Resolve via auto-resolve:
```
synthadoc lint run --auto-resolve
```

Or resolve manually: open `wiki/llm-benchmarks.md`, edit the conflicting benchmark claim,
and change `status: contradicted` to `status: active`.

---

## Step 4 — Scenario C: Orphan

Ingest the neural network architecture diagram. It covers a topic not mentioned in any
existing wiki page.

```
synthadoc ingest raw_sources/neural-network-architecture.png
```

**Expected result:** a new `neural-network-architecture` (or similar) page is created, but
nothing links to it. Open `wiki/dashboard.md` — it appears in the **Orphan pages** table.

Your options: link it from a related page, leave it as a standalone, or delete and re-ingest
with a better source using `--force`.

---

## Step 5 — Check status

```
synthadoc status
synthadoc jobs list
synthadoc lint report
synthadoc lifecycle log
```

---

## Wiki pages (pre-built)

| Page | Description |
|------|-------------|
| `transformer-architecture` | Vaswani et al. 2017, encoder-decoder, self-attention |
| `attention-mechanisms` | Scaled dot-product, multi-head, Flash Attention |
| `large-language-models` | GPT series, BERT, LLaMA, emergent capabilities |
| `training-techniques` | Pre-training, SFT, LoRA, tokenisation, data filtering |
| `reinforcement-learning-from-human-feedback` | RLHF pipeline, InstructGPT, DPO |
| `scaling-laws` | Kaplan et al., Chinchilla, compute-optimal training |
| `llm-benchmarks` | MMLU, HumanEval, BIG-Bench, evaluation pitfalls |
| `geoffrey-hinton` | Researcher profile — backpropagation, AlexNet, Turing Award |
| `andrej-karpathy` | Researcher profile — Tesla AI, nanoGPT, Eureka Labs |

---

## Uninstall

```
synthadoc uninstall ai-research
```

Requires two confirmations — a y/N prompt and typing the wiki name.

See the [Quick-Start Guide](../../../docs/user-quick-start-guide.md) for the full walkthrough.

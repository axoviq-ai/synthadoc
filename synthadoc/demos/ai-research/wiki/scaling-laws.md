---
aliases: []
categories:
- Large Language Models
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: public-domain/scaling-laws.txt
  hash: placeholder
  ingested: '2026-04-08'
  size: 0
status: active
tags:
- scaling
- training
- compute
- llm
title: Scaling Laws
type: concept
updated: '2026-07-12'
---

# Scaling Laws

Scaling laws describe the empirical relationship between model performance and three
variables: the number of model parameters (N), the size of the training dataset (D), and
the amount of compute (C). The key finding is that loss decreases as a smooth power law
when any of these variables increases — a predictable relationship that enables
researchers to forecast model capability before training.

## Kaplan et al. (2020)

The first systematic study of neural language model scaling (OpenAI, 2020) found that:

- Loss scales as a power law in N, D, and C independently
- Model size has the largest impact per unit of compute
- Data and compute should scale together, but models were being under-trained relative
  to their size

This led to training very large models on relatively small datasets — GPT-3 (175B
parameters) was trained on roughly 300B tokens.

## Chinchilla Scaling Laws (Hoffmann et al., 2022)

The Chinchilla paper (DeepMind, 2022) revised the Kaplan findings with a more thorough
compute-optimal analysis. The key result: **for a given compute budget, model size and
training tokens should be scaled equally**. Specifically, the optimal token count is
approximately 20× the parameter count.

This implied that GPT-3 and PaLM were significantly under-trained. The Chinchilla model
(70B parameters, 1.4T tokens) outperformed the 280B Gopher model trained on the same
compute budget, validating the analysis.

## Implications for Modern Training

- LLaMA models were explicitly designed to be Chinchilla-optimal or over-trained, making
  them efficient at *inference* time (smaller model, better performance)
- Long-run training (e.g. Llama 3 on 15T tokens for a 70B model) intentionally exceeds
  Chinchilla-optimal to maximise inference efficiency at deployment scale
- Scaling laws have limits: performance on specific reasoning tasks can improve
  discontinuously (emergent abilities), not smoothly

## See Also

- [[large-language-models]] — models trained under these scaling regimes
- [[training-techniques]] — the training process scaling laws apply to

## Chinchilla (2022) Revision

A subsequent study by DeepMind (Hoffmann et al., 2022), known as **Chinchilla**, revisited the Kaplan et al. findings and revised the recommended scaling strategy:

- For a given compute budget, model parameters and training tokens should be scaled **roughly equally** — approximately **20 tokens per parameter**.
- Many existing models, including GPT-3 (175B parameters trained on ~300B tokens), were significantly **undertrained** by this standard.
- The Chinchilla paper demonstrated this empirically: a 70B-parameter model (Chinchilla) outperformed the much larger 280B-parameter Gopher when both were trained with optimal token budgets.

## Implications for Model Sizing

The Chinchilla finding shifted industry practice toward training smaller models on more data rather than maximizing parameters at the expense of tokens. This influenced subsequent [[large-language-models]] such as LLaMA, which adopted training budgets more closely aligned with the Chinchilla-optimal regime. The debate between Kaplan-style parameter-favored scaling and Chinchilla-style compute-balanced scaling remains a central consideration in [[training-techniques]] for frontier models.

## Chinchilla (Hoffmann et al., 2022)

A follow-up study by DeepMind (Hoffmann, Borgeaud, Mensch, et al., 2022) challenged key assumptions in the Kaplan scaling analysis and produced a revised set of scaling laws. Using a rigorous fitting procedure across more than 400 trained models, the Chinchilla paper found that compute-optimal training should scale **parameters and dataset size roughly equally** — not prioritise parameters as Kaplan et al. had suggested.

The headline result: an optimal model should be trained on approximately **20 tokens per parameter**. This implied that many large models at the time (including GPT-3) were significantly *undertrained* — GPT-3 (175B parameters, ~300B tokens) had far more parameters than were compute-optimal for its training budget.

Chinchilla itself trained a 70B-parameter model on 1.4T tokens, matching the compute-optimal frontier while being roughly 2.5× smaller than GPT-3 but trained on ~5× more data.

The Chinchilla finding became a central reference point for subsequent model training decisions, shifting the field's emphasis from training ever-larger models on fixed datasets toward balancing parameter count with data volume.

## Chinchilla (Hoffmann et al., 2022)

DeepMind's *Training Compute-Optimal Large Language Models* paper (Hoffmann, Borgeaud, Mensch, et al., 2022) revised the Kaplan et al. scaling prescription. By running a rigorous sweep over model sizes from 70M to 16B parameters trained on 5B to 500B tokens, the authors found that **N and D should scale roughly equally** for compute-optimal training — approximately 20 tokens per parameter.

Key implications:
- Under the Chinchilla prescription, gpt-3 (175B parameters trained on ~300B tokens) was significantly **under-trained**: a compute-optimal model at that compute budget would have been roughly 4× smaller and trained on more tokens.
- The result favored smaller models trained on more data, directly contradicting the Kaplan et al. bias toward rapidly increasing parameter count.
- Chinchilla (70B parameters, 1.4T tokens) was presented as the compute-optimal baseline, outperforming gpt-3 (175B) and Gopher (280B) on many downstream evaluations.

The Chinchilla finding reshaped subsequent open-source efforts (e.g., LLaMA, Mistral) toward smaller-parameter, more-data regimes, and remains a central reference point in [[large-language-models]] training-budget discussions.

## Chinchilla (2022)

Hoffmann, Borgeaud, Mensch, and colleagues at [[deepmind]] ("Training Compute-Optimal Large Language Models") revisited the scaling laws with more careful experimental design and produced the Chinchilla model. Their key finding:

- For a fixed compute budget, the optimal model has roughly equal scaling in parameters and data: N_opt ∝ C^0.50, D_opt ∝ C^0.50
- Equivalently, the optimal training run uses approximately **20 tokens per parameter** ^[scaling-laws.txt:23-29]

This was a significant revision. Under Kaplan, [[gpt-3]] (175B params, 300B tokens ≈ 1.7 tokens/param) was substantially under-trained. Under Chinchilla, the same compute would be better spent on a ~70B parameter model trained on ~1.4T tokens. DeepMind validated this by training Chinchilla (70B, 1.4T tokens) with the same compute as Gopher (280B) — Chinchilla matched or exceeded Gopher on nearly every benchmark. ^[scaling-laws.txt:31-33]

## The Overtraining Strategy

Chinchilla's result shifted design philosophy. LLaMA (2023) explicitly targeted over-trained regimes (more tokens than Chinchilla-optimal), reasoning that inference cost per query favors smaller models at deployment scale. Concrete examples:

- LLaMA 2: 70B params, 2T tokens
- LLaMA 3: 8B params, 15T tokens

This "overtrain small models" strategy trades training cost for cheaper inference. ^[scaling-laws.txt:37-37]

## Limitations and Open Questions

- Scaling laws are **empirical** — they describe what has been observed but do not explain *why* the power law relationship holds. Theoretical accounts remain incomplete. ^[scaling-laws.txt:41-41]
- Exponents are **not universal**: different architectures, tokenisers, datasets, and tasks yield different scaling behaviour. Kaplan and Chinchilla were measured on English text modeling; applicability to code, multilingual, and multimodal tasks is similar but not identical. ^[scaling-laws.txt:43-43]
- **Emergent capabilities** complicate the picture — some capabilities appear discontinuously at certain scales, which is not easily reconciled with smooth power laws in loss. Whether emergence is a real discontinuity or an artifact of coarse-grained metrics is debated. ^[scaling-laws.txt:45-45]

## Scaling Beyond Language

Power-law scaling behavior has been observed across domains:

- **Vision**: image classification and generation show similar power laws
- **Multimodal**: scaling vision encoders and language model components shows additive benefits
- **Reinforcement learning**: game-playing agents show power laws in environment interactions and model size, though with steeper data requirements than language modeling
- **Code models**: Codex and Code LLaMA show scaling behavior consistent with language model laws, with benefits from code-specific training data ^[scaling-laws.txt:51-57]

The generality of scaling laws across domains has led some researchers to treat them as a near-universal property of learning from data with gradient descent on over-parameterised models, though a complete theoretical account remains open. ^[scaling-laws.txt:59-59]
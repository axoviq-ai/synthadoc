---
aliases: []
categories:
- Large Language Models
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: ai-fundamentals-overview.md
  hash: a3f8c2d1e4b9071652340abc98def765a3f8c2d1e4b9071652340abc98def765
  ingested: '2026-05-09'
  size: 3847
status: active
tags:
- scaling
- training
- compute
- llm
title: Scaling Laws
type: concept
updated: '2026-06-27'
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

A subsequent study by DeepMind (Hoffmann et al., 2022), known as **Chinchilla**, revisited the Kaplan et al. findings and revised the recommended scaling strategy: ^[scaling-laws.txt:23]

- For a given compute budget, model parameters and training tokens should be scaled **roughly equally** — approximately **20 tokens per parameter**. ^[scaling-laws.txt:25-29]
- Many existing models, including GPT-3 (175B parameters trained on ~300B tokens), were significantly **undertrained** by this standard. ^[scaling-laws.txt:31]
- The Chinchilla paper demonstrated this empirically: a 70B-parameter model (Chinchilla) outperformed the much larger 280B-parameter Gopher when both were trained with optimal token budgets. ^[scaling-laws.txt:33]

## Implications for Model Sizing

The Chinchilla finding shifted industry practice toward training smaller models on more data rather than maximizing parameters at the expense of tokens. This influenced subsequent [[large-language-models]] such as LLaMA, which adopted training budgets more closely aligned with the Chinchilla-optimal regime. ^[scaling-laws.txt:37] The debate between Kaplan-style parameter-favored scaling and Chinchilla-style compute-balanced scaling remains a central consideration in [[training-techniques]] for frontier models.

## Chinchilla (Hoffmann et al., 2022)

A follow-up study by DeepMind (Hoffmann, Borgeaud, Mensch, et al., 2022) challenged key assumptions in the Kaplan scaling analysis and produced a revised set of scaling laws. Using a rigorous fitting procedure across more than 400 trained models, the Chinchilla paper found that compute-optimal training should scale **parameters and dataset size roughly equally** — not prioritise parameters as Kaplan et al. had suggested. ^[scaling-laws.txt:23-27]

The headline result: an optimal model should be trained on approximately **20 tokens per parameter**. This implied that many large models at the time (including GPT-3) were significantly *undertrained* — GPT-3 (175B parameters, ~300B tokens) had far more parameters than were compute-optimal for its training budget. ^[scaling-laws.txt:29-31]

Chinchilla itself trained a 70B-parameter model on 1.4T tokens, matching the compute-optimal frontier while being roughly 2.5× smaller than GPT-3 but trained on ~5× more data. ^[scaling-laws.txt:33]

The Chinchilla finding became a central reference point for subsequent model training decisions, shifting the field's emphasis from training ever-larger models on fixed datasets toward balancing parameter count with data volume. ^[scaling-laws.txt:37]

## Chinchilla (Hoffmann et al., 2022)

DeepMind's *Training Compute-Optimal Large Language Models* paper (Hoffmann, Borgeaud, Mensch, et al., 2022) revised the Kaplan et al. scaling prescription. ^[scaling-laws.txt:23] By running a rigorous sweep over model sizes from 70M to 16B parameters trained on 5B to 500B tokens, the authors found that **N and D should scale roughly equally** for compute-optimal training — approximately 20 tokens per parameter. ^[scaling-laws.txt:23-29]

Key implications:
- Under the Chinchilla prescription, gpt-3 (175B parameters trained on ~300B tokens) was significantly **under-trained**: a compute-optimal model at that compute budget would have been roughly 4× smaller and trained on more tokens. ^[scaling-laws.txt:31]
- The result favored smaller models trained on more data, directly contradicting the Kaplan et al. bias toward rapidly increasing parameter count. ^[scaling-laws.txt:31]
- Chinchilla (70B parameters, 1.4T tokens) was presented as the compute-optimal baseline, outperforming gpt-3 (175B) and Gopher (280B) on many downstream evaluations. ^[scaling-laws.txt:33]

The Chinchilla finding reshaped subsequent open-source efforts (e.g., LLaMA, Mistral) toward smaller-parameter, more-data regimes, and remains a central reference point in [[large-language-models]] training-budget discussions. ^[scaling-laws.txt:37]
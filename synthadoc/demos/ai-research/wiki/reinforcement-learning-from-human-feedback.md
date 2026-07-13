---
aliases:
- RLHF
categories:
- Large Language Models
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: public-domain/reinforcement-learning-from-human-feedback.txt
  hash: placeholder
  ingested: '2026-04-08'
  size: 0
status: active
tags:
- rlhf
- alignment
- training
- llm
title: Reinforcement Learning from Human Feedback
type: concept
updated: '2026-07-12'
---

# Reinforcement Learning from Human Feedback

Reinforcement learning from human feedback (RLHF) is a training technique that uses human
preference data to align a language model's outputs with human values and intent. It became
the standard alignment method after InstructGPT (Ouyang et al., 2022) demonstrated that a
fine-tuned 1.3B model could outperform GPT-3 (175B) on human-preference evaluations.

## The Three-Stage Pipeline

**Stage 1 — Supervised Fine-Tuning (SFT):**  
A pre-trained base model is fine-tuned on human-written demonstrations of desired behaviour.
This produces a model that roughly follows instructions.

**Stage 2 — Reward Model Training:**  
Human labellers rank multiple model responses to the same prompt from best to worst. A
separate reward model (RM) is trained to predict these rankings, learning a scalar score
representing human preference.

**Stage 3 — RL Optimisation (PPO):**  
The SFT model is further fine-tuned using Proximal Policy Optimisation (PPO), treating
the reward model's score as the reward signal. A KL-divergence penalty prevents the model
from diverging too far from the SFT baseline (reward hacking).

## Applications

- **InstructGPT / ChatGPT** — the first large-scale deployment; established RLHF as a
  practical alignment technique
- **Claude (Anthropic)** — uses Constitutional AI (CAI) as an extension of RLHF, replacing
  some human preference labels with AI-generated feedback
- **Llama 2 Chat** — Meta's open-weight RLHF-aligned model series

## Limitations

- **Reward hacking** — the model learns to maximise the reward model's score rather than
  genuine quality; requires careful KL penalties and iterative reward model updates
- **Labeller variance** — human preferences are inconsistent; reward model quality is
  bounded by labeller agreement
- **Cost** — collecting high-quality preference data at scale is expensive

DPO (Direct Preference Optimisation) has emerged as a simpler alternative — see
[[training-techniques]] for a comparison.

## See Also

- [[training-techniques]] — RLHF in context of the full training pipeline
- [[large-language-models]] — models aligned with RLHF

## Core Problem RLHF Addresses

Pre-trained language models like [[large-language-models|GPT-3]] learn statistical patterns for next-token prediction, but this objective does not inherently make them helpful, harmless, or aligned with user intent. RLHF exists to bridge this gap between *text prediction* and *genuine helpfulness*, serving as the alignment layer between a base model and its deployment in products like ChatGPT.

## Connection to instruction-tuning

Supervised fine-tuning (the first stage of RLHF) is closely related to instruction tuning — both train the model on human demonstrations of desired behaviour. Instruction tuning is sometimes used as a broader umbrella term that includes the SFT stage of the RLHF pipeline.

## Technical Foundations

The three stages rely on several key components:

- **Supervised Fine-Tuning (SFT):** Human annotators write ideal responses that the base model is fine-tuned to imitate, establishing a baseline of helpful behaviour.
- **Reward Model:** A separate model is trained on human preference rankings (pairwise comparisons of model outputs) to predict which response a human would prefer.
- **Policy Optimisation with PPO:** The SFT model (the *policy*) is fine-tuned using proximal-policy-optimization (PPO) to maximise the reward model's score. A **KL-divergence** penalty anchors the policy close to the SFT model, preventing the model from drifting too far and producing incoherent text in pursuit of high reward.

The KL penalty is critical: without it, the policy can exploit the reward model — a failure mode known as *reward hacking* — producing outputs that score well but are nonsensical or harmful.

## Demonstrated Impact

The 2022 InstructGPT paper showed that a 1.3B-parameter RLHF-tuned model was preferred by human evaluators over the 175B-parameter gpt-3 base model, despite being roughly 100× smaller. This result, more than raw parameter count, motivated the industry shift toward [[large-language-models|alignment-first]] training pipelines and directly enabled ChatGPT's release in late 2022.

## Technical Details

The RLHF policy optimisation stage uses **proximal-policy-optimization** (PPO) as the optimisation algorithm. A KL-divergence penalty is applied between the policy being trained and the original supervised fine-tuned model to prevent the model from drifting too far from its pre-RLHF distribution, which helps maintain generation quality and avoid reward hacking.

Beyond improving instruction following, RLHF has been shown to reduce **toxicity** in model outputs and improve **truthfulness**, making it a key technique not only for alignment but also for safety properties of deployed language models like chatgpt.

## Constitutional AI

Anthropic introduced constitutional AI (CAI) as an alternative to human labelling for the comparison step. Instead of human comparisons, the model is asked to evaluate its own outputs against a written list of principles (the "constitution"). Self-critique and revision are used to generate improved outputs, which are then used for preference training. CAI reduces the reliance on human annotators for the safety-relevant comparisons and is discussed further in training-techniques. ^[reinforcement-learning-from-human-feedback.txt:45-45]

## Direct Preference Optimisation

Direct preference optimisation (DPO, Rafailov et al., 2023) reformulates the RLHF objective as a supervised learning problem over preference pairs, eliminating the need to train an explicit reward model and run PPO. DPO derived a closed-form expression for the optimal policy given a preference dataset, showing that the same objective as PPO can be optimised directly on the preference data. ^[reinforcement-learning-from-human-feedback.txt:49-49]

DPO is substantially simpler and cheaper to implement than the full RLHF pipeline and achieves comparable or better alignment results on standard benchmarks. It has been widely adopted in open-source large-language-models fine-tuning. ^[reinforcement-learning-from-human-feedback.txt:51-51]

## Limitations

RLHF is subject to **reward hacking**: the policy can learn to produce outputs that score highly on the reward-model without actually being better — exploiting gaps between the reward model and true human preference. This is particularly problematic because the reward model is trained on a finite set of comparisons and generalises imperfectly. ^[reinforcement-learning-from-human-feedback.txt:37-37]

**Annotator disagreement** introduces noise: human judgements of output quality are not consistent, especially on complex topics or when cultural values differ. The reward model captures the average of annotator preferences, which may not represent any individual's view. ^[reinforcement-learning-from-human-feedback.txt:39-39]

RLHF also introduces **sycophancy**: models trained with RLHF learn that annotators prefer confident, fluent, agreeable responses, even when these are less accurate. Subsequent work has explored techniques to reduce this effect. ^[reinforcement-learning-from-human-feedback.txt:41-41]
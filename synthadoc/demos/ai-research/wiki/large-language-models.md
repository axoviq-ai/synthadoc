---
aliases: []
categories:
- Large Language Models
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: public-domain/large-language-models.txt
  hash: placeholder
  ingested: '2026-04-08'
  size: 0
status: active
tags:
- llm
- transformers
- gpt
- language-models
title: Large Language Models
type: technology
updated: '2026-07-12'
---

# Large Language Models

Large language models (LLMs) are [[transformer-architecture]]-based models trained on
massive text corpora to predict the probability of the next token. At sufficient scale,
this simple objective produces models capable of reasoning, code generation, translation,
and open-ended instruction following.

## The Scale Threshold

Early transformers (BERT, GPT-2) demonstrated strong performance on specific tasks but
required task-specific fine-tuning. GPT-3 (Brown et al., 2020), with 175 billion
parameters, showed that a sufficiently large model could perform novel tasks from a few
examples in the prompt — a property called *few-shot in-context learning*. This established
a qualitative shift: scale itself became a training strategy. [[scaling-laws]] formalised
why this works.

## Landmark Models

| Model       | Organisation  | Parameters | Key contribution                          |
|-------------|---------------|------------|-------------------------------------------|
| GPT-3       | OpenAI        | 175B       | In-context learning at scale              |
| BERT        | Google        | 340M       | Masked LM, encoder-only pretraining       |
| PaLM        | Google        | 540B       | Chain-of-thought reasoning at scale       |
| LLaMA 2     | Meta          | 7B–70B     | Open-weights, commercially permissive     |
| Claude 3    | Anthropic     | Undisclosed| Constitutional AI alignment               |
| GPT-4       | OpenAI        | Undisclosed| Multimodal, strong reasoning              |
| Gemini      | Google        | Undisclosed| Multimodal from the ground up             |

## Instruction Tuning and Alignment

Base LLMs predict next tokens; they do not follow instructions reliably. Two techniques
bridge the gap:

- **Instruction fine-tuning** — supervised fine-tuning on (instruction, response) pairs
- **RLHF** — [[reinforcement-learning-from-human-feedback]] refines behaviour using human
  preference signals; used in InstructGPT, ChatGPT, and Claude

## Context Windows

Early LLMs were limited to 2K–4K token contexts. Modern models (GPT-4 Turbo, Claude 3,
Gemini 1.5 Pro) support 128K–1M tokens, enabling full-document reasoning and long-session
memory.

## See Also

- [[transformer-architecture]] — the architecture all major LLMs share
- [[scaling-laws]] — why bigger models trained on more data perform better
- [[training-techniques]] — how LLMs are pre-trained and aligned
- [[llm-benchmarks]] — how LLM capabilities are measured and compared

## GPT-4 and the Multimodal Frontier

GPT-4, released by openai in 2023, extended the GPT lineage with multimodal capabilities — accepting both text and image inputs and producing text outputs. This marked a significant expansion beyond text-only language modeling, demonstrating that [[transformer-architecture]]-based models could process heterogeneous input modalities within a single unified architecture.

## Open Model Releases and Ecosystem Diversification

Alongside OpenAI's proprietary models, the landscape expanded with open-weight releases such as LLaMA 2 (Meta, 2023), which provided the research community with access to capable base models for fine-tuning and study. These open releases complemented the closed frontier models and accelerated research into alignment, evaluation, and deployment.

## Frontier Model Opacity

A defining characteristic of the post-2023 era is that frontier model specifications — architecture details, parameter counts, training data composition, and training compute — remain undisclosed by their developers. This opacity, driven by competitive and safety considerations, contrasts sharply with the open publication norms of earlier [[transformer-architecture]] research and complicates independent analysis of frontier capabilities.

## The GPT Series: Evolution from GPT-1 to GPT-4

The GPT (Generative Pre-trained Transformer) line, developed by openai, traces a clear arc of scaling and capability gains:

- **GPT-1 (2018)** — Introduced the paradigm of unsupervised pre-training followed by supervised fine-tuning, demonstrating that a generative transformer could generalise across multiple NLP tasks.
- **GPT-2 (2019)** — Scaled to 1.5 billion parameters; its release was initially withheld over misuse concerns, highlighting early tensions between capability and safety.
- **GPT-3 (2020)** — At 175 billion parameters, it exhibited emergent in-context-learning, performing new tasks from few-shot prompts without weight updates. This is widely seen as the threshold where [[large-language-models]] became broadly useful.
- **GPT-4 (2023)** — Introduced robust multimodal capabilities (text and image input), alongside significant gains in reasoning, factual reliability, and long-context handling.

## Encoder vs Decoder Paradigms

Two foundational architectures emerged from the [[transformer-architecture]]:

- **Encoder-only models (e.g., bert)** — Use bidirectional attention and masked language modelling, producing strong representations for classification, extraction, and understanding tasks.
- **Decoder-only models (e.g., the GPT family)** — Use causal (left-to-right) attention trained with next-token prediction, making them natural generative models and the basis for modern [[large-language-models]].

This split shaped the entire modern NLP landscape, with decoder-only models ultimately prevailing for general-purpose assistants.

## Multimodal and the Modern Landscape

Beyond GPT-4, multimodal capabilities have become a frontier: Google's Gemini Ultra, Anthropic's Claude 3, and Meta's LLaMA 2 represent competing pushes in scale, multimodality, and open-weight availability. Alignment via [[reinforcement-learning-from-human-feedback]] remains a critical component of turning base models into deployable assistants.

## Comparative Overview of Major LLMs

The following table summarizes key [LLM benchmarks]([[llm-benchmarks]]) and specifications for several landmark models. Figures reflect initial release values.

| Model | Developer | Released | Parameters | MMLU | HumanEval | Context Window | Open Weights |
|-------|-----------|----------|------------|------|-----------|----------------|--------------|
| BERT-Large | Google | 2018 | 340M | — | — | 512 | Yes |
| GPT-3 | OpenAI | 2020 | 175B | — | — | 2,048 | No |
| LLaMA 2 70B | Meta | 2023 | 70B | 69.9% | 32.3% | 4,096 | Yes |
| Mistral 7B | Mistral | 2023 | 7B | 62.5% | 40.2% | 8,192 | Yes |
| GPT-4 | OpenAI | 2023 | undisclosed | 86.4% | 67.0% | 8,192 | No |
| Claude 3 Opus | Anthropic | 2024 | undisclosed | 86.8% | 84.9% | 200,000 | No |
| Gemini Ultra | Google | 2024 | undisclosed | 90.0% | — | 32,768 | No |
| Llama 3 70B | Meta | 2024 | 70B | 79.3% | 82.0% | 8,192 | Yes |

## Benchmarking Caveats

Headline benchmark numbers require careful interpretation. **Gemini Ultra's widely reported 90% MMLU score uses chain-of-thought at 32 samples (CoT@32)** rather than the standard 5-shot evaluation used for most other models. Under 5-shot conditions, Gemini Ultra falls below GPT-4. This illustrates a recurring problem in cross-model comparison: results reported under different prompting or sampling regimes are not directly comparable, even when the benchmark is the same. See [[llm-benchmarks]] for further discussion of evaluation methodology.

## Historical Overview and Major Model Lineages

Large language models emerged as the dominant paradigm in natural language processing following the introduction of the [[transformer-architecture]] in 2017. The field rapidly shifted away from earlier recurrent network approaches (RNNs, LSTMs) and task-specific supervised models toward a unified paradigm: large-scale self-supervised pre-training on raw text, followed by various forms of fine-tuning and alignment.

### The Pre-Transformer Era

Before transformers, NLP relied on recurrent architectures and pipelines of task-specific supervised models. Performance on benchmarks was incremental, and transfer learning across tasks was limited. The [[transformer-architecture]] paper, *Attention Is All You Need* (Vaswani et al., 2017), demonstrated that self-attention could serve as the foundation for sequence modelling, enabling far greater parallelisation during training.

### The Rise of Self-Supervised Pre-Training

Two seminal 2018 models defined the modern LLM landscape:

- **bert** (Google, Devlin et al., 2018) — an encoder-only model trained with masked language modelling, excelling at understanding tasks such as classification and question answering.
- **GPT-1** (OpenAI, Radford et al., 2018) — a decoder-only model trained on next-token prediction, establishing the generative pre-training paradigm that would dominate subsequent years.

These models demonstrated that pre-training on large unlabelled corpora produced representations broadly useful across downstream tasks, reducing the need for task-specific architectures.

### The Scaling Era (GPT-2 through GPT-4)

The GPT series from OpenAI progressively demonstrated that scale — more parameters, more data, more compute — produced qualitatively new capabilities:

- **GPT-2** (2019, 1.5B parameters) showed that a sufficiently large generative model could perform coherent text completion without task-specific training.
- **GPT-3** (Brown et al., 2020, 175B parameters) demonstrated in-context-learning, performing novel tasks from a few examples provided in the prompt alone — a capability absent in smaller models.
- **GPT-4** (2023) introduced multimodal capabilities, accepting both text and image inputs, and exhibited substantially improved reasoning and instruction following.

### Instruction Tuning and Alignment

Raw pre-trained models do not naturally follow user instructions. The development of [[reinforcement-learning-from-human-feedback]] (RLHF), pioneered by instructgpt (Ouyang et al., 2022), addressed this gap. Models such as **claude-3** (Anthropic, 2024) and Meta's **LLaMA 2** further refined alignment techniques, incorporating constitutional AI, red-teaming, and extended RLHF pipelines. Alignment research became a central subfield alongside raw capability scaling.

### Key Themes

Three developments defined the LLM era as qualitatively distinct from earlier NLP:

1. **Scale** — compute, data, and parameter counts grew by orders of magnitude, producing emergent capabilities at threshold sizes.
2. **In-context learning** — models learned from examples embedded in the prompt, blurring the line between training and inference.
3. **Instruction tuning via RLHF** — alignment with human intent transformed raw generative models into broadly useful assistants.

## Training Paradigms for Modern LLMs

The evolution from GPT-2 to GPT-3 and beyond involved several key training innovations beyond simple next-token prediction:

**Pre-training** — Models are first trained on massive text corpora using self-supervised learning (predicting the next token). This is the foundational paradigm described by 2017 transformer work and scaled up dramatically by the GPT family.

**Scaling Laws (Hoffmann et al., 2022)** — Research by Hoffmann et al. formalized the relationship between model size, dataset size, and compute, demonstrating that balanced scaling across all three dimensions (rather than just increasing parameters) yields optimal performance. This 'Chinchilla scaling' influenced subsequent model training decisions.

**Instruction Tuning** — After pre-training, models are fine-tuned on datasets of (instruction, response) pairs, teaching them to follow user commands rather than merely completing text. This shifted LLMs from base completion engines to interactive assistants.

**RLHF (Reinforcement Learning from Human Feedback)** — A final alignment stage where human preference judgments are used to train a reward model, which then fine-tunes the LLM via reinforcement learning (typically PPO). Pioneered in the InstructGPT and ChatGPT era. This connects to broader work in [[andrej-karpathy|Karpathy]]'s educational content and [[geoffrey-hinton|Hinton]]'s foundational deep learning research.

## Key Researchers Beyond Hinton

While [[geoffrey-hinton]] is foundational for deep learning, other key figures shaped modern LLMs:

- **Yann LeCun** — Pioneer of convolutional neural networks (CNNs) and advocate for self-supervised learning approaches.
- **Yoshua Bengio** — Co-author with Hinton on early deep learning breakthroughs; contributed to attention mechanisms and language model research.

Together with [[geoffrey-hinton]], LeCun and Bengio are often referred to as the 'godfathers of deep learning,' having received the 2018 Turing Award for their collective contributions.

## GPT Series Details

The [[transformer-architecture]] decoder-only approach established by the GPT line progressed rapidly:

- **GPT-1** (2018, 117M parameters) showed that pre-training on a large corpus with task-specific fine-tuning could match or exceed specialised models on multiple NLP benchmarks. ^[large-language-models.txt:15-15]
- **GPT-2** (2019, 1.5B parameters) demonstrated that scaling alone — without task-specific fine-tuning — produced coherent long-form text generation. OpenAI initially withheld the full model over misuse concerns. ^[large-language-models.txt:17-17]
- **GPT-3** (2020, 175B parameters, trained on ~300B tokens) demonstrated in-context learning, shifting the field toward prompting as the primary interface. ^[large-language-models.txt:19-19]
- **InstructGPT** (2022) applied [[reinforcement-learning-from-human-feedback]] to GPT-3. ^[large-language-models.txt:21-21]
- **GPT-4** (2023) extended the architecture to multimodal inputs, achieving near-professional performance on several human examinations. ^[large-language-models.txt:23-23]

Frontier models (GPT-4, Claude 3, Gemini Ultra) have not publicly disclosed parameter counts or training data sizes. ^[large-language-models.txt:9-9]

## Context Length Evolution

The context window — the maximum tokens a model can attend to — has expanded substantially: GPT-2 (1,024 tokens) → GPT-3 (4,096) → 8K → 32K → 128K → over 1M tokens in some systems using specialised architectures. Longer contexts enable reasoning over entire documents, code repositories, or extended multi-turn conversations. ^[large-language-models.txt:51-51]

## Emergent Capabilities

Above certain scale thresholds, [[large-language-models]] exhibit capabilities absent in smaller models and not explicitly trained for — multi-step arithmetic, chain-of-thought reasoning, coding from natural language, and analogy completion. ^[large-language-models.txt:45-45] The mechanism is debated: some researchers attribute emergence to phase transitions in internal representations, while others argue it reflects continuous improvements that only become measurable at scale given benchmark difficulty. ^[large-language-models.txt:47-47]
---
aliases: []
categories:
- Large Language Models
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: public-domain/training-techniques.txt
  hash: placeholder
  ingested: '2026-04-08'
  size: 0
status: active
tags:
- training
- fine-tuning
- alignment
- llm
title: Training Techniques
type: concept
updated: '2026-07-12'
---

# Training Techniques

Modern [[large-language-models]] are trained in multiple stages, each addressing a
different objective — from learning general language structure to following specific
instructions safely and helpfully.

## Pre-training

Pre-training is unsupervised training on a large corpus using a self-supervised objective.
For decoder-only models (GPT family), this is *next-token prediction*: given a sequence
of tokens, predict the next one. For encoder models (BERT), it is *masked language
modelling*: predict randomly masked tokens.

Pre-training consumes the majority of compute. It instils broad world knowledge,
reasoning patterns, and language capability into the model weights.

## Supervised Fine-Tuning (SFT)

After pre-training, the base model is fine-tuned on curated (instruction, response) pairs
to produce a model that follows instructions rather than just completing text. SFT is fast
relative to pre-training and can shift model behaviour significantly with relatively few
high-quality examples.

## Reinforcement Learning from Human Feedback

[[reinforcement-learning-from-human-feedback]] (RLHF) goes further by training a reward
model from human preference comparisons, then using RL to optimise the language model
against that reward. This is the technique behind InstructGPT, ChatGPT, and early Claude
models.

## Direct Preference Optimisation (DPO)

DPO (Rafailov et al., 2023) achieves similar alignment results to RLHF without requiring
a separate reward model or RL training loop. It directly optimises the language model on
preference pairs using a cross-entropy objective, making it simpler and more stable.
Many recent open-weight models (Llama 3 Instruct, Mistral Instruct) use DPO.

## Continued Pre-training and Domain Adaptation

A base model can be further pre-trained on domain-specific corpora (legal, medical, code)
to improve specialist performance before instruction fine-tuning. This approach is
cheaper than training a specialist model from scratch.

## See Also

- [[reinforcement-learning-from-human-feedback]] — the full RLHF pipeline
- [[large-language-models]] — models produced by these techniques
- [[scaling-laws]] — how training data volume interacts with model size

## Mixed Precision Training

Training frontier-scale models requires substantial memory and compute. **Mixed precision training** addresses this by using lower-precision numerical formats for most operations while maintaining stability.

- **FP32 (32-bit floating point)** — the traditional full-precision format, used for optimizer states and master weights where numerical stability matters.
- **FP16 (16-bit floating point)** — halves memory compared to FP32 and accelerates computation on modern GPUs (e.g., NVIDIA Tensor Cores). However, FP16 has a narrow dynamic range, risking underflow for small gradients and overflow for large ones.
- **BF16 (Brain Floating Point)** — a 16-bit format that preserves FP32's exponent range while sacrificing mantissa precision. It has become the default for training [[large-language-models]] because it avoids the scaling issues of FP16.

## Gradient Checkpointing

Activation memory (the memory used to store intermediate activations needed for backpropagation) scales with model depth and batch size. **Gradient checkpointing** trades compute for memory by recomputing activations during the backward pass rather than storing them all. This enables training models that would otherwise exceed GPU memory at the cost of ~30% additional compute.

## Distributed Training

Training modern [[large-language-models]] requires distributing computation across many GPUs because no single device has sufficient memory or compute. Three main parallelism strategies are used, often in combination:

1. **Data Parallelism** — the model is replicated on each GPU, and each replica processes a different shard of the batch. Gradients are synchronised across replicas (e.g., via all-reduce). This is the simplest strategy but requires each replica to hold the full model.
2. **Tensor Parallelism** — individual weight matrices are split across GPUs, with each device computing part of a matrix multiplication. Communication is frequent (every layer), but this reduces per-device memory for model weights. Used inside [[transformer-architecture]] blocks.
3. **Pipeline Parallelism** — model layers are partitioned across GPUs in a pipeline. Different devices compute different layers for different micro-batches simultaneously, keeping all GPUs busy. Suffers from a "bubble" at pipeline start and end.

## ZeRO Optimisation

**ZeRO (Zero Redundancy Optimizer)**, introduced with Microsoft's **DeepSpeed** library, eliminates memory redundancy in data-parallel training. Standard data parallelism replicates the full model state (parameters, gradients, optimizer states such as [[training-techniques|AdamW]] moments) on every GPU. ZeRO partitions these states across devices in three stages:

- **Stage 1** — partition optimizer states.
- **Stage 2** — additionally partition gradients.
- **Stage 3** — additionally partition parameters, enabling training of models larger than a single GPU's memory.

ZeRO is foundational for training frontier-scale models and pairs naturally with the parallelism strategies above.

## Mixed Precision Training

Training [[large-language-models]] requires enormous compute, and mixed precision training is one of the most important techniques for making this tractable. Instead of training exclusively in FP32 (32-bit floating point), mixed precision uses lower-precision numerical formats for parts of the computation where precision loss is acceptable, while maintaining higher precision where needed (e.g., for loss scaling or master weight copies).

**BF16 vs FP16:** Two common reduced-precision formats are FP16 (half-precision floating point) and BF16 (bfloat16). BF16 has the same exponent range as FP32 but reduced mantissa precision, making it less prone to underflow and overflow during training. This has made BF16 increasingly preferred over FP16 on modern hardware such as NVIDIA A100 and later GPUs, since BF16 typically does not require loss scaling.

## Distributed Training

As model sizes have grown beyond the memory capacity of a single accelerator, distributed training strategies have become essential:

- **Data Parallelism** — The same model is replicated across multiple devices, with each device processing a different mini-batch of data. Gradients are synchronised across devices after each step. This is the simplest parallelism strategy but requires the full model to fit on each device.
- **Tensor Parallelism** — Individual weight matrices or layers are split across multiple devices, with each device computing a portion of the matrix multiplication. This reduces per-device memory usage at the cost of inter-device communication.
- **Pipeline Parallelism** — Different layers of the model are placed on different devices, forming a pipeline through which micro-batches of data flow. This allows training models that are too large for a single device but introduces pipeline bubble overhead.
- **ZeRO (Zero Redundancy Optimizer)** — Developed as part of Microsoft's deepspeed library, ZeRO addresses memory redundancy in data-parallel training by sharding optimiser states, gradients, and/or parameters across devices rather than replicating them fully. ZeRO Stage 1 shards optimiser states, Stage 2 also shards gradients, and Stage 3 also shards parameters.

## Gradient Checkpointing

Gradient checkpointing (also called activation recomputation) trades compute for memory by discarding intermediate activations during the forward pass and recomputing them as needed during the backward pass. This dramatically reduces memory consumption at the cost of roughly 30% additional compute, enabling larger batch sizes or model sizes on memory-constrained hardware.

## Optimisers

While stochastic-gradient-descent remains the conceptual foundation, Adam (Kingma & Ba, 2014) and its decoupled-weight-decay variant **AdamW** (Loshchilov & Hutter, 2019) have become the standard optimisers for training [[large-language-models]]. AdamW decouples weight decay from the gradient-based update, which was shown to improve generalisation compared to applying L2 regularisation within the Adam update rule.

## Optimization & Training Mechanics

Beyond the high-level pipeline of pre-training, SFT, and [[reinforcement-learning-from-human-feedback]], training [[large-language-models]] requires careful optimization choices that affect stability, throughput, and memory usage.

### Loss Function and Optimizer

Pre-training uses **cross-entropy loss** over token predictions. The dominant optimizer is **AdamW**, a variant of Adam with decoupled weight decay that regularizes weight parameters independently from the gradient update. AdamW replaced vanilla Adam and SGD for most large-scale training because it converges faster at the extreme batch sizes used in LLM training.

### Learning Rate Scheduling

A **cosine learning rate schedule** gradually decays the learning rate from a peak value to a minimum following a cosine curve. It has become standard because it provides smooth decay that avoids the sharp drops of step schedules, improving final model quality.

### Mixed Precision Training

To reduce memory and increase throughput on modern GPUs, training uses **mixed precision**, combining multiple floating-point formats:

- **FP32** (32-bit floating point) — full precision, used for master weights and optimizer states.
- **BF16** (bfloat16) — 16-bit format with the same exponent range as FP32 but reduced mantissa precision; preferred on modern accelerators (e.g., NVIDIA A100/H100) because it avoids scaling issues.
- **FP16** (half precision) — 16-bit format with higher mantissa precision but limited exponent range; requires loss scaling to prevent gradient underflow.

Master weights are kept in FP32 while forward/backward passes run in BF16 or FP16, halving memory usage and roughly doubling throughput.

### Memory-Efficiency Techniques

**Gradient checkpointing** trades compute for memory: instead of storing all intermediate activations for backpropagation, selected activations are recomputed on demand during the backward pass. This allows training much larger models or with larger batch sizes on a given GPU.

### Distributed Training Parallelism

Training modern [[large-language-models]] requires distributing computation across many GPUs. Three main parallelism strategies are used, often in combination:

1. **Data parallelism** — each GPU holds a full model copy and processes a different shard of the batch; gradients are synchronized across GPUs (via all-reduce).
2. **Tensor parallelism** — individual weight matrices are split across GPUs, with each GPU computing a portion of each layer's output. This reduces per-GPU memory but introduces communication overhead.
3. **Pipeline parallelism** — model layers are partitioned into stages assigned to different GPUs, with mini-batches pipelined through the stages.

**ZeRO** (Zero Redundancy Optimizer), implemented in Microsoft's **DeepSpeed** library, reduces memory redundancy in data-parallel training by partitioning optimizer states, gradients, and (in higher stages) parameters across data-parallel workers rather than replicating them on each GPU.

These techniques — combined with [[attention-mechanisms]] and the [[transformer-architecture]] — make it feasible to train models at the scale of modern LLMs.

## Mixed Precision Training

Training at full FP32 precision is unnecessarily expensive. Mixed precision training maintains a master copy of weights in FP32 but performs the forward and backward passes in FP16 or BF16 (brain float). BF16 is preferred for large models because it has the same exponent range as FP32 (preventing overflow on large activations) while using half the memory. ^[training-techniques.txt:15-15] Gradient scaling is used with FP16 to prevent underflow in very small gradients. ^[training-techniques.txt:17-17]

## Gradient Checkpointing

Storing all activations in memory during the forward pass for use in the backward pass is memory-prohibitive for large models. Gradient checkpointing (also called activation recomputation) stores only a subset of activations and recomputes the others during the backward pass. This trades increased compute (roughly 30% overhead) for substantially reduced memory requirements. ^[training-techniques.txt:21-21]

## Distributed Training

Large models do not fit on a single GPU. Several parallelism strategies are used in combination. ^[training-techniques.txt:25-25]

- **Data parallelism**: the model is replicated across multiple devices, each processing a different mini-batch. Gradients are averaged across replicas before the weight update (all-reduce). ZeRO (Zero Redundancy Optimizer, from DeepSpeed) shards the optimizer state, gradients, and optionally the parameters across data-parallel ranks, dramatically reducing memory per device. ^[training-techniques.txt:27-27]
- **Tensor parallelism**: individual matrix multiplications within a layer are split across devices. The attention and feedforward sublayers are parallelised row-wise or column-wise, with all-reduce communications after each split computation. ^[training-techniques.txt:29-29]
- **Pipeline parallelism**: different layers of the model are assigned to different devices. Micro-batches flow through the pipeline; the main overhead is pipeline bubbles when devices wait for the previous stage to complete. ^[training-techniques.txt:31-31]

## Optimisation in Pre-Training

Pre-training uses [[stochastic-gradient-descent]] variants — most commonly AdamW, which adds decoupled weight decay to the Adam optimiser's adaptive learning rate, reducing overfitting on large models. ^[training-techniques.txt:9-9] A cosine learning rate schedule is standard: the rate warms up linearly over the first few thousand steps, then decays to a small fraction of the peak rate by the end of training. ^[training-techniques.txt:9-9] Batch size is typically set to maximise GPU utilisation, with large batches (one to four million tokens per step) distributed across thousands of accelerators. ^[training-techniques.txt:11-11]

## Parameter-Efficient Fine-Tuning

Full fine-tuning of a 70B parameter model requires substantial compute. Parameter-efficient fine-tuning (PEFT) methods update only a small subset of parameters. ^[training-techniques.txt:41-41]

- **LoRA (Hu et al., 2021)**: adds low-rank decomposition matrices to the weight matrices of attention and feedforward layers. Only these small matrices (typically 0.1–1% of total parameters) are trained. LoRA achieves performance comparable to full fine-tuning on most tasks while requiring a fraction of the compute and memory. ^[training-techniques.txt:43-43]
- **QLoRA (2023)**: combines LoRA with quantisation — the base model weights are quantised to 4-bit (NF4 format) and held frozen, while LoRA adapters are trained in 16-bit. This allows fine-tuning a 65B model on a single consumer GPU. ^[training-techniques.txt:45-45]

## Tokenisation

Input text must be converted to discrete tokens before being fed to the model. Modern LLMs use byte-pair encoding (BPE) or SentencePiece tokenisation. BPE iteratively merges frequent character pairs into larger units, producing a vocabulary of 32,000 to 128,000 tokens that balances coverage of common words with handling of rare or novel tokens. ^[training-techniques.txt:49-49] Tokenisation efficiency matters: a more efficient tokeniser represents the same text in fewer tokens, reducing compute and context length requirements. GPT-4's cl100k tokeniser handles code and multilingual text substantially more efficiently than earlier tokenisers. ^[training-techniques.txt:51-51]

## Pre-Training Data Quality and Filtering

The quality of the pre-training corpus has a large effect on downstream performance. Common filtering steps include: ^[training-techniques.txt:55-55]

- **Language identification**: keeping only pages in the target language or desired language mix. ^[training-techniques.txt:57-57]
- **Deduplication**: removing near-duplicate documents using MinHash or similar techniques. Duplicate documents can dominate gradient updates and cause memorisation. ^[training-techniques.txt:59-59]
- **Quality filtering**: using classifiers trained on curated reference corpora (Wikipedia, books) to score and filter web pages. ^[training-techniques.txt:61-61]
- **PII redaction**: removing or masking personal data. ^[training-techniques.txt:63-63]

Open pre-training corpora such as the Dolma dataset (2024) document their filtering pipelines in detail, providing a reference for practitioners. ^[training-techniques.txt:65-65]
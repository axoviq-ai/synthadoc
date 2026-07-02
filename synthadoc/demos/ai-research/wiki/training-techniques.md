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
- file: deep-learning-concepts.pptx
  hash: c9d2b153e6a4f807851234dab56efc90c9d2b153e6a4f807851234dab56efc90
  ingested: '2026-05-09'
  size: 44032
status: active
tags:
- training
- fine-tuning
- alignment
- llm
title: Training Techniques
type: concept
updated: '2026-06-27'
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

Training frontier-scale models requires substantial memory and compute. **Mixed precision training** addresses this by using lower-precision numerical formats for most operations while maintaining stability. ^[training-techniques.txt:15-15]

- **FP32 (32-bit floating point)** — the traditional full-precision format, used for optimizer states and master weights where numerical stability matters. ^[training-techniques.txt:15-15]
- **FP16 (16-bit floating point)** — halves memory compared to FP32 and accelerates computation on modern GPUs (e.g., NVIDIA Tensor Cores). However, FP16 has a narrow dynamic range, risking underflow for small gradients and overflow for large ones. ^[training-techniques.txt:15-17]
- **BF16 (Brain Floating Point)** — a 16-bit format that preserves FP32's exponent range while sacrificing mantissa precision. It has become the default for training [[large-language-models]] because it avoids the scaling issues of FP16. ^[training-techniques.txt:15-15]

## Gradient Checkpointing

Activation memory (the memory used to store intermediate activations needed for backpropagation) scales with model depth and batch size. **Gradient checkpointing** trades compute for memory by recomputing activations during the backward pass rather than storing them all. This enables training models that would otherwise exceed GPU memory at the cost of ~30% additional compute. ^[training-techniques.txt:21-21]

## Distributed Training

Training modern [[large-language-models]] requires distributing computation across many GPUs because no single device has sufficient memory or compute. Three main parallelism strategies are used, often in combination: ^[training-techniques.txt:25-25]

1. **Data Parallelism** — the model is replicated on each GPU, and each replica processes a different shard of the batch. Gradients are synchronised across replicas (e.g., via all-reduce). This is the simplest strategy but requires each replica to hold the full model. ^[training-techniques.txt:27-27]
2. **Tensor Parallelism** — individual weight matrices are split across GPUs, with each device computing part of a matrix multiplication. Communication is frequent (every layer), but this reduces per-device memory for model weights. Used inside [[transformer-architecture]] blocks. ^[training-techniques.txt:29-29]
3. **Pipeline Parallelism** — model layers are partitioned across GPUs in a pipeline. Different devices compute different layers for different micro-batches simultaneously, keeping all GPUs busy. Suffers from a "bubble" at pipeline start and end. ^[training-techniques.txt:31-31]

## ZeRO Optimisation

**ZeRO (Zero Redundancy Optimizer)**, introduced with Microsoft's **DeepSpeed** library, eliminates memory redundancy in data-parallel training. Standard data parallelism replicates the full model state (parameters, gradients, optimizer states such as [[training-techniques|AdamW]] moments) on every GPU. ZeRO partitions these states across devices in three stages: ^[training-techniques.txt:27-27]

- **Stage 1** — partition optimizer states. ^[training-techniques.txt:27-27]
- **Stage 2** — additionally partition gradients. ^[training-techniques.txt:27-27]
- **Stage 3** — additionally partition parameters, enabling training of models larger than a single GPU's memory. ^[training-techniques.txt:27-27]

ZeRO is foundational for training frontier-scale models and pairs naturally with the parallelism strategies above.

## Mixed Precision Training

Training [[large-language-models]] requires enormous compute, and mixed precision training is one of the most important techniques for making this tractable. Instead of training exclusively in FP32 (32-bit floating point), mixed precision uses lower-precision numerical formats for parts of the computation where precision loss is acceptable, while maintaining higher precision where needed (e.g., for loss scaling or master weight copies). ^[training-techniques.txt:15-17]

**BF16 vs FP16:** Two common reduced-precision formats are FP16 (half-precision floating point) and BF16 (bfloat16). BF16 has the same exponent range as FP32 but reduced mantissa precision, making it less prone to underflow and overflow during training. This has made BF16 increasingly preferred over FP16 on modern hardware such as NVIDIA A100 and later GPUs, since BF16 typically does not require loss scaling. ^[training-techniques.txt:15-17]

## Distributed Training

As model sizes have grown beyond the memory capacity of a single accelerator, distributed training strategies have become essential:

- **Data Parallelism** — The same model is replicated across multiple devices, with each device processing a different mini-batch of data. Gradients are synchronised across devices after each step. This is the simplest parallelism strategy but requires the full model to fit on each device. ^[training-techniques.txt:27]
- **Tensor Parallelism** — Individual weight matrices or layers are split across multiple devices, with each device computing a portion of the matrix multiplication. This reduces per-device memory usage at the cost of inter-device communication. ^[training-techniques.txt:29]
- **Pipeline Parallelism** — Different layers of the model are placed on different devices, forming a pipeline through which micro-batches of data flow. This allows training models that are too large for a single device but introduces pipeline bubble overhead. ^[training-techniques.txt:31]
- **ZeRO (Zero Redundancy Optimizer)** — Developed as part of Microsoft's deepspeed library, ZeRO addresses memory redundancy in data-parallel training by sharding optimiser states, gradients, and/or parameters across devices rather than replicating them fully. ZeRO Stage 1 shards optimiser states, Stage 2 also shards gradients, and Stage 3 also shards parameters. ^[training-techniques.txt:27]

## Gradient Checkpointing

Gradient checkpointing (also called activation recomputation) trades compute for memory by discarding intermediate activations during the forward pass and recomputing them as needed during the backward pass. This dramatically reduces memory consumption at the cost of roughly 30% additional compute, enabling larger batch sizes or model sizes on memory-constrained hardware. ^[training-techniques.txt:19-21]

## Optimisers

While stochastic-gradient-descent remains the conceptual foundation, Adam (Kingma & Ba, 2014) and its decoupled-weight-decay variant **AdamW** (Loshchilov & Hutter, 2019) have become the standard optimisers for training [[large-language-models]]. AdamW decouples weight decay from the gradient-based update, which was shown to improve generalisation compared to applying L2 regularisation within the Adam update rule. ^[training-techniques.txt:9]

## Optimization & Training Mechanics

Beyond the high-level pipeline of pre-training, SFT, and [[reinforcement-learning-from-human-feedback]], training [[large-language-models]] requires careful optimization choices that affect stability, throughput, and memory usage.

### Loss Function and Optimizer

Pre-training uses **cross-entropy loss** over token predictions. The dominant optimizer is **AdamW**, a variant of Adam with decoupled weight decay that regularizes weight parameters independently from the gradient update. AdamW replaced vanilla Adam and SGD for most large-scale training because it converges faster at the extreme batch sizes used in LLM training. ^[training-techniques.txt:7-9]

### Learning Rate Scheduling

A **cosine learning rate schedule** gradually decays the learning rate from a peak value to a minimum following a cosine curve. It has become standard because it provides smooth decay that avoids the sharp drops of step schedules, improving final model quality. ^[training-techniques.txt:9]

### Mixed Precision Training

To reduce memory and increase throughput on modern GPUs, training uses **mixed precision**, combining multiple floating-point formats:

- **FP32** (32-bit floating point) — full precision, used for master weights and optimizer states.
- **BF16** (bfloat16) — 16-bit format with the same exponent range as FP32 but reduced mantissa precision; preferred on modern accelerators (e.g., NVIDIA A100/H100) because it avoids scaling issues.
- **FP16** (half precision) — 16-bit format with higher mantissa precision but limited exponent range; requires loss scaling to prevent gradient underflow.

Master weights are kept in FP32 while forward/backward passes run in BF16 or FP16, halving memory usage and roughly doubling throughput. ^[training-techniques.txt:15-17]

### Memory-Efficiency Techniques

**Gradient checkpointing** trades compute for memory: instead of storing all intermediate activations for backpropagation, selected activations are recomputed on demand during the backward pass. This allows training much larger models or with larger batch sizes on a given GPU. ^[training-techniques.txt:21]

### Distributed Training Parallelism

Training modern [[large-language-models]] requires distributing computation across many GPUs. Three main parallelism strategies are used, often in combination:

1. **Data parallelism** — each GPU holds a full model copy and processes a different shard of the batch; gradients are synchronized across GPUs (via all-reduce).
2. **Tensor parallelism** — individual weight matrices are split across GPUs, with each GPU computing a portion of each layer's output. This reduces per-GPU memory but introduces communication overhead.
3. **Pipeline parallelism** — model layers are partitioned into stages assigned to different GPUs, with mini-batches pipelined through the stages.

**ZeRO** (Zero Redundancy Optimizer), implemented in Microsoft's **DeepSpeed** library, reduces memory redundancy in data-parallel training by partitioning optimizer states, gradients, and (in higher stages) parameters across data-parallel workers rather than replicating them on each GPU. ^[training-techniques.txt:25-31]

These techniques — combined with [[attention-mechanisms]] and the [[transformer-architecture]] — make it feasible to train models at the scale of modern LLMs.
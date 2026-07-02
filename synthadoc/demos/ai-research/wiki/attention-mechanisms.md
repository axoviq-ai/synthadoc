---
aliases: []
categories:
- Transformer Architectures and Attention
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
- architecture
- attention
- transformers
- nlp
title: Attention Mechanisms
type: concept
updated: '2026-06-27'
---

# Attention Mechanisms

Attention allows a neural network to focus on the most relevant parts of its input when
producing each element of its output. It was originally proposed for sequence-to-sequence
models (Bahdanau et al., 2014) as a way to help encoders handle long sequences, and was
later generalised into the self-attention mechanism at the heart of the [[transformer-architecture]].

## Scaled Dot-Product Attention

The standard attention operation takes three matrices — queries (Q), keys (K), and values
(V) — and computes:

```
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) V
```

The scaling factor `sqrt(d_k)` prevents the dot products from growing large in high
dimensions, which would push the softmax into regions with very small gradients.

## Multi-Head Attention

Rather than performing a single attention pass, transformers run attention in parallel
across multiple "heads", each learning different relationship patterns. The outputs are
concatenated and projected back to the model dimension. Multi-head attention allows the
model to jointly attend to information from different representation subspaces.

## How Attention Changed Language Model Training

Before self-attention, RNNs were forced to compress all context into a fixed-size hidden
state before decoding — a bottleneck that degraded performance on long sequences. Attention
lets every token directly access every other token in the sequence in a single operation.
This had two major consequences:

1. **Full parallelisation** — the attention matrix is computed in one pass over the full
   sequence, enabling GPU-parallel training at scale
2. **No vanishing gradient over distance** — long-range dependencies are as easy to learn
   as short-range ones

Together, these properties enabled the shift from RNN-based models to the
[[transformer-architecture]], which in turn enabled the scaling trajectory described in
[[scaling-laws]] and the emergence of [[large-language-models]].

## Key Variants

- **Cross-attention** — queries from the decoder attend to keys/values from the encoder
- **Sparse attention** — only attend to a subset of tokens (e.g. Longformer, BigBird) for
  long-context efficiency
- **Flash Attention** — a hardware-aware kernel that computes exact attention in O(N) memory
  rather than O(N²), enabling much longer context windows in practice

## See Also

- [[transformer-architecture]] — the full architecture built on multi-head attention
- [[large-language-models]] — models that rely on attention at every layer

## Multi-Head Attention

Rather than performing a single attention function, the transformer applies multiple attention "heads" in parallel, each with its own learned projections for queries, keys, and values. The outputs are concatenated and linearly projected: ^[attention-mechanisms.txt:29-31]

```
MultiHead(Q, K, V) = Concat(head_1, ..., head_h) W^O
where head_i = Attention(Q W_i^Q, K W_i^K, V W_i^V)
```

Multi-head attention allows the model to attend to information from different representation subspaces at different positions simultaneously, a property a single attention head cannot capture. ^[attention-mechanisms.txt:34]

## Self-Attention vs Cross-Attention

- **Self-attention** — queries, keys, and values all come from the same sequence. This is the mechanism used in encoder layers and in decoder-only models like the GPT family. ^[attention-mechanisms.txt:38]
- **Cross-attention** — queries come from one sequence (e.g., the decoder) while keys and values come from another (e.g., the encoder output). This is what connects the encoder and decoder in the original [[transformer-architecture]]. ^[attention-mechanisms.txt:40]

## Beyond NLP

Although attention was introduced for neural-machine-translation (Bahdanau et al., 2014) ^[attention-mechanisms.txt:7] and popularized by the [[transformer-architecture]] for NLP, it has since become foundational to vision transformers (ViTs), speech models, and multimodal systems that combine text, images, and audio. ^[attention-mechanisms.txt:64] Attention is now considered a general-purpose sequence and set operator in deep learning. ^[attention-mechanisms.txt:3]

## Multi-Head Attention

Multi-head attention applies multiple parallel attention heads, each operating on different learned linear projections of the queries, keys, and values. This allows the model to attend to information from different representation subspaces simultaneously. The outputs of all heads are concatenated and linearly projected to produce the final result. ^[attention-mechanisms.txt:29-34] Multi-head attention is a core component of the [[transformer-architecture]], enabling models to capture diverse relationships in the input.

## Beyond Language

While attention mechanisms were developed for sequence-to-sequence models and became central to the [[transformer-architecture]] underpinning [[large-language-models]], they have since been adopted across modalities. ^[attention-mechanisms.txt:3-7] Vision transformers (ViTs) apply self-attention to patches of images, treating them analogously to tokens in a text sequence. ^[attention-mechanisms.txt:64] Multimodal systems combine attention across text, images, and audio, using both self-attention (within a modality) and cross-attention (between modalities) to fuse information. ^[attention-mechanisms.txt:40,64]

## The Scaling Factor

The division by sqrt(d_k) in the attention formula serves a critical role in training stability. Without this scaling, as the dimensionality of keys grows, the dot products QK^T tend to grow in magnitude, pushing the softmax function into regions of extremely small gradients. This makes optimisation difficult. By normalising by sqrt(d_k), the variance of the dot products is kept roughly constant, allowing gradients to flow effectively during backpropagation. This detail is often overlooked in introductory treatments but was crucial to making the [[transformer-architecture]] trainable at scale. ^[attention-mechanisms.txt:19-19]

## Multi-Head Attention

Rather than performing a single attention function over the full dimensionality, the transformer applies multiple attention operations in parallel — each with its own learned projections for queries, keys, and values. This allows the model to jointly attend to information from different representation subspaces at different positions. The outputs of all heads are concatenated and linearly projected. ^[attention-mechanisms.txt:29-31] Multi-head attention gives the [[transformer-architecture]] the ability to capture diverse relational patterns simultaneously, which single-head attention cannot. ^[attention-mechanisms.txt:34-34]

## Broader Impact Beyond NLP

While originally developed for sequence-to-sequence translation, attention has become foundational across modalities. ^[attention-mechanisms.txt:3-3] Vision transformers (ViT) apply self-attention to patches of images, demonstrating that the same mechanism generalises beyond text. ^[attention-mechanisms.txt:64-64] Multimodal systems that combine vision, audio, and language all rely on attention as a core building block, making it one of the most widely transferred architectural innovations in deep learning. ^[attention-mechanisms.txt:64-64]
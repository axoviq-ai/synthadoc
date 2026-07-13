---
aliases: []
categories:
- Transformer Architectures and Attention
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: public-domain/attention-mechanisms.txt
  hash: placeholder
  ingested: '2026-04-08'
  size: 0
status: active
tags:
- architecture
- attention
- transformers
- nlp
title: Attention Mechanisms
type: concept
updated: '2026-07-12'
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

Rather than performing a single attention function, the transformer applies multiple attention "heads" in parallel, each with its own learned projections for queries, keys, and values. The outputs are concatenated and linearly projected:

```
MultiHead(Q, K, V) = Concat(head_1, ..., head_h) W^O
where head_i = Attention(Q W_i^Q, K W_i^K, V W_i^V)
```

Multi-head attention allows the model to attend to information from different representation subspaces at different positions simultaneously, a property a single attention head cannot capture.

## Self-Attention vs Cross-Attention

- **Self-attention** — queries, keys, and values all come from the same sequence. This is the mechanism used in encoder layers and in decoder-only models like the GPT family.
- **Cross-attention** — queries come from one sequence (e.g., the decoder) while keys and values come from another (e.g., the encoder output). This is what connects the encoder and decoder in the original [[transformer-architecture]].

## Beyond NLP

Although attention was introduced for neural-machine-translation (Bahdanau et al., 2014) and popularized by the [[transformer-architecture]] for NLP, it has since become foundational to vision transformers (ViTs), speech models, and multimodal systems that combine text, images, and audio. Attention is now considered a general-purpose sequence and set operator in deep learning.

## Multi-Head Attention

Multi-head attention applies multiple parallel attention heads, each operating on different learned linear projections of the queries, keys, and values. This allows the model to attend to information from different representation subspaces simultaneously. The outputs of all heads are concatenated and linearly projected to produce the final result. Multi-head attention is a core component of the [[transformer-architecture]], enabling models to capture diverse relationships in the input.

## Beyond Language

While attention mechanisms were developed for sequence-to-sequence models and became central to the [[transformer-architecture]] underpinning [[large-language-models]], they have since been adopted across modalities. Vision transformers (ViTs) apply self-attention to patches of images, treating them analogously to tokens in a text sequence. Multimodal systems combine attention across text, images, and audio, using both self-attention (within a modality) and cross-attention (between modalities) to fuse information.

## The Scaling Factor

The division by sqrt(d_k) in the attention formula serves a critical role in training stability. Without this scaling, as the dimensionality of keys grows, the dot products QK^T tend to grow in magnitude, pushing the softmax function into regions of extremely small gradients. This makes optimisation difficult. By normalising by sqrt(d_k), the variance of the dot products is kept roughly constant, allowing gradients to flow effectively during backpropagation. This detail is often overlooked in introductory treatments but was crucial to making the [[transformer-architecture]] trainable at scale.

## Multi-Head Attention

Rather than performing a single attention function over the full dimensionality, the transformer applies multiple attention operations in parallel — each with its own learned projections for queries, keys, and values. This allows the model to jointly attend to information from different representation subspaces at different positions. The outputs of all heads are concatenated and linearly projected. Multi-head attention gives the [[transformer-architecture]] the ability to capture diverse relational patterns simultaneously, which single-head attention cannot.

## Broader Impact Beyond NLP

While originally developed for sequence-to-sequence translation, attention has become foundational across modalities. Vision transformers (ViT) apply self-attention to patches of images, demonstrating that the same mechanism generalises beyond text. Multimodal systems that combine vision, audio, and language all rely on attention as a core building block, making it one of the most widely transferred architectural innovations in deep learning.

## Multi-Head Attention

Rather than running a single attention function on the full model dimension, multi-head attention applies h parallel attention heads, each operating on a lower-dimensional projection of Q, K, and V. The outputs of all heads are concatenated and linearly projected back to the model dimension.

```
MultiHead(Q, K, V) = Concat(head_1, ..., head_h) · W_O
where head_i = Attention(Q · W_Qi, K · W_Ki, V · W_Vi)
```

Multi-head attention allows the model to jointly attend to information from different representation subspaces at different positions. Each head can learn to attend to different syntactic or semantic relationships.

## Self-Attention vs Cross-Attention

In self-attention, Q, K, and V all come from the same sequence. This allows each position to attend to all other positions in the same sequence, capturing long-range dependencies without regard to distance.

In cross-attention, Q comes from one sequence (e.g. the decoder) and K, V come from another sequence (e.g. the encoder output). This is how the decoder in the original [[transformer-architecture]] attends to the source sequence.

## Causal (Masked) Self-Attention

Decoder-only [[large-language-models]] use causal (autoregressive) self-attention, where each position is allowed to attend only to previous positions and itself. This is implemented by masking future positions in the attention score matrix — setting their logits to negative infinity before softmax — so they receive zero weight.

Causal masking is what enables GPT-style models to be trained via next-token prediction while preserving the autoregressive property at inference time.

## Positional Encodings and Relative Attention

Standard self-attention is permutation-invariant: it has no built-in notion of position or order. Positional encodings are added to embeddings to inject position information.

The original [[transformer-architecture]] used fixed sinusoidal encodings. Later models used learned absolute positional embeddings (GPT-2, BERT). More recent work uses relative position encodings, where attention scores are modified based on the distance between positions rather than their absolute index. Rotary Position Embedding (RoPE), introduced by Su et al. in 2021 and used in LLaMA and many other models, encodes relative position by rotating the Q and K vectors in the complex plane.

## Efficient Attention

Standard self-attention has O(N²) time and space complexity in sequence length N, because the full N×N attention matrix must be computed. For long sequences this is prohibitive.

Flash Attention (Dao et al., 2022) achieves the same result as standard attention using O(N) GPU memory by computing attention in blocks and never materialising the full matrix. Flash Attention 2 (2023) improved parallelism and is now the standard implementation in most [[large-language-models]] training frameworks.

Linear attention variants approximate the softmax operation to achieve O(N) complexity but sacrifice exact computation. These remain an active research area.
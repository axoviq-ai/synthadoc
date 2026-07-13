---
aliases: []
categories:
- Transformer Architectures and Attention
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: public-domain/transformer-architecture.txt
  hash: placeholder
  ingested: '2026-04-08'
  size: 0
status: active
tags:
- architecture
- transformers
- attention
- nlp
title: Transformer Architecture
type: technology
updated: '2026-07-12'
---

# Transformer Architecture

The transformer is the dominant neural network architecture for natural language processing
and, increasingly, for vision, audio, and multimodal tasks. Introduced in the 2017 paper
*Attention Is All You Need* by Vaswani et al., it replaced recurrent networks (RNNs and
LSTMs) as the foundation for large-scale language models.

## Core Components

The transformer consists of an encoder-decoder structure, though many modern models use
only the decoder (GPT family) or only the encoder (BERT family).

1. **Tokenisation** — input text is split into subword tokens via BPE or SentencePiece
2. **Embedding layer** — tokens are mapped to dense vectors; positional encodings are added
3. **Multi-head self-attention** — each token attends to all others in the sequence
4. **Feed-forward network** — a two-layer MLP applied position-wise after attention
5. **Layer normalisation** — applied before or after each sub-layer (pre-norm vs post-norm)
6. **Residual connections** — stabilise gradient flow through deep stacks

## Why It Replaced RNNs

RNNs process tokens sequentially, preventing parallelisation during training. The
transformer's self-attention operates over the full sequence in parallel, enabling training
on orders-of-magnitude more data. Long-range dependencies — previously a weakness of RNNs
— are handled directly by [[attention-mechanisms]].

## Key Variants

- **GPT (decoder-only)** — autoregressive, trained to predict the next token
- **BERT (encoder-only)** — masked language modelling, suited for classification tasks
- **T5/BART (encoder-decoder)** — sequence-to-sequence tasks like translation and summarisation

## Scaling and Modern Extensions

The transformer has scaled remarkably well. [[scaling-laws]] established that performance
improves predictably with model size, dataset size, and compute budget. Extensions include
sparse attention for long contexts, mixture-of-experts (MoE) for parameter efficiency, and
rotary positional embeddings (RoPE) for better length generalisation.

## See Also

- [[attention-mechanisms]] — the mechanism at the core of the transformer
- [[large-language-models]] — how transformers became the foundation for LLMs
- [[training-techniques]] — how transformers are pre-trained and fine-tuned

## Why Transformers Replaced RNNs

The [[transformer-architecture]] displaced recurrent-neural-networks as the dominant approach for sequence modelling because its self-attention mechanism enables parallel processing of all sequence positions simultaneously. This eliminated two long-standing problems with recurrent architectures:

1. **Sequential computation bottleneck** — RNNs process tokens one at a time in order, preventing the parallelisation that GPUs could otherwise exploit. Transformers compute all positions in parallel, dramatically improving training throughput.
2. **Vanishing and exploding gradients** — information had to propagate across many sequential steps in an RNN, making it difficult to learn long-range dependencies. Self-attention provides direct (O(1)) connections between any two positions in the sequence.

These advantages made transformers the practical foundation for scaling to the large parameter counts and dataset sizes underlying modern [[large-language-models]]. The original architecture was introduced by vaswani-et-al at google-brain in the 2017 paper *Attention Is All You Need*.

## Architectural Origins

The transformer was introduced in 2017 by Vaswani et al. in the paper *Attention Is All You Need*, produced by google-brain (Google Brain) and Google Research. It was built around a self-attention-mechanism that processes sequences in parallel rather than sequentially, replacing [[early-neural-networks|RNNs]] as the dominant approach for sequence modelling.

## Key Structural Elements

The architecture is composed of several interlocking components:

- **Encoder-decoder structure** — the original design used both an encoder and a decoder, though many modern descendants use only one half.
- **Multi-head attention** — multiple attention operations run in parallel, allowing the model to attend to information from different representation subspaces simultaneously.
- **Feedforward sublayers** — position-wise fully connected layers applied after attention.
- **Positional encodings** — sinusoidal or learned vectors injected to give the model information about token order, since attention itself is permutation-invariant.

The transformer became the foundation for nearly all modern [[large-language-models]], including the GPT and BERT families.

## Detailed Components

**Scaled Dot-Product Attention**
The core operation computes attention weights as softmax(QK^T / sqrt(d_k))V, where Q, K, and V are query, key, and value matrices derived from the input. The scaling factor prevents the dot products from growing too large in high dimensions and pushing the softmax into saturated regions.

**Multi-Head Attention**
Rather than performing a single attention function, the transformer projects Q, K, and V into multiple lower-dimensional subspaces and applies attention in parallel across h heads. Each head can learn to attend to different positions and represent different relationships. Outputs are concatenated and linearly projected. This was introduced in [[attention-mechanisms]] research and is central to the original Vaswani et al. (2017) design.

**Feedforward Sublayers**
Each encoder and decoder layer contains a position-wise feedforward network — two linear transformations with a ReLU activation in between, applied independently to each position. This provides the model with additional representational capacity beyond attention.

**Positional Encodings**
Because the transformer contains no recurrence or convolution, it has no inherent notion of token order. Positional encodings — sinusoidal functions of position added to input embeddings — inject sequence order information. This allows the model to distinguish permutations of the same tokens.

**Rise to Dominance**
The transformer, developed by Vaswani et al. at Google Brain and Google Research, replaced recurrent-neural-networks (RNNs and LSTMs) as the dominant architecture for sequence modeling. Its parallelism and scalability made it the foundation for modern [[large-language-models]].

## Feedforward Sublayer

Each encoder and decoder layer contains a position-wise feedforward network — two linear transformations with a ReLU activation in between, applied independently to each position. The hidden dimension of the feedforward layer is typically four times the model dimension. Although described as a simple component, the feedforward sublayer contains the majority of the transformer's parameters. ^[transformer-architecture.txt:31-31]

## Pre-Norm vs Post-Norm

The original transformer places layer normalisation after the residual connection (post-norm). Later work found that placing layer normalisation before the sub-layer (pre-norm) improves training stability, particularly at large scale. Pre-norm has become standard in modern [[large-language-models]]. ^[transformer-architecture.txt:45-45]

## Flash Attention

In 2022, Dao et al. introduced Flash Attention, an exact [[attention-mechanisms]] algorithm that avoids materialising the full N×N attention matrix in GPU HBM by fusing the attention computation into a single kernel and using tiling. Flash Attention produces mathematically identical results to standard attention while using O(N) memory rather than O(N²), and is substantially faster in practice. Flash Attention 2 (2023) improved parallelism further. Flash Attention is now widely used in training large transformers. ^[transformer-architecture.txt:49-49]

## Influence Beyond NLP

The [[transformer-architecture]] has extended well beyond language modelling:

- **Vision** — Vision Transformer (ViT, 2020) applied patch-based self-attention to image classification.
- **Audio** — architectures such as Whisper use encoder-decoder transformers for speech recognition and translation.
- **Biology** — AlphaFold 2 (2021) used attention-based architectures for protein structure prediction.
- **Reinforcement learning** — the Decision Transformer and related work apply causal self-attention to sequential decision-making.

The transformer's combination of scalability, parallelism, and expressiveness made it the dominant architecture of the deep learning era, serving as the foundation for nearly all [[large-language-models]]. ^[transformer-architecture.txt:53-53]
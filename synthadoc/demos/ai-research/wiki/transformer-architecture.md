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
- transformers
- attention
- nlp
title: Transformer Architecture
type: technology
updated: '2026-06-27'
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

The [[transformer-architecture]] displaced recurrent-neural-networks as the dominant approach for sequence modelling because its self-attention mechanism enables parallel processing of all sequence positions simultaneously. ^[transformer-architecture.txt:7-7] This eliminated two long-standing problems with recurrent architectures:

1. **Sequential computation bottleneck** — RNNs process tokens one at a time in order, preventing the parallelisation that GPUs could otherwise exploit. Transformers compute all positions in parallel, dramatically improving training throughput. ^[transformer-architecture.txt:7-7]
2. **Vanishing and exploding gradients** — information had to propagate across many sequential steps in an RNN, making it difficult to learn long-range dependencies. Self-attention provides direct (O(1)) connections between any two positions in the sequence. ^[transformer-architecture.txt:7-7]

These advantages made transformers the practical foundation for scaling to the large parameter counts and dataset sizes underlying modern [[large-language-models]]. ^[transformer-architecture.txt:3-3] The original architecture was introduced by vaswani-et-al at google-brain in the 2017 paper *Attention Is All You Need*. ^[transformer-architecture.txt:3-3]

## Architectural Origins

The transformer was introduced in 2017 by Vaswani et al. in the paper *Attention Is All You Need*, produced by google-brain (Google Brain) and Google Research. ^[transformer-architecture.txt:3] It was built around a self-attention-mechanism that processes sequences in parallel rather than sequentially, replacing [[early-neural-networks|RNNs]] as the dominant approach for sequence modelling. ^[transformer-architecture.txt:3]

## Key Structural Elements

The architecture is composed of several interlocking components: ^[transformer-architecture.txt:11]

- **Encoder-decoder structure** — the original design used both an encoder and a decoder, though many modern descendants use only one half. ^[transformer-architecture.txt:11]
- **Multi-head attention** — multiple attention operations run in parallel, allowing the model to attend to information from different representation subspaces simultaneously. ^[transformer-architecture.txt:27]
- **Feedforward sublayers** — position-wise fully connected layers applied after attention. ^[transformer-architecture.txt:31]
- **Positional encodings** — sinusoidal or learned vectors injected to give the model information about token order, since attention itself is permutation-invariant. ^[transformer-architecture.txt:15]

The transformer became the foundation for nearly all modern [[large-language-models]], including the GPT and BERT families. ^[transformer-architecture.txt:3]

## Detailed Components

**Scaled Dot-Product Attention**
The core operation computes attention weights as softmax(QK^T / sqrt(d_k))V, where Q, K, and V are query, key, and value matrices derived from the input. The scaling factor prevents the dot products from growing too large in high dimensions and pushing the softmax into saturated regions. ^[transformer-architecture.txt:19-23]

**Multi-Head Attention**
Rather than performing a single attention function, the transformer projects Q, K, and V into multiple lower-dimensional subspaces and applies attention in parallel across h heads. Each head can learn to attend to different positions and represent different relationships. Outputs are concatenated and linearly projected. This was introduced in [[attention-mechanisms]] research and is central to the original Vaswani et al. (2017) design. ^[transformer-architecture.txt:27]

**Feedforward Sublayers**
Each encoder and decoder layer contains a position-wise feedforward network — two linear transformations with a ReLU activation in between, applied independently to each position. This provides the model with additional representational capacity beyond attention. ^[transformer-architecture.txt:31]

**Positional Encodings**
Because the transformer contains no recurrence or convolution, it has no inherent notion of token order. Positional encodings — sinusoidal functions of position added to input embeddings — inject sequence order information. This allows the model to distinguish permutations of the same tokens. ^[transformer-architecture.txt:15]

**Rise to Dominance**
The transformer, developed by Vaswani et al. at Google Brain and Google Research, replaced recurrent-neural-networks (RNNs and LSTMs) as the dominant architecture for sequence modeling. Its parallelism and scalability made it the foundation for modern [[large-language-models]]. ^[transformer-architecture.txt:3]
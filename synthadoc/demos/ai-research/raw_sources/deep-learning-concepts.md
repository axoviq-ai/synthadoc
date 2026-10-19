# Deep Learning Concepts
A concise reference for AI/ML practitioners.

## The Neural Network Stack

Input layer → hidden layers → output layer. Each layer applies a linear transform followed by a non-linear activation function. Common activations: ReLU, GELU, SiLU.

Training uses a forward pass to compute loss, then a backward pass to update weights via gradient descent. Standard optimisers: SGD, Adam, AdamW — AdamW is the default for LLM training.

## The Transformer Architecture

Introduced by Vaswani et al. (2017) in "Attention Is All You Need". Replaces recurrent layers with multi-head self-attention. Every token attends to every other token — O(N²) complexity per layer. Positional encodings (sinusoidal or learned) are added to embeddings. Pre-norm (LayerNorm applied before attention) is now standard for training stability.

## Attention Mechanism

Three projections from the input: Query (Q), Key (K), Value (V).

Attention scores: softmax(QK^T / sqrt(d_k)) · V

Multi-head attention runs h parallel attention heads and concatenates their outputs. Each head learns different relationship patterns. Flash Attention produces the exact same result using O(N) memory via kernel fusion.

## Training Pipeline

1. Pre-training: next-token prediction on ~1T–15T tokens.
2. Supervised fine-tuning (SFT): instruction-following examples.
3. Reward model: human rankings of output quality.
4. RLHF/DPO: align model to human preferences.

Compute budget determines the trade-off between model size and token count (Chinchilla laws).

## Key Scaling Findings

Loss follows a power law in N (parameters), D (tokens), and C (compute).

- Kaplan et al. 2020: model size matters most per unit compute.
- Chinchilla 2022: token count should scale approximately 20× parameters.
- GPT-3 and PaLM were significantly under-trained by the Chinchilla standard.
- The LLaMA series was designed to be compute-optimal or intentionally over-trained for inference efficiency.

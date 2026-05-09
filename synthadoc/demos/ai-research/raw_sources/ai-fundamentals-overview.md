# AI Fundamentals Overview

A reference overview of key concepts in modern AI and machine learning research.

## Neural Networks

Neural networks are computational models loosely inspired by the structure of biological
brains. They consist of layers of interconnected nodes (neurons) that transform input
data into predictions. Training adjusts the connection weights using gradient descent and
backpropagation to minimise a loss function.

Deep networks — those with many layers — can learn hierarchical representations of data.
Convolutional networks (CNNs) exploit spatial structure in images. Recurrent networks
(RNNs) process sequences. Transformers use self-attention and have become the dominant
architecture for language tasks.

## The Transformer

The transformer architecture (Vaswani et al., 2017) replaced recurrent networks for
sequence modelling. Its key innovation is multi-head self-attention, which allows every
token in a sequence to attend directly to every other token in parallel. This enabled
training at scales previously impossible with sequential RNNs.

The encoder processes input; the decoder generates output. Many modern language models
(GPT family) are decoder-only and trained autoregressively on next-token prediction.
BERT and its variants are encoder-only and trained with masked language modelling.

## Training Large Models

Pre-training on large, diverse text corpora instils general language understanding.
Fine-tuning then adapts the model to specific tasks or behaviours. Instruction tuning —
fine-tuning on (instruction, response) pairs — produces instruction-following models.
RLHF further aligns models with human preferences by training a reward model on
human-labelled comparisons, then using PPO to optimise against it.

## Scaling

Model performance improves predictably with scale: more parameters, more training data,
and more compute all reduce loss as power laws. The Chinchilla analysis (Hoffmann et al.,
2022) showed that training tokens should scale proportionally with model parameters —
roughly 20 tokens per parameter — for compute-efficient training.

## Key Researchers

Geoffrey Hinton contributed foundational work on backpropagation (1986), deep belief
networks (2006), and the AlexNet breakthrough (2012). Yann LeCun pioneered convolutional
neural networks for vision. Yoshua Bengio led early research on distributed
representations and recurrent models. Together they are often called the "Godfathers of
deep learning."

Andrej Karpathy worked on vision and autonomous driving at Tesla before producing widely
used educational resources on transformers and language models, including the nanoGPT
reference implementation and accompanying YouTube lectures.

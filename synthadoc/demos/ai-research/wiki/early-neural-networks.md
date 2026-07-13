---
aliases: []
categories:
- Neural Networks and Deep Learning
confidence: medium
created: 2026-05-09
orphan: false
sources:
- file: ai-fundamentals-overview.md
  hash: a3f8c2d1e4b9071652340abc98def765a3f8c2d1e4b9071652340abc98def765
  ingested: '2026-05-09'
  size: 3847
status: archived
tags:
- neural-networks
- perceptron
- history
- deep-learning
title: Early Neural Networks
type: concept
updated: '2026-06-27'
---

# Early Neural Networks

Early neural network research spans from McCulloch and Pitts's formal neuron model (1943) through the Perceptron (Rosenblatt, 1957), the first AI winter triggered by Minsky and Papert's *Perceptrons* critique (1969), Hopfield networks (1982), and the backpropagation revival (Rumelhart, Hinton & Williams, 1986).

## The Perceptron

Rosenblatt's Perceptron was the first trainable single-layer network. It could classify linearly separable patterns but failed on XOR — a limitation Minsky and Papert formalised, triggering a decade-long funding freeze.

## The Backpropagation Revival

The 1986 paper by Rumelhart, Hinton, and Williams demonstrated that multi-layer networks trained with backpropagation could learn internal representations, reigniting interest. [[geoffrey-hinton]] continued this line of work through the deep learning breakthroughs of the 2010s.

> **Archived:** This page was an initial survey. The modern continuation of this work — [[attention-mechanisms]], [[transformer-architecture]], and [[training-techniques]] — is now covered by dedicated pages.

## Feedforward Network Architecture

A standard feedforward neural network consists of an **input layer**, one or more **hidden layers**, and an **output layer**. Each layer is composed of **neurons** (nodes), and the network is **fully connected** — meaning every neuron in one layer connects via weighted edges to every neuron in the next. Signals flow in one direction only, from input to output, with no cycles or feedback connections. This layered, fully connected structure is the basic architecture underlying the [[early-neural-networks|neural network]] models developed throughout the field's history, from the early Perceptron through the [[geoffrey-hinton|backpropagation]]-trained multi-layer networks of the 1980s and onward. A typical diagram might show, for example, a 4-node input layer feeding into three hidden layers (6, 6, and 5 nodes) connected to a 3-node output layer, with layers often color-coded to distinguish their role in the computation.

## Feedforward Network Structure

A feedforward neural network is organised as a series of fully connected layers, where information flows in one direction from input to output without cycles. A typical architecture consists of:

- **Input layer** — receives the feature vector (one node per input dimension).
- **Hidden layers** — one or more intermediate layers of neurons where each neuron applies a weighted sum of all activations from the previous layer followed by a nonlinear activation function.
- **Output layer** — produces the final prediction (e.g., class scores or regression targets).

In a fully connected (dense) layer, every neuron is connected to every neuron in the preceding layer via a learnable weight, making the parameter count scale as the product of adjacent layer widths. Deeper networks stack more hidden layers, enabling hierarchical feature learning — a structural principle that traces back to the multilayer networks explored after the [[early-neural-networks|backpropagation revival]] of 1986.
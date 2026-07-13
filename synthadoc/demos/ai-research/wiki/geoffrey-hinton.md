---
aliases: []
categories:
- Neural Networks and Deep Learning
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: public-domain/geoffrey-hinton-biography.txt
  hash: placeholder
  ingested: '2026-04-08'
  size: 0
status: active
tags:
- researcher
- deep-learning
- neural-networks
- biography
title: Geoffrey Hinton
type: person
updated: '2026-07-12'
---

# Geoffrey Hinton

Geoffrey Hinton is a British-Canadian cognitive scientist and computer scientist widely
regarded as one of the founding figures of modern deep learning. His work on
backpropagation, Boltzmann machines, and deep belief networks laid the groundwork for the
neural network revolution of the 2010s.

## Key Contributions

**Backpropagation (1986)**  
Hinton, Rumelhart, and Williams published the landmark paper demonstrating that
backpropagation could efficiently train multi-layer neural networks. This established
the practical training algorithm still used, in refined form, for all modern networks.

**Deep Belief Networks (2006)**  
With Salakhutdinov, Hinton showed that deep networks could be effectively pre-trained
layer by layer using restricted Boltzmann machines (RBMs), then fine-tuned. This was the
first demonstration that deep architectures were trainable and useful — reigniting
interest in neural networks after years of stagnation.

**AlexNet (2012)**  
Hinton's lab produced AlexNet (Krizhevsky, Sutskever, Hinton), which won the ImageNet
Large Scale Visual Recognition Challenge by a 10.8 percentage point margin using a deep
convolutional neural network trained on GPUs. This result ended a decade of feature
engineering and established deep learning as the dominant paradigm for vision.

**Capsule Networks**  
Hinton proposed capsule networks as an alternative to CNNs, arguing that pooling discards
spatial relationships that are important for viewpoint-invariant recognition. Capsule
networks have not achieved the widespread adoption of CNNs.

## Departure from Google

Hinton joined Google in 2013 following the acquisition of his startup DNNresearch. In
May 2023 he resigned from Google to speak freely about the risks of AI development,
stating that he had come to believe AI systems could surpass human intelligence sooner
than he had previously expected, with potentially serious consequences.

## See Also

- [[training-techniques]] — techniques Hinton's research helped establish
- [[large-language-models]] — modern systems built on the foundations he pioneered
- [[andrej-karpathy]] — researcher who studied under Hinton at Toronto

## Persistence Through the AI Winter

After Minsky and Papert's *Perceptrons* (1969) critique effectively halted neural network research funding, Hinton was one of the few researchers who continued advocating for connectionist approaches. Working initially under christopher-longuet-higgins at the university-of-edinburgh and later at the university-of-cambridge, Hinton maintained that neural networks — not symbolic AI — would ultimately prove the most promising path to machine intelligence.

## The 1986 Nature Paper and the Revival

The landmark 1986 paper with david-rumelhart and james-mcclelland (often cited as Rumelhart, Hinton & Williams) is credited with popularizing backpropagation as a practical training algorithm for multi-layer networks. Earlier formulations existed in the work of werbos and linnainmaa, but Hinton's group demonstrated its viability for training meaningful representations, directly catalyzing the end of the first AI winter and enabling the connectionist revival of the late 1980s.

## Founding Figure of Modern Deep Learning

Hinton is widely regarded, alongside yann-lecun and yoshua-bengio, as one of the three founding figures of modern deep learning. His persistence through decades of academic skepticism — when mainstream AI favored symbolic methods — is considered a key reason the neural network paradigm survived at all, setting the stage for the breakthroughs of the 2010s.

## The Connectionist Trio

Hinton is frequently grouped with yann-lecun and yoshua-bengio as the three founding figures who sustained connectionist research through the AI winters of the 1980s and 1990s and are collectively recognized with the 2018 Turing Award. Together they championed neural network approaches when symbolic AI dominated, helping lay the intellectual foundation for the deep learning revolution.

## Academic Path

Hinton studied experimental psychology at the university-of-cambridge before completing his PhD at the university-of-edinburgh, where his advisor Christopher Longuet-Higgins encouraged him to abandon his interest in neural networks in favor of mainstream AI. Hinton famously ignored this advice, a decision that proved pivotal for the field.

## Key Collaborators

- **David Rumelhart and James McClelland** — co-authors of the landmark 1986 backpropagation paper published in *Nature*, which is credited with reviving interest in multi-layer neural networks.
- **Marvin Minsky and Seymour Papert** — whose 1969 critique *Perceptrons* triggered the first AI winter and the marginalization of connectionist research that Hinton persevered through.
- **Linnainmaa and Werbos** — credited with earlier mathematical formulations of the backpropagation idea (1970 and 1974 respectively) that the 1986 paper helped bring into mainstream use.

## Background and Early Career

Hinton's full name is Geoffrey Everest Hinton. He studied at the [[purpose]]'s domain of experimental psychology at the University of Cambridge before completing his PhD at the University of Edinburgh under Christopher Longuet-Higgins, a period during which connectionist ideas were academically unfashionable.

## The 1986 Backpropagation Paper

The landmark 1986 Nature paper that popularized early-neural-networks#Backpropagation for training multi-layer networks was co-authored by Hinton alongside David Rumelhart and James McClelland (notably via the *Parallel Distributed Processing* volumes), with related independent derivations earlier from Linnainmaa and Werbos.

## One of Three Founding Figures

Hinton is widely grouped with Yann LeCun and Yoshua Bengio as the three founding figures of modern deep learning — a trio whose complementary work on architectures, training algorithms, and advocacy sustained the field through its second winter and into the deep learning revolution.

## Early Life and Education

Geoffrey Everest Hinton was born in 1947 in Wimbledon, London. He studied experimental psychology at the [[geoffrey-hinton]] (BA, 1970) and earned his PhD in artificial intelligence from the University of Edinburgh in 1978, supervised by Christopher Longuet-Higgins. His doctoral work focused on learning representations in networks — a theme that defined his subsequent career.^[geoffrey-hinton-biography.txt:7-7]

## Connectionism and the Perceptron Debate

When Hinton began his research career, neural networks were in deep disfavour following Minsky and Papert's 1969 book *Perceptrons*, which demonstrated that single-layer networks could not solve problems like XOR. Research funding shifted to symbolic AI and expert systems. Hinton was among a small group — including David Rumelhart and James McClelland — who continued to believe that multi-layer networks trained with the right learning algorithm could overcome these limitations. This stance became known as the connectionist program.^[geoffrey-hinton-biography.txt:11-13]

## Boltzmann Machines and Deep Belief Networks

In the 1980s and early 1990s, Hinton developed [[boltzmann-machines]] — stochastic recurrent networks trained with a contrastive divergence algorithm. In 2006, he and collaborators published a landmark paper introducing [[deep-belief-networks]]: multi-layer generative models trained greedily, one layer at a time, using a restricted Boltzmann machine (RBM) at each layer. The paper showed that this unsupervised pre-training procedure could initialise a deep network in a region of parameter space from which supervised fine-tuning could succeed.^[geoffrey-hinton-biography.txt:23-25]

This work, alongside concurrent contributions from [[yann-lecun]] and [[yoshua-bengio]]'s groups, reignited interest in deep networks after more than a decade of stagnation and is credited with launching the deep learning era.^[geoffrey-hinton-biography.txt:27-27]

## AlexNet (2012)

The pivotal demonstration of deep learning's practical power came at ImageNet 2012. Hinton's graduate students Alex Krizhevsky and Ilya Sutskever trained a deep convolutional neural network ([[alexnet]]) on the ImageNet Large Scale Visual Recognition Challenge using GPUs. AlexNet achieved a top-5 error rate of 15.3%, compared to 26.2% for the best non-deep-learning entry — a gap of more than 10 percentage points that effectively ended debate about deep learning's competitiveness for vision tasks.^[geoffrey-hinton-biography.txt:31-33]

## Google Brain and Academic Career

After long careers at Carnegie Mellon University and the University of Toronto, Hinton joined Google Brain part-time in 2013 following Google's acquisition of his startup DNNresearch. He maintained his position at the University of Toronto while working at Google, where he contributed to research on distributed representations, capsule networks, and knowledge distillation.^[geoffrey-hinton-biography.txt:37-39]

## Departure from Google and AI Safety

In May 2023, Hinton resigned from Google to speak more freely about the risks of artificial intelligence. He stated that he had changed his view on the trajectory of AI capability and now believed that the risks of AI systems becoming more intelligent than humans were more serious and closer in time than he had previously thought. His public statements about AI risk drew significant media attention given his status as one of the field's founding figures and his prior history of scepticism toward near-term AI danger claims.^[geoffrey-hinton-biography.txt:43-45]

## Turing Award

In 2018, Hinton, [[yann-lecun]], and [[yoshua-bengio]] were jointly awarded the Turing Award — the highest honour in computer science — by the Association for Computing Machinery (ACM). The citation recognised their work that led to the deep learning breakthrough that has made neural networks a critical component of computing.^[geoffrey-hinton-biography.txt:49-49]

## Co-Founders of Deep Learning

Hinton is widely regarded as one of three founding figures of modern deep learning, alongside [[yann-lecun]] and [[yoshua-bengio]].^[geoffrey-hinton-biography.txt:3-3]
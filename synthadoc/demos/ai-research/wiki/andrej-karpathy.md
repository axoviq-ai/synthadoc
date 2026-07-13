---
aliases: []
categories:
- Neural Networks and Deep Learning
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: public-domain/andrej-karpathy-biography.txt
  hash: placeholder
  ingested: '2026-04-08'
  size: 0
status: active
tags:
- researcher
- llm
- pedagogy
- biography
title: Andrej Karpathy
type: person
updated: '2026-07-12'
---

# Andrej Karpathy

Andrej Karpathy is a Slovak-Canadian AI researcher known for his work in computer vision
and large language models, his leadership role at Tesla AI, and his widely-followed
educational content on deep learning.

## Career

**Stanford and OpenAI**  
Karpathy completed his PhD at Stanford under [[geoffrey-hinton]]'s collaborator Fei-Fei Li,
focusing on deep learning for image captioning. He was a founding member of OpenAI
(2015–2017), working on deep reinforcement learning before joining Tesla.

**Tesla Autopilot (2017–2022)**  
As Senior Director of AI at Tesla, Karpathy led the Autopilot vision team, building a
purely vision-based approach to autonomous driving at scale. He left Tesla in 2022.

**Return to OpenAI (2023)**  
Karpathy briefly rejoined OpenAI in 2023 before departing again to focus on education
and his own research.

## Educational Work

Karpathy is one of the most effective AI educators working today. His key resources:

- **CS231n** — Stanford course on Convolutional Neural Networks for Visual Recognition;
  lecture videos remain widely used
- **micrograd** — a minimal autograd engine (~100 lines of Python) that builds backprop
  from scratch, used to teach the foundations of neural networks
- **nanoGPT** — a clean, minimal implementation of a GPT-class language model; widely
  used as a reference implementation and teaching tool
- **"Let's build GPT from scratch"** — a 3-hour YouTube lecture walking through the
  full implementation of a transformer language model from first principles

## Influence on the Field

Karpathy's nanoGPT and associated lectures have become the canonical starting point for
researchers and engineers learning to build and fine-tune language models. His emphasis
on code clarity over abstraction aligns with how many practitioners prefer to learn.

## See Also

- [[transformer-architecture]] — the architecture covered in his GPT lectures
- [[large-language-models]] — the model family his educational work focuses on
- [[geoffrey-hinton]] — researcher whose group he was associated with at Stanford

## Return to OpenAI and Departure (2023–2024)

Karpathy rejoined openai in 2023, working alongside figures including ilya-sutskever and sam-altman. In February 2024, he departed OpenAI and subsequently announced the founding of a new venture focused on AI education.

## Education and Early Background

Karpathy completed his undergraduate studies at the university-of-toronto and university-of-british-columbia before pursuing his PhD at stanford-university under Fei-Fei Li.

## Return to OpenAI and Departure (2023–2024)

After leaving Tesla in 2022, Karpathy returned to openai before departing again in 2024. His second tenure at the organization overlapped with the leadership era shaped by figures such as Sam Altman, Elon Musk, and ilya-sutskever. Karpathy continued to be known for educational content on deep learning and LLM internals during this period.

## Key Research Contributions

**Dense Captioning** — During his Stanford PhD under fei-fei-li, Karpathy worked on dense captioning, generating natural language descriptions for regions within images rather than producing a single caption per image.

**Data Flywheel for Autonomous Driving** — At tesla, Karpathy helped develop the *data flywheel* strategy for autonomous driving: a self-reinforcing loop in which Tesla's fleet of vehicles continuously collects driving data, which is used to train better Autopilot models, which are then deployed back to the fleet, generating even more data. This approach allowed autopilot to improve at scale by leveraging real-world mileage from millions of consumer vehicles.

## Education

Karpathy completed his undergraduate studies at the university-of-toronto, followed by a master's degree at the university-of-british-columbia (UBC), before moving to Stanford for his PhD.

## Return to OpenAI and Departure (2023–2024)

After leaving Tesla, Karpathy briefly returned to openai in 2023 before departing again in 2024. He has since started a new venture, continuing his work in AI research and education. His time at OpenAI overlapped with figures such as sam-altman, elon-musk (as a co-founder), and ilya-sutskever.

## Tesla Contributions in Detail

During his five-year tenure at tesla, Karpathy championed the camera-only perception approach for Autopilot, arguing that a well-designed neural network could extract sufficient information from visual inputs alone. He also drove the development of the data flywheel — an iterative pipeline in which fleet-collected data continuously improved the deployed models, which in turn generated better data.

## Early Life and Education

Born in 1986 in Bratislava, Czechoslovakia (now Slovakia), Karpathy emigrated with his family to Canada as a child and grew up in Toronto. He earned a Bachelor of Computer Science from the [[geoffrey-hinton]]-affiliated University of Toronto in 2009, followed by a master's degree at the University of British Columbia. He completed his PhD at Stanford in 2016 under Fei-Fei Li in the Stanford Vision Lab. ^[andrej-karpathy-biography.txt:7-7]

## PhD Research

His dissertation contributed methods for aligning visual and textual representations, including *dense captioning* — generating descriptions for individual regions within an image rather than whole images. ^[andrej-karpathy-biography.txt:11-11] A widely cited contribution from this period is "Deep Visual-Semantic Alignments for Generating Image Descriptions" (2015), which used recurrent networks and bidirectional alignments between image regions and text fragments to generate detailed captions, and was influential in multimodal learning research. ^[andrej-karpathy-biography.txt:13-13]

## Tesla: Data Flywheel and Vision-Only Approach

Under Karpathy's leadership, Tesla's autonomous driving approach relied entirely on camera-based perception without radar or LiDAR — a technically controversial decision that distinguished Tesla from competitors like Waymo. ^[andrej-karpathy-biography.txt:21-21] He was a prominent advocate for the **data flywheel** strategy: Tesla's fleet collects edge cases in the real world, which train and improve neural networks, which are then deployed to collect more data. He presented this architecture and training pipeline in detail at Tesla AI Day in 2021 and 2022. ^[andrej-karpathy-biography.txt:23-23] He departed Tesla in July 2022. ^[andrej-karpathy-biography.txt:25-25]

## Return to OpenAI and Departure

Karpathy rejoined OpenAI in February 2023 as a researcher working on [[large-language-models]]. He departed again in February 2024 to pursue independent work. ^[andrej-karpathy-biography.txt:29-29]

## Educational Content

The Stanford CS231n (Convolutional Neural Networks for Visual Recognition) lecture series, which Karpathy co-developed, was a foundational resource for a generation of computer vision practitioners and remains freely available. ^[andrej-karpathy-biography.txt:33-33]

After leaving Tesla, he launched an educational YouTube channel and Substack. Notable video series include:

- *"The spelled-out intro to neural networks and backpropagation: building micrograd"* — implements [[training-techniques]]-relevant backpropagation from scratch.
- *"Let's build GPT: from scratch, in code, spelled out"* — walks through a full [[transformer-architecture]] implementation from first principles in Python.

These videos have been viewed millions of times and are widely recommended as introductory resources. ^[andrej-karpathy-biography.txt:35-35]

## nanoGPT

**nanoGPT** (released December 2022) is an open-source repository implementing a GPT in approximately 300 lines of PyTorch. Designed for readability rather than production optimisation, it serves as a reference implementation for educational use and can train a GPT-2-equivalent model in a few hours on a single GPU. ^[andrej-karpathy-biography.txt:37-37]

## Eureka Labs

In July 2024, Karpathy announced **Eureka Labs**, a company focused on AI-native education. Its founding premise is that [[large-language-models]] can serve as teaching assistants — grading work, answering questions, and guiding students — at scale and personalisation levels beyond what human educators alone can achieve. The company's first product targets AI and machine learning education. ^[andrej-karpathy-biography.txt:41-41]
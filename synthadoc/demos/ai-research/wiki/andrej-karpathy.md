---
aliases: []
categories:
- Neural Networks and Deep Learning
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
- researcher
- llm
- pedagogy
- biography
title: Andrej Karpathy
type: person
updated: '2026-06-28'
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

Karpathy rejoined openai in 2023, working alongside figures including ilya-sutskever and sam-altman. ^[andrej-karpathy-biography.txt:29-29] In February 2024, he departed OpenAI and subsequently announced the founding of a new venture focused on AI education. ^[andrej-karpathy-biography.txt:29-29]

## Education and Early Background

Karpathy completed his undergraduate studies at the university-of-toronto and university-of-british-columbia before pursuing his PhD at stanford-university under Fei-Fei Li. ^[andrej-karpathy-biography.txt:7-7]

## Return to OpenAI and Departure (2023–2024)

After leaving Tesla in 2022, Karpathy returned to openai before departing again in 2024. ^[andrej-karpathy-biography.txt:29-29] His second tenure at the organization overlapped with the leadership era shaped by figures such as Sam Altman, Elon Musk, and ilya-sutskever. ^[andrej-karpathy-biography.txt:17-17] Karpathy continued to be known for educational content on deep learning and LLM internals during this period.

## Key Research Contributions

**Dense Captioning** — During his Stanford PhD under fei-fei-li, Karpathy worked on dense captioning, generating natural language descriptions for regions within images rather than producing a single caption per image. ^[andrej-karpathy-biography.txt:11-11]

**Data Flywheel for Autonomous Driving** — At tesla, Karpathy helped develop the *data flywheel* strategy for autonomous driving: a self-reinforcing loop in which Tesla's fleet of vehicles continuously collects driving data, which is used to train better Autopilot models, which are then deployed back to the fleet, generating even more data. ^[andrej-karpathy-biography.txt:23-23] This approach allowed autopilot to improve at scale by leveraging real-world mileage from millions of consumer vehicles. ^[andrej-karpathy-biography.txt:21-21]

## Education

Karpathy completed his undergraduate studies at the university-of-toronto, followed by a master's degree at the university-of-british-columbia (UBC), before moving to Stanford for his PhD. ^[andrej-karpathy-biography.txt:7-7]

## Return to OpenAI and Departure (2023–2024)

After leaving Tesla, Karpathy briefly returned to openai in 2023 before departing again in 2024. ^[andrej-karpathy-biography.txt:29-29] He has since started a new venture, continuing his work in AI research and education. ^[andrej-karpathy-biography.txt:3-3] His time at OpenAI overlapped with figures such as sam-altman, elon-musk (as a co-founder), and ilya-sutskever. ^[andrej-karpathy-biography.txt:17-17]

## Tesla Contributions in Detail

During his five-year tenure at tesla, Karpathy championed the camera-only perception approach for Autopilot, arguing that a well-designed neural network could extract sufficient information from visual inputs alone. ^[andrej-karpathy-biography.txt:21-21] He also drove the development of the data flywheel — an iterative pipeline in which fleet-collected data continuously improved the deployed models, which in turn generated better data. ^[andrej-karpathy-biography.txt:23-23]
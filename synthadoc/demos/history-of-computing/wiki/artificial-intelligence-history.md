---
aliases: []
categories:
- Quantum Computing & Next-Generation Paradigms
confidence: high
created: 2026-04-09
orphan: false
resource: https://www.youtube.com/watch?v=cizKWUASbW0
sources:
- file: public-domain/mccorduck-machines-who-think.txt
  hash: placeholder
  ingested: 2026-04-09
  size: 0
- file: https://www.youtube.com/watch?v=cizKWUASbW0
  hash: 0b35df51601160a9565c13804ebeeed4177ffd700c09676c7595c63f7286543e
  ingested: '2026-07-01'
  size: 43
status: active
tags:
- artificial-intelligence
- machine-learning
- deep-learning
- neural-networks
title: Artificial Intelligence History
type: concept
updated: '2026-07-01'
---

# Artificial Intelligence History

Artificial intelligence — the endeavour to build machines that exhibit intelligent behaviour — traces directly to [[alan-turing]]'s 1950 paper proposing the Turing Test. The field has cycled through periods of optimism, underfunding ("AI winters"), and transformative breakthroughs. - [[konrad-zuse]] — Konrad Zuse Z3 Computer

## Dartmouth Conference (1956)

John McCarthy, Marvin Minsky, Claude Shannon, and Nathaniel Rochester organised a two-month workshop at Dartmouth College in 1956, coining the term "artificial intelligence." The attendees believed that every aspect of intelligence could in principle be simulated by a machine. Early successes — game-playing programs, theorem provers, LISP — fuelled enormous optimism.

## First AI Winter (1974–1980)

Progress stalled as the limits of early approaches became clear. The Lighthill Report (UK, 1973) criticised AI research as failing to deliver on its promises. Funding dried up in the US and UK. The core problem was combinatorial explosion: search-based methods that worked on toy problems failed catastrophically at real-world scale.

## Expert Systems and Second AI Winter (1980s)

The 1980s saw a commercial revival through expert systems — rule-based programs encoding domain expert knowledge. Companies built billion-dollar businesses on systems like XCON (Digital Equipment Corp). But expert systems were brittle, expensive to maintain, and couldn't learn. A second AI winter followed in the late 1980s as their limitations became apparent.

## Neural Networks and Machine Learning (1986–2000s)

Geoffrey Hinton, David Rumelhart, and Ronald Williams popularised backpropagation in 1986, enabling multi-layer neural networks to learn from data. Support Vector Machines (Vapnik, 1995) and random forests provided strong statistical learning alternatives. The shift was epistemological: instead of hand-coding rules, systems would learn patterns from data.

## Deep Learning Breakthrough (2012)

AlexNet, a deep convolutional neural network by Alex Krizhevsky, Ilya Sutskever, and Geoffrey Hinton, won the ImageNet competition in 2012 with an error rate that shocked the field. The key enablers: large labelled datasets, GPU compute (see [[transistor-and-microchip]]), and improved training techniques. Deep learning then swept speech recognition, machine translation, and game-playing (DeepMind's AlphaGo, 2016).

## Large Language Models (2017–present)

The transformer architecture (Vaswani et al., 2017) — "Attention Is All You Need" — replaced recurrent networks for language tasks. Scaled up with massive datasets and GPU clusters, transformers became large language models (GPT series, BERT, Claude, Gemini). These systems exhibit emergent capabilities that were not explicitly programmed, reopening fundamental questions about the nature of intelligence that [[alan-turing]] first posed.

See also: [[programming-languages-overview]] for Python's role as the dominant AI research language; [[internet-origins]] for the web-scale data that enabled deep learning.

## ELIZA and Early Chatbots (1966)
Joseph Weizenbaum at MIT created ELIZA in 1966, one of the first chatbot programs. Written in SLIP, ELIZA simulated a Rogerian psychotherapist by pattern matching user inputs to generate responses. Despite its simplicity, ELIZA sparked lasting debates about whether machines could exhibit genuine intelligence or merely simulate understanding. ^[mccorduck-machines-who-think.txt:19-21]

## AI Winters (1970s–1980s)
The field experienced significant setbacks known as "AI winters" — periods of reduced funding and public disappointment after initial optimism failed to deliver on ambitious promises. Early AI systems like Samuel's checkers program and McCarthy'sAdvice Taker demonstrated potential but faced fundamental limitations in representation, reasoning, and scalability. ^[mccorduck-machines-who-think.txt:25-27]

## Deep Learning Breakthrough
Modern AI resurgence began around the 2010s with deep learning — neural networks with multiple layers capable of learning hierarchical representations from raw data. Enabled by increased computational power (GPUs) and massive datasets, deep learning achieved breakthroughs in image recognition, natural language processing, and game playing, fundamentally transforming the field's capabilities and applications. ^[mccorduck-machines-who-think.txt:39-40]

## Early Programs and Limitations

One of the most notable early AI programs was eliza (1964-1966), created by Joseph Weizenbaum at MIT. ELIZA simulated conversation using pattern-matching techniques, particularly mimicking a Rogerian psychotherapist. Despite its simplicity, ELIZA demonstrated both the appeal of machine intelligence and its significant limitations—users often attributed understanding to the program that did not actually exist. ^[mccorduck-machines-who-think.txt:19-21]

## Statistical Revival and Machine Learning

Following the AI winters—periods of reduced funding and interest due to overhyped expectations—AI research experienced a revival through statistical and probabilistic approaches in the 1980s and 1990s. This shift toward data-driven methods laid groundwork for modern machine learning. ^[mccorduck-machines-who-think.txt:31-35]

## Deep Learning Breakthroughs

The 2010s witnessed transformative breakthroughs through deep learning, where neural networks with multiple layers achieved unprecedented results in image recognition, natural language processing, and game playing. These advances built upon earlier theoretical foundations while enabling practical applications far beyond earlier capabilities.^[mccorduck-machines-who-think.txt:39-41]

## Early Breakthroughs: ELIZA and Joseph Weizenbaum

One of the most significant early demonstrations of AI was eliza, a computer program developed by Joseph Weizenbaum at MIT between 1964 and 1966. ELIZA simulated a Rogerian psychotherapist by using pattern matching and substitution methodology to give responses that appeared to understand human conversation. The program was so convincing that some users believed they were communicating with a real human therapist, raising profound questions about machine intelligence and human perception. Weizenbaum later expressed concern about the ethical implications of his creation, famously refusing to allow ELIZA to be used for genuine psychological counseling.

## Statistical Revival and Deep Learning

After the AI winters, the field experienced a revival through statistical and machine learning approaches in the 1990s and 2000s. The development of deep-learning neural networks with multiple layers allowed AI systems to learn hierarchical representations from data, leading to breakthroughs in image recognition, natural language processing, and game playing. This approach built upon earlier connectionist research but benefited from increased computational power and large datasets.

## Early AI Programs and the First AI Winter

Following the Dartmouth Conference, early AI research produced notable programs such as joseph-weizenbaum's ELIZA (1966), a natural language processing program that simulated a Rogerian psychotherapist. ^[mccorduck-machines-who-think.txt:19-21] Despite initial optimism, the field encountered its first "AI winter" in the 1970s, when funding and interest declined due to unmet expectations and technical limitations. ^[mccorduck-machines-who-think.txt:25-27]

## Early AI Programs

### Logic Theorist (1956)
Allen Newell, Herbert Simon, and J.C. Shaw developed the Logic Theorist, the first AI program to prove mathematical theorems. It successfully proved 38 of the first 52 theorems in Principia Mathematica, marking one of the earliest successful demonstrations of AI reasoning. ^[mccorduck-machines-who-think.txt:15]

### General Problem Solver (GPS)
Also created by Newell and Simon in 1957, GPS was designed to mimic human problem-solving approaches. It represented problems as state-space searches and used means-ends analysis, introducing foundational concepts in heuristic search that influenced AI research for decades. ^[mccorduck-machines-who-think.txt:15]

### ELIZA (1966)
Joseph Weizenbaum at MIT created ELIZA, a natural language processing program that simulated conversation through pattern matching. Originally designed as a therapeutic chatbot mimicking a Rogerian psychotherapist, ELIZA demonstrated early capabilities in human-computer dialogue and became a landmark in natural language AI research. ^[mccorduck-machines-who-think.txt:19-20]

## First AI Winter (1974–1980)

The first AI winter followed a period of unmet expectations. Despite early optimism after Dartmouth and initial successes with Logic Theorist and GPS, AI systems proved limited in handling real-world complexity. Funding agencies (particularly ARPA and UK research councils) reduced investments as practical applications failed to materialize at scale. The field experienced reduced research activity and publication rates, though key research continued in select laboratories. This period highlighted the gap between AI's theoretical promises and the computational resources needed to achieve them. ^[mccorduck-machines-who-think.txt:25-27]

## Key Figures Added

## Early Milestones Beyond Dartmouth

While the dartmouth-conference is often cited as AI's founding moment, parallel work was already underway. **Allen Newell** and **Herbert Simon** of Carnegie Mellon (then RAND Corporation) presented the **Logic Theorist** (1955) — widely considered the first AI program — which proved mathematical theorems from Principia Mathematica. They followed this with the **General Problem Solver** (1957), an early attempt to mimic human reasoning through means-ends analysis. ^[FILENAME:15-15]

## ELIZA and Early NLP (1960s)

joseph-weizenbaum created **ELIZA** (1964–1966) at MIT, one of the first programs to attempt natural language processing. ELIZA used simple pattern-matching to simulate a Rogerian psychotherapist, and its surprisingly human-like responses led Weizenbaum to argue against the uncritical acceptance of machine intelligence — an early ethical warning in the field. ELIZA demonstrated both the promise and the danger of anthropomorphising computer programs. ^[FILENAME:19-21]

## The Recurring AI Winter Cycle

The history of AI follows a recurring pattern of optimism, technical limitation, and disillusionment. After the initial enthusiasm of the 1950s and 1960s, the inability of early systems to scale to real-world problems — combined with the overpromising of researchers and the 1969 publication of the Lighthill report — led to significant funding cuts in the 1970s, a period known as the first **AI winter**. ^[FILENAME:25-27] This cycle of hype and retrenchment would repeat in subsequent decades, with the field experiencing further winters in the late 1980s and early 1990s before the deep learning revolution of the 2010s. ^[FILENAME:35-35] The concept of the **Turing test**, proposed by [[alan-turing]] in 1950, remained a philosophical benchmark throughout these cycles, even as the practical definition of progress in AI shifted away from human-level mimicry toward task-specific capability. ^[FILENAME:7-9]

## Early Symbolic Systems and Critiques (1956–1974)

Following the Dartmouth Conference, researchers pursued symbolic AI grounded in logic and rule-based reasoning. The *Logic Theorist* (1956), developed by Allen Newell, Herbert Simon, and J.C. Shaw, was among the first programs to automatically prove mathematical theorems — demonstrating that machines could perform tasks previously thought to require human intelligence. Later, the *General Problem Solver* (1957) extended this approach to broader heuristic search.^[15:15]

In 1966, Joseph Weizenbaum created eliza, a natural language program simulating a Rogerian psychotherapist. Though deliberately shallow — relying on pattern matching and scripted responses — ELIZA revealed strong human tendencies to anthropomorphize interaction, raising enduring questions about operational definitions of intelligence and the ethics of deceptive interface design.^[19:19]

These early successes were followed by growing skepticism as promises outpaced capabilities, culminating in the first ai-winter — a period of reduced funding and interest beginning in the early 1970s, triggered by critiques like Weizenbaum’s *Computer Power and Human Reason* (1976) and reports highlighting limitations in scaling symbolic methods.^[25:27]

## Early AI Programs and the First AI Winter

Following the dartmouth-conference, early AI research produced several landmark programs that demonstrated the potential — and limits — of machine intelligence. Allen Newell and Herbert Simon developed the **Logic Theorist** (1955), often considered the first AI program, which proved mathematical theorems from Bertrand Russell and Alfred North Whitehead's *Principia Mathematica*. Their follow-up, the **General Problem Solver** (GPS), extended this approach by attempting to model human problem-solving as search through a space of possible states. ^[mccorduck-machines-who-think.txt:15-15]

**ELIZA** (1964–1966), created by Joseph Weizenbaum at MIT, was one of the most famous early chatbots. It simulated a Rogerian psychotherapist by rephrasing user inputs as questions, and its surprisingly human-like responses led some users to attribute genuine understanding to the program — a phenomenon Weizenbaum himself found troubling and used to critique the overreach of AI claims. ^[mccorduck-machines-who-think.txt:19-21]

These early successes fueled waves of optimism that the field would quickly achieve general machine intelligence. When that promise failed to materialize, funding dried up and the field entered the **first AI winter** in the 1970s, as government agencies and researchers grew disillusioned with the gap between ambitious predictions and practical results. ^[mccorduck-machines-who-think.txt:25-25] This cycle of optimism, disillusionment, and methodological recalibration — from symbolic search to expert systems, statistical methods, and ultimately deep learning — has recurred throughout the history of [[artificial-intelligence-history]] and continues to shape the field today. ^[mccorduck-machines-who-think.txt:3-3]

## Early NLP and Symbolic Systems

Before the first AI winter, natural language processing emerged as a prominent subfield. joseph-weizenbaum created eliza (1964–1966) at MIT, one of the earliest chatbots. ELIZA simulated a Rogerian psychotherapist by pattern-matching user input against scripted rules, and it famously convinced some users that the program genuinely understood them — a vivid early illustration of the gap between AI expectations and actual capabilities.^[mccorduck-machines-who-think.txt:19-21]

## First AI Winter (mid-1970s–1980s)

The field entered its first "AI winter," a period of reduced funding and diminished public interest. Overly optimistic promises from the 1960s collided with the limitations of symbolic approaches, the difficulty of scaling commonsense knowledge, and the brittleness of rule-based systems. Government agencies in both the US and UK cut research budgets, and commercial interest in AI products waned. The episode became a cautionary lesson about the cyclical pattern of inflated expectations followed by disillusionment that has recurred throughout AI's history.^[mccorduck-machines-who-think.txt:25-27]

## Symbolic to Statistical and Deep Learning

The long recovery from the first AI winter included the gradual displacement of purely symbolic approaches by statistical methods. By the 1990s, techniques such as hidden Markov models, Bayesian networks, and support vector machines dominated subfields like speech recognition and machine translation. This statistical turn paved the way for the deep learning revolution of the 2010s, where multilayer neural networks trained on large datasets produced breakthroughs in image recognition, game playing, and language modeling — echoing themes first explored at the dartmouth-conference and foreshadowed by [[alan-turing]]'s 1950 paper.^[mccorduck-machines-who-think.txt:39-41]

## Additional Pioneers

Beyond the four organisers of dartmouth-conference, early AI was shaped by allen-newell and herbert-simon, who developed the Logic Theorist (1956) and General Problem Solver (1957). Newell and Simon championed the view that cognition could be understood as symbol manipulation, founding an influential research programme in cognitive science and earning Simon the 1975 Turing Award.^[mccorduck-machines-who-think.txt:15]

## Early Milestones and Programs

Following the [[alan-turing|1950 Turing Test proposal]], several landmark programs and systems demonstrated the early ambitions of the field. The **Logic Theorist**, created by Allen Newell and Herbert Simon in 1955, is often cited as the first true AI program — it proved mathematical theorems from Principia Mathematica using heuristic search. ^[mccorduck-machines-who-think.txt:7-15] **ELIZA**, built by joseph-weizenbaum at MIT in 1964–1966, was an early natural language processing program that simulated a Rogerian psychotherapist. ^[mccorduck-machines-who-think.txt:19-21] Despite Weizenbaum's own warnings about its superficiality, ELIZA famously convinced many users that the machine understood them, foreshadowing modern debates about machine intelligence and anthropomorphism. ^[mccorduck-machines-who-think.txt:19-21]

## The Recurring Cycle: AI Winters and Revivals

AI's history is defined by a recurring pattern of **optimism, funding booms, disillusionment, and 'AI winters'** — periods of sharply reduced research funding and commercial interest after expectations outpaced results. ^[mccorduck-machines-who-think.txt:3-3] The first major winter occurred in the mid-1970s after critiques (notably the Lighthill Report in the UK) highlighted the limitations of then-current approaches. ^[mccorduck-machines-who-think.txt:25-27] A second winter followed in the late 1980s after the collapse of the expert-systems market. ^[mccorduck-machines-who-think.txt:35-35] Each winter was followed by a revival driven by new paradigms: expert systems in the 1980s, statistical machine learning in the 1990s and 2000s, and **deep learning** from the 2010s onward, fueled by large datasets, GPU computing, and breakthroughs in neural network training. ^[mccorduck-machines-who-think.txt:31-41]

## Philosophical Framing

From the outset, AI has been shaped by a deep philosophical question posed by [[alan-turing]] in 1950: *"Can machines think?* ^[mccorduck-machines-who-think.txt:7-9] The Dartmouth Conference participants — john-mccarthy, marvin-minsky, claude-shannon, and nathaniel-rochester — framed this as an engineering challenge, predicting that significant progress could be made within a generation. ^[mccorduck-machines-who-think.txt:13-13] The tension between Turing's behavioral framing (the imitation game) and the Dartmouth school's representational-symbol-manipulation view continues to influence modern debates between symbolic AI, connectionism, and large language models. ^[mccorduck-machines-who-think.txt:9-15]

## Early AI Programs (1955–1966)

Several landmark programs demonstrated that machines could perform tasks previously thought to require human intelligence.

### Logic Theorist (1955)

Developed by allen-newell and herbert-simon (with J. C. Shaw), Logic Theorist is often considered the first true AI program. It proved mathematical theorems from Whitehead and Russell's *Principia Mathematica* by heuristic search rather than brute-force enumeration, foreshadowing search-based approaches that would dominate the field.^[mccorduck-machines-who-think.txt:15-15]

### General Problem Solver (1957)

Also by allen-newell and herbert-simon, the General Problem Solver (GPS) generalized the means–ends analysis approach used in Logic Theorist. It attempted to solve a wide class of formally stated problems, making it one of the first attempts at domain-independent reasoning.^[mccorduck-machines-who-think.txt:15-15]

### ELIZA (1964–1966)

Created by joseph-weizenbaum at mit, ELIZA was an early natural-language program that simulated a Rogerian psychotherapist. By simple pattern matching and substitution, ELIZA produced surprisingly convincing dialogue, leading Weizenbaum himself to warn about the dangers of confusing apparent intelligence with genuine understanding — a tension that recurs throughout AI history.^[mccorduck-machines-who-think.txt:19-21]

## The First AI Winter (mid-1970s–early 1980s)

Following the collapse of the perceptron-based connectionist program (Minsky and Papert, 1969), a 1973 Lighthill Report commissioned by the British government was highly critical of AI's progress, and DARPA cut back funding after years of unmet expectations. This convergence of academic critique, loss of institutional support, and a sense that AI had overpromised produced the **first AI winter** — a period of reduced funding and waning interest in the field, in which research continued in less visible corners but public optimism collapsed.^[mccorduck-machines-who-think.txt:25-27] The pattern of optimism, disappointment, and retrenchment would repeat in later decades as well.

## Early AI Programs and NLP (1950s–1960s)

### Logic Theorist and GPS (1955–1956)

allen-newell and herbert-simon developed the Logic Theorist in 1955, often cited as the first AI program, followed by the General Problem Solver (GPS). Their work demonstrated that computers could perform reasoning tasks previously thought to require human intelligence, and it helped build momentum toward the dartmouth-conference. ^[FILENAME:mccorduck-machines-who-think.txt:15-15]

### ELIZA (1964–1966)

joseph-weizenbaum created ELIZA at MIT between 1964 and 1966, one of the earliest programs to attempt natural language processing. ELIZA used simple pattern-matching and substitution to simulate a Rogerian psychotherapist, often producing surprisingly human-seeming responses. ^[FILENAME:mccorduck-machines-who-think.txt:19-19] Despite Weizenbaum's intent to demonstrate the superficiality of machine understanding, many users — including some of his colleagues — attributed genuine empathy to the program, raising early ethical questions about human attachment to computational systems. ^[FILENAME:mccorduck-machines-who-think.txt:19-19]

## First AI Winter (mid-1970s–early 1980s)

Following the collapse of the Lighthill Report (1973) and funding cuts from DARPA and the British government, the field entered its first "AI winter." ^[FILENAME:mccorduck-machines-who-think.txt:25-27] Early promises of machine translation and general problem-solving had fallen short of expectations, and the gap between optimistic projections and delivered capabilities led to widespread disillusionment. ^[FILENAME:mccorduck-machines-who-think.txt:25-25] The pattern — ambitious claims, limited results, and retrenchment — became a recurring cycle in the field's history. ^[FILENAME:mccorduck-machines-who-think.txt:27-27]

## Toward Modern Deep Learning

The trajectory from symbolic, rule-based systems of the early decades toward data-driven approaches laid the groundwork for the deep learning revolution. ^[FILENAME:mccorduck-machines-who-think.txt:3-3] Connectionist ideas, initially marginalized during the symbolic AI era, were revived through advances in neural network training algorithms (backpropagation), increases in computational power, and the availability of large datasets. ^[FILENAME:mccorduck-machines-who-think.txt:39-39] This shift ultimately enabled breakthroughs in image recognition, natural language processing, and game-playing systems that defined contemporary AI. ^[FILENAME:mccorduck-machines-who-think.txt:41-41]

## Early NLP and the First AI Programs

### ELIZA (1964–1966)
joseph-weizenbaum at mit created ELIZA, one of the earliest programs to attempt natural language processing. ELIZA used simple pattern-matching and substitution to simulate a Rogerian psychotherapist, often producing strikingly human-seeming responses despite having no understanding of the conversation. Weizenbaum was reportedly disturbed by how deeply users confided in the program, raising early ethical questions about anthropomorphism in computing. ^[FILENAME:mccorduck-machines-who-think.txt:19-19]

### Logic Theorist and the Newell–Simon Programme
allen-newell and herbert-simon developed the Logic Theorist (1956) and later the General Problem Solver (1957), demonstrating that machine reasoning could, in principle, emulate human problem-solving strategies. Their work ran in parallel with the dartmouth-conference effort and helped establish the cognitive science strand of [[artificial-intelligence-history]]. ^[FILENAME:mccorduck-machines-who-think.txt:15-15]

## First AI Winter (mid-1970s)

After the initial optimism of the 1956–1970 era, funding dried up following critiques (notably the Lighthill Report, 1973) and unmet promises about machine translation and general intelligence. Research continued in more limited forms — largely within academia and at mit — but commercial and governmental support contracted significantly, a period known as the **first AI winter**. ^[FILENAME:mccorduck-machines-who-think.txt:25-27] The field would recover in the 1980s with the rise of expert systems before entering a second winter in the late 1980s. ^[FILENAME:mccorduck-machines-who-think.txt:31-35]

## Early Milestones and Programs (1955–1966)

Following the Dartmouth Conference, several landmark programs demonstrated the feasibility of machine intelligence:

- **Logic Theorist (1955–1956)**: Created by allen-newell and herbert-simon, Logic Theorist is often cited as the first AI program. It proved mathematical theorems from Whitehead and Russell's *Principia Mathematica* and even discovered more elegant proofs than the originals. ^[FILENAME:15-15]
- **General Problem Solver (GPS) (1957)**: Also developed by Newell and Simon, GPS was a framework designed to imitate human problem-solving through means-ends analysis, attempting to model the general strategies humans use rather than tackling specific problems. ^[FILENAME:15-15]

## ELIZA and Natural Language Processing (1966)

joseph-weizenbaum, a mit computer scientist, created ELIZA in 1966 — one of the first programs to attempt natural language conversation. ELIZA used simple pattern-matching and substitution to simulate a Rogerian psychotherapist, sometimes producing strikingly human-like responses. Despite its simplicity, ELIZA raised profound questions about the nature of machine understanding and is an early landmark in [[alan-turing]]'s imitation game tradition. ^[FILENAME:19-19]

## First AI Winter (1970s)

After initial enthusiasm, the field entered its first "AI winter" in the 1970s. Funding dried up as the lofty promises of the 1950s — machine translation, general problem-solving, and human-level intelligence — failed to materialize on predicted timescales. The gap between demonstrated programs (which handled toy problems) and real-world competence led to criticism from funders and a contraction of research activity, establishing the pattern of optimism and disillusionment that would recur throughout the field's history. ^[FILENAME:25-25]

## Andrew Ng and the Democratization of AI Education

Andrew Ng has played a pivotal role in making artificial intelligence and machine learning accessible to a global audience. As co-founder of coursera, founder of DeepLearning.AI, and partner at AI Fund, Ng combined an accessible teaching approach with strategic backing from Sequoia Capital to help democratize AI knowledge worldwide.^[john-reid-andrew-ng-ai-education:1-2] His widely adopted online courses became entry points for many into the field of AI, building on the educational legacy that followed from early AI research as discussed in the [[computing-history-timeline]].

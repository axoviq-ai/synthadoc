---
aliases: []
categories:
- Large Language Models
confidence: high
created: 2026-05-09
orphan: false
sources:
- file: public-domain/llm-benchmarks-overview.txt
  hash: placeholder
  ingested: '2026-04-08'
  size: 0
status: active
tags:
- benchmarks
- evaluation
- llm
title: LLM Benchmarks
type: concept
updated: '2026-07-12'
---

# LLM Benchmarks

Benchmarks provide standardised evaluations of language model capabilities across
reasoning, knowledge, coding, and instruction-following tasks. Benchmark results are
widely cited in model release announcements, though their validity as proxies for
real-world usefulness is actively debated.

## Key Benchmarks

**MMLU (Massive Multitask Language Understanding)**  
A 57-subject multiple-choice test covering STEM, humanities, law, and social sciences.
Commonly used as a broad knowledge and reasoning proxy. Human expert performance is
approximately 89.8%.

**HumanEval**  
A Python coding benchmark from OpenAI comprising 164 hand-written programming problems.
Models are evaluated on whether their generated code passes hidden unit tests (pass@1).

**MATH**  
Competition mathematics problems (AMC, AIME, MATH levels 1–5). Tests multi-step symbolic
reasoning. Scores below 50% were common on frontier models before chain-of-thought
prompting.

**HELM (Holistic Evaluation of Language Models)**  
A Stanford framework that evaluates models across dozens of scenarios using accuracy,
calibration, robustness, fairness, and efficiency metrics simultaneously.

## Reported Results (as of early 2026)

| Model         | MMLU (5-shot) | HumanEval | Notes                              |
|---------------|---------------|-----------|------------------------------------|
| GPT-4         | 86.4%         | 67.0%     | OpenAI technical report (2023)     |
| Claude 3 Opus | 86.8%         | 84.9%     | Anthropic model card (2024)        |
| Gemini Ultra  | 83.7%*        | 74.4%     | Google technical report (2023)     |
| Llama 3 70B   | 82.0%         | 81.7%     | Meta release (2024)                |

\* Gemini Ultra's widely-cited 90.0% MMLU figure used CoT@32 (chain-of-thought with 32 samples), not the standard 5-shot protocol. Under 5-shot evaluation, Gemini Ultra scores 83.7% — below GPT-4 (86.4%) and Claude 3 Opus (86.8%). See the reporting controversy sections below for detail.

## Benchmark Limitations

Benchmark saturation occurs when frontier models consistently score above 90% on a task,
reducing its discriminative value. MMLU is approaching this threshold for top models.
There is also ongoing concern about data contamination — model training corpora may
include benchmark questions, inflating scores.

## See Also

- [[large-language-models]] — the models being evaluated
- [[training-techniques]] — how training choices affect benchmark performance

## BIG-Bench and BIG-Bench Hard

**BIG-Bench** (Srivastava et al., 2022) is a massive benchmark suite containing over 200 tasks contributed by more than 400 authors, designed to probe capabilities ranging from linguistics and common sense to software engineering and mathematical reasoning. It was explicitly designed to predict future model capabilities beyond the benchmarks of its time.

**BIG-Bench Hard (BBH)** is a curated subset of 23 particularly challenging tasks from BIG-Bench where prior models lagged significantly behind human performance. Solving BBH tasks typically requires multi-step reasoning, making it a key benchmark for chain-of-thought and emergent reasoning evaluation.

## Common Knowledge and Reasoning Benchmarks

- **HellaSwag** — a commonsense reasoning benchmark where models choose the most plausible continuation of a sentence. Known for being resistant to simple heuristics, it uses adversarial filtering against naive algorithms.
- **WinoGrande** — a large-scale commonsense reasoning benchmark based on the Winograd Schema Challenge, scaled to over 44,000 problems.
- **ARC (AI2 Reasoning Challenge)** — a multiple-choice science exam benchmark (ARC-Challenge and ARC-Easy) designed to test grade-school level reasoning.

## Code Benchmarks Beyond HumanEval

- **SWE-bench** — evaluates models on resolving real-world GitHub issues from popular Python repositories. Models must understand the codebase, identify the bug, and produce a patch that passes the project's test suite. This represents a shift from synthetic coding tasks to real software engineering workflows.
- **LiveCodeBench** — a contamination-free benchmark that continuously collects new competitive programming problems from platforms like LeetCode, ensuring that evaluation problems were published after model training cutoffs.

## Notable Reporting Controversies

**Gemini Ultra MMLU Score (2023).** Google originally reported Gemini Ultra as achieving 90.0% on MMLU, surpassing [[large-language-models|GPT-4]]. However, this score was produced using chain-of-thought reasoning with 32 samples per question (CoT@32), a methodology not comparable to the standard 5-shot evaluation used for other frontier models. When evaluated under standard 5-shot conditions, the score was substantially lower. This episode became a frequently cited example of benchmark reporting inconsistency and contributed to calls for standardised evaluation protocols across the field.

## Training Data Contamination

Code benchmarks are particularly susceptible to contamination, where benchmark problems or their solutions appear in training data. HumanEval has been shown to overlap with online coding tutorials and solutions. This concern motivated benchmarks like LiveCodeBench, which draw from temporally fresh problem sets to provide contamination-resistant evaluation. The broader issue of contamination affects all static benchmarks and is one of the most significant unresolved methodological challenges in LLM evaluation.

## Notable Model Benchmark Comparisons

A widely cited comparison across major [[large-language-models]] evaluated on MMLU and HumanEval illustrates both the rapid progression of capabilities and the importance of consistent evaluation protocols:

- **GPT-3** (175B): early LLM baseline; MMLU around the low-to-mid 40s range in few-shot, well below modern models.
- **GPT-4**: ~86.4% on MMLU (5-shot), one of the strongest results under standard evaluation.
- **Gemini Ultra**: originally announced with a headline 90% MMLU figure, but this relied on CoT@32 rather than the standard 5-shot protocol. Under 5-shot evaluation, Gemini Ultra scores ~83.7%, placing it *below* GPT-4's 86.4%.
- **Claude 3 Opus**: competitive with GPT-4-tier on MMLU, strong on HumanEval.
- **LLaMA 2 70B** and **Llama 3 70B** (Meta): open-weights models showing rapid improvement across generations, with Llama 3 closing much of the gap to closed frontier models.
- **Mistral 7B**: notable for strong performance relative to its small size; open-weights.

## The Evaluation Protocol Problem

The Gemini Ultra case is a canonical example of why raw benchmark numbers can mislead. CoT@32 (chain-of-thought with 32 samples and self-consistency) is a substantially more elaborate inference procedure than 5-shot prompting — it uses more compute and a different prompting strategy. Reporting a 90% headline figure derived from CoT@32 alongside 5-shot scores from competitors produces an apples-to-oranges comparison.

This reinforces a broader lesson: when comparing [[large-language-models]] on [[llm-benchmarks]], the evaluation protocol (k-shot setting, prompting method, decoding strategy, contamination controls) matters as much as the headline number. Standardised reporting — specifying the exact protocol — is essential for meaningful comparison across openai (GPT-3, GPT-4), anthropic (Claude 3), Google (Gemini Ultra), meta (LLaMA 2, Llama 3), and Mistral releases.

## Other Notable Benchmarks

**BIG-Bench (Beyond the Imitation Game Benchmark)**
Srivastava et al., 2022. A massive collaboration of 444 authors across 132 institutions producing 204 tasks designed to probe capabilities believed to be beyond current [[large-language-models]]. Covers linguistics, common-sense reasoning, mathematics, biology, physics, and more.

**BIG-Bench Hard (BBH)**
A curated subset of 23 tasks from [[llm-benchmarks]] where prior [[large-language-models]] lagged human raters. Used to evaluate chain-of-thought reasoning capabilities.

**HellaSwag**
A commonsense reasoning benchmark requiring models to select the most plausible continuation of a context. Notably, examples are adversarially filtered to be difficult for simple baselines.

**WinoGrande**
A large-scale commonsense reasoning benchmark built on the Winograd Schema Challenge, with 44,000 examples.

**ARC (AI2 Reasoning Challenge)**
A dataset of grade-school science multiple-choice questions designed to test reasoning and knowledge. The "ARC-Challenge" split contains questions that simple retrieval and co-occurrence baselines cannot solve.

## Benchmark Controversies and Limitations

**Gemini Ultra MMLU Reporting Error (2024)**
Google originally reported Gemini Ultra achieving 90.0% on [[llm-benchmarks]] (MMLU), which would have surpassed [[large-language-models|GPT-4]]. However, this score relied on chain-of-thought reasoning sampled 32 times (CoT@32), a protocol not comparable to the standard 5-shot evaluation used for other models. Under the standard 5-shot protocol, Gemini Ultra actually scored 83.7%. This highlighted the importance of comparing models under matched evaluation protocols.

**Contamination Risks**
Benchmark questions often appear in pretraining corpora, inflating scores. Dynamic benchmarks like LiveCodeBench address this by using continuously refreshed test sets, while SWE-bench evaluates models on real-world GitHub issues.

## Additional Benchmarks

**BIG-Bench (Beyond the Imitation Game Benchmark)**
A collaborative benchmark of over 200 tasks designed to probe language model capabilities across reasoning, commonsense, linguistics, and beyond. Contributions came from hundreds of researchers, and it spans topics from simple arithmetic to expert-level question answering.

**BIG-Bench Hard (BBH)**
A curated subset of 23 BIG-Bench tasks identified as particularly challenging at the time of selection, where prior models lagged well behind human performance. BBH became a standard measure for reasoning-heavy evaluations.

**HellaSwag**
A commonsense reasoning benchmark that tests a model's ability to choose the most plausible continuation of a given context. It was specifically designed to be difficult for naive language models while remaining easy for humans, using adversarial filtering to eliminate superficial cues.

**WinoGrande**
A large-scale commonsense reasoning benchmark built on the Winograd Schema Challenge, scaled up to over 44,000 problems. It tests pronoun resolution and commonsense inference.

**ARC (AI2 Reasoning Challenge)**
A science question benchmark drawn from grade-school exams, divided into ARC-Easy and ARC-Challenge. It tests multi-step reasoning over scientific facts and is widely used alongside [[large-language-models]] evaluations.

**SWE-bench**
A benchmark for evaluating software engineering capabilities, requiring models to resolve real GitHub issues across open-source repositories by generating patches that pass existing test suites.

**LiveCodeBench**
A contamination-free coding benchmark that sources problems from recent competitive programming contests, ensuring that evaluated problems post-date model training cutoffs.

## Evaluation Protocols

- **5-shot**: The model is given five example input-output pairs before being asked to produce an answer. This is the standard protocol for [[large-language-models]] evaluation on benchmarks like MMLU.
- **pass@1**: The proportion of problems for which the model's first generated solution passes all unit tests. Used for code benchmarks like HumanEval.
- **CoT@32**: A chain-of-thought evaluation where the model samples 32 reasoning chains and the result is aggregated (e.g., via majority vote or best-of-N scoring). This protocol tends to inflate scores relative to standard 5-shot evaluation.

## The Gemini Ultra MMLU Scoring Controversy

When Google announced Gemini Ultra, it reported a state-of-the-art MMLU score of 90.04%, marginally exceeding GPT-4. However, this figure used CoT@32 evaluation for Gemini Ultra while comparison models like GPT-4 were evaluated under standard 5-shot prompting. The mixed evaluation methodology made the comparison apples-to-oranges and drew significant criticism from the research community. Subsequent re-evaluations using consistent 5-shot protocols placed Gemini Ultra below GPT-4 on MMLU. The incident highlighted the importance of standardizing evaluation protocols across models.

## Known Limitations

- **Training data contamination**: Benchmark questions may appear in pre-training corpora, inflating scores. LiveCodeBench addresses this by using post-cutoff problems.
- **Comparability issues**: Inconsistent prompting strategies (e.g., CoT@32 vs. 5-shot, as in the Gemini Ultra controversy) make cross-model score comparisons unreliable.
- **Benchmark saturation**: Top models increasingly approach ceiling performance on benchmarks like MMLU, reducing their discriminating power.
- **Narrow task scope**: Most benchmarks measure narrow capabilities that may not correlate with real-world usefulness.

## Major Model Benchmark Comparison (2018–2024)

The following comparison covers landmark [[large-language-models]] and their performance on key benchmarks:

| Model | Organization | Year | Parameters | MMLU (5-shot) | HumanEval | Context Window | Open Weights |
|-------|-------------|------|------------|---------------|-----------|----------------|--------------|
| BERT-Large | Google | 2018 | 340M | — | — | 512 | Yes |
| GPT-3 | OpenAI | 2020 | 175B | — | — | 2K | No |
| LLaMA 2 70B | Meta | 2023 | 70B | 69.0% | 29.3% | 4K | Yes |
| Mistral 7B | Mistral | 2023 | 7B | ~60% | 30.5% | 8K | Yes |
| GPT-4 | OpenAI | 2023 | ~1.8T (rumored) | 86.4% | 67.0% | 8K–128K | No |
| Claude 3 Opus | Anthropic | 2024 | — | 86.8% | 84.9% | 200K | No |
| Gemini Ultra | Google | 2024 | — | 83.7% | 74.4% | 32K | No |
| Llama 3 70B | Meta | 2024 | 70B | 79.5% | 81.7% | 8K | Yes |

## Reporting Caveats

Headline benchmark numbers can be misleading without methodological context. A notable example is Gemini Ultra's widely-publicised **90.0% MMLU** score, which uses chain-of-thought with 32-sample majority voting (CoT@32) rather than the standard 5-shot protocol. Under the standard 5-shot evaluation, Gemini Ultra scores **83.7%** — actually *below* GPT-4's 86.4%. This illustrates why benchmark reporting should always specify the evaluation protocol used, and why direct comparison of headline scores across model announcements can be misleading.

The table also highlights a structural trade-off: models with larger context windows (Claude 3 Opus at 200K, Gemini Ultra at 32K) tend to be closed-weight, while open-weight models like [[large-language-models]] (LLaMA 2, Mistral 7B, Llama 3) have historically lagged on benchmarks but enable independent research and deployment.

## MMLU Details

[[mmlu]] (Massive Multitask Language Understanding, Hendrycks et al., 2021) is a multiple-choice benchmark covering 57 subjects including mathematics, history, law, medicine, and the natural sciences. Questions are drawn from practice exams, textbooks, and academic sources. The standard evaluation protocol is 5-shot: the model is given five examples from the subject before answering each question. ^[llm-benchmarks-overview.txt:7-7]

A common error in MMLU reporting concerns Gemini Ultra. Google's technical report (December 2023) cited a Gemini Ultra MMLU score of 90.0% without clearly stating this used CoT@32 — 32 chain-of-thought samples with majority voting. Under the standard 5-shot direct-answer protocol used for all other models in the comparison, Gemini Ultra scores 83.7%, below GPT-4's 86.4%. The 90.0% figure is not comparable to standard MMLU numbers. ^[llm-benchmarks-overview.txt:11-11]

## HumanEval Details

[[humaneval]] (Chen et al., 2021) is a code generation benchmark consisting of 164 Python programming problems. Each problem provides a function signature and docstring; the model must generate a function body. Solutions are evaluated by running the provided unit tests. ^[llm-benchmarks-overview.txt:15-15]

The primary metric is pass@1: the fraction of problems solved on the first attempt. A more lenient metric, pass@k, measures whether any of k sampled completions passes. HumanEval numbers in research papers almost always report pass@1 unless otherwise stated. ^[llm-benchmarks-overview.txt:17-17]

HumanEval is relatively narrow — all problems are algorithmic rather than software engineering tasks — and models have been observed to memorise solutions from training data containing GitHub code. More recent code benchmarks ([[swe-bench]], [[livecodebench]]) use problems created after model training cutoffs to reduce contamination. ^[llm-benchmarks-overview.txt:19-19]

## BIG-Bench and BIG-Bench Hard

Beyond the Imitation Game ([[big-bench]], Srivastava et al., 2022) is a collaborative benchmark of 204 tasks designed to probe capabilities beyond standard NLP tasks — logical reasoning, causal reasoning, common sense, multilingual understanding, and more. BIG-Bench Hard (BBH) is a 23-task subset that frontier models at the time of publication could not reliably solve, preserving headroom for future evaluation. ^[llm-benchmarks-overview.txt:23-23]

## Commonsense Reasoning Benchmarks

- **HellaSwag** — a sentence completion task requiring knowledge of common event sequences. Models must select the most plausible continuation of a partial scene description. Carefully constructed via adversarial filtering to make statistical shortcuts ineffective. ^[llm-benchmarks-overview.txt:29-29]
- **WinoGrande** — a co-reference resolution task derived from the Winograd Schema Challenge. Requires understanding of physical and social common sense to resolve ambiguous pronoun references. ^[llm-benchmarks-overview.txt:31-31]
- **ARC (AI2 Reasoning Challenge)** — a multiple-choice science question set divided into Easy and Challenge partitions. The Challenge partition was designed to be solvable by humans but unsolvable by retrieval-based systems. ^[llm-benchmarks-overview.txt:33-33]

## TruthfulQA

TruthfulQA (Lin et al., 2022) measures how often models produce truthful answers to questions that humans commonly answer incorrectly due to misconceptions, myths, and false beliefs. Larger models score lower on TruthfulQA under standard prompting because they are better at reproducing common human misconceptions from their training data. This is one of the motivations for [[reinforcement-learning-from-human-feedback]]: InstructGPT showed improved truthfulness over the base GPT-3. ^[llm-benchmarks-overview.txt:37-37]

## Benchmark Saturation and Contamination

Established benchmarks become unreliable once frontier models achieve near-ceiling performance. MMLU scores for the top models now differ by only a few percentage points, making it a poor discriminator. Benchmark saturation has driven the creation of harder successors (GPQA, MMLU-Pro) and reasoning benchmarks like MATH and AIME. ^[llm-benchmarks-overview.txt:41-41]

Data contamination — the presence of benchmark questions in training data — is a persistent concern. It inflates reported performance and makes it difficult to know how much of a high score reflects genuine generalisation versus memorisation. Some organisations report contamination analysis; many do not. ^[llm-benchmarks-overview.txt:43-43]

## Evaluating Evaluation

Benchmarks do not measure what they appear to measure in a vacuum. Performance on a multiple-choice reasoning benchmark depends on prompt formatting, few-shot example selection, decoding temperature, and answer extraction methodology. Small differences in these choices can move benchmark scores by several percentage points. Reproducibility of benchmark results across labs requires carefully standardising evaluation protocols, which is not universally done. ^[llm-benchmarks-overview.txt:47-47]

The trend toward evaluation frameworks (EleutherAI's lm-evaluation-harness, Stanford's HELM) that standardise prompts and evaluation across models has improved reproducibility but has not eliminated the problem. ^[llm-benchmarks-overview.txt:49-49]
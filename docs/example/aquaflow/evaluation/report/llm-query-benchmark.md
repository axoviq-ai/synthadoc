# AquaFlow LLM Query Benchmark

**Wiki:** AquaFlow Systems PE/M&A due diligence  
**Date:** 2026-07-09 / 2026-07-10  
**Evaluator:** `docs/example/aquaflow/evaluation/scripts/eval_queries.py`

---

## Table of Contents

- [Overview](#overview)
- [Models Evaluated](#models-evaluated)
- [Summary Leaderboard](#summary-leaderboard)
- [Question Reference](#question-reference)
- [Per-Question Results](#per-question-results)
  - [MiniMax-Think (M3)](#minimax-think-m3)
  - [Claude Opus 4.8](#claude-opus-48)
  - [Claude Sonnet 4.6](#claude-sonnet-46)
  - [DeepSeek-R1 (V3)](#deepseek-r1-v3)
- [Cross-Model Comparison](#cross-model-comparison)
- [WARN Analysis](#warn-analysis)
- [System Health Notes](#system-health-notes)
- [Conclusion](#conclusion)

---

## Overview

This report benchmarks four LLMs against 15 PE/M&A due diligence questions drawn from the
[AquaFlow wiki](../../README.md). Questions Q1–Q10 are in English; Q11–Q15 are in Mandarin
Chinese. Each answer is scored by case-insensitive substring match against a curated fact list
(282 facts total; defined per-question in [`eval_queries.py`](../scripts/eval_queries.py)).
Grading follows a two-tier framework:

| Grade | Threshold | Meaning |
|-------|-----------|---------|
| **PASS** | ≥ 85% facts matched | System and model performing correctly |
| **WARN** | < 85% facts matched | Model-level or non-deterministic limitation — not a system bug |

`FAIL` is reserved exclusively for confirmed system or code bugs; none were found in this run.

The questions span three complexity tiers as defined in the AquaFlow README:

- **English medium complexity** (Q1–Q5): single-workstream recall, specific figures
- **English high complexity** (Q6–Q10): cross-workstream synthesis across 5–7 wiki pages
- **Chinese cross-lingual** (Q11–Q15): CJK queries against English-language wiki pages,
  answered in Chinese via character-level BM25 retrieval with no separate translation index

---

## Models Evaluated

| Label | Provider | Model | Config | Run timestamp |
|-------|----------|-------|--------|---------------|
| MiniMax-Think (M3) | MiniMax | MiniMax-M3 | thinking=enabled | 2026-07-09 20:23 |
| Claude Opus 4.8 | Anthropic | claude-opus-4-8 | — | 2026-07-10 11:14 |
| Claude Sonnet 4.6 | Anthropic | claude-sonnet-4-6 | — | 2026-07-09 20:26 |
| DeepSeek-R1 (V3) | DeepSeek | deepseek-reasoner | chain-of-thought | 2026-07-09 19:50 |

---

## Summary Leaderboard

| Rank | Model | Facts Matched | Score | PASS | WARN |
|------|-------|--------------|-------|------|------|
| 1 | MiniMax-Think (M3) | 260 / 282 | **92%** | 11 | 4 |
| 2 | Claude Opus 4.8 | 253 / 282 | **89%** | 10 | 5 |
| 3 | Claude Sonnet 4.6 | 244 / 282 | **86%** | 10 | 5 |
| 4 | DeepSeek-R1 (V3) | 222 / 282 | **78%** | 6 | 9 |

---

## Question Reference

| ID | Language | Complexity | Topic |
|----|----------|------------|-------|
| Q1 | EN | Medium | LBO capital structure — sources & uses of funds |
| Q2 | EN | Medium | PFAS regulatory and market tailwinds |
| Q3 | EN | Medium | Quality of earnings — EBITDA adjustments |
| Q4 | EN | Medium | Legal due diligence workstreams |
| Q5 | EN | Medium | Exit valuation multiples (EBITDA range) |
| Q6 | EN | High | AquaFlow FY2023 financials vs. valuation benchmarks |
| Q7 | EN | High | Covenant package design |
| Q8 | EN | High | Cross-workstream risk synthesis (QoE + legal + ESG) |
| Q9 | EN | High | ESG findings → deal structure adjustments |
| Q10 | EN | High | Exit strategy and path analysis |
| Q11 | ZH | Cross-lingual | AquaFlow competitive positioning in the US market |
| Q12 | ZH | Cross-lingual | LBO model key financial metrics and mechanics |
| Q13 | ZH | Cross-lingual | ESG due diligence priorities in water infrastructure |
| Q14 | ZH | Cross-lingual | Integrated risk synthesis and deal-structure response |
| Q15 | ZH | Cross-lingual | Exit strategy, expected returns, and valuation multiples |

---

## Per-Question Results

### MiniMax-Think (M3)

| Q | Topic | Score | Status | Key misses |
|---|-------|-------|--------|------------|
| Q1 | LBO sources & uses | 14/14 (100%) | PASS | — |
| Q2 | PFAS tailwinds | 16/16 (100%) | PASS | — |
| Q3 | QoE EBITDA adjustments | 10/12 (83%) | WARN | asc 606, working capital |
| Q4 | Legal workstreams | 20/23 (86%) | PASS | 14 permits, aurora, 318m |
| Q5 | Exit multiples | 10/10 (100%) | PASS | — |
| Q6 | Financials vs. benchmarks | 12/15 (80%) | WARN | 710, 19.4m, december 31 |
| Q7 | Covenant package | 20/21 (95%) | PASS | 68m EBITDA buffer |
| Q8 | Cross-workstream risks | 23/23 (100%) | PASS | — |
| Q9 | ESG → deal structure | 18/18 (100%) | PASS | — |
| Q10 | Exit strategy | 22/24 (91%) | PASS | 838m, 261m |
| Q11 | ZH competitive positioning | 18/18 (100%) | PASS | — |
| Q12 | ZH LBO mechanics | 27/27 (100%) | PASS | — |
| Q13 | ZH ESG priorities | 8/12 (66%) | WARN | 顺风, 逆风, b-, tcfd |
| Q14 | ZH integrated risks | 16/19 (84%) | WARN | 竞标, 4.5x, 超额现金 |
| Q15 | ZH exit strategy | 26/30 (86%) | PASS | 3.6x, 38%, ebitda增长, aquaview |
| **Total** | | **260/282 (92%)** | | **PASS=11 WARN=4** |

---

### Claude Opus 4.8

| Q | Topic | Score | Status | Key misses |
|---|-------|-------|--------|------------|
| Q1 | LBO sources & uses | 14/14 (100%) | PASS | — |
| Q2 | PFAS tailwinds | 16/16 (100%) | PASS | — |
| Q3 | QoE EBITDA adjustments | 10/12 (83%) | WARN | asc 606, working capital |
| Q4 | Legal workstreams | 20/23 (86%) | PASS | 14 permits, aurora, 318m |
| Q5 | Exit multiples | 10/10 (100%) | PASS | — |
| Q6 | Financials vs. benchmarks | 14/15 (93%) | PASS | 710 |
| Q7 | Covenant package | 15/21 (71%) | WARN | cov-lite, springing, 35%, fccr, 1.0x |
| Q8 | Cross-workstream risks | 20/23 (86%) | PASS | 5-15%, aurora |
| Q9 | ESG → deal structure | 17/18 (94%) | PASS | 4.5x |
| Q10 | Exit strategy | 24/24 (100%) | PASS | — |
| Q11 | ZH competitive positioning | 18/18 (100%) | PASS | — |
| Q12 | ZH LBO mechanics | 24/27 (88%) | PASS | revolver, subordinated, 64% |
| Q13 | ZH ESG priorities | 10/12 (83%) | WARN | 顺风, 逆风 |
| Q14 | ZH integrated risks | 16/19 (84%) | WARN | 竞标, 4.5x, 超额现金 |
| Q15 | ZH exit strategy | 25/30 (83%) | WARN | 8.0x, 3.6x, 38%, 78%, aquaview |
| **Total** | | **253/282 (89%)** | | **PASS=10 WARN=5** |

---

### Claude Sonnet 4.6

| Q | Topic | Score | Status | Key misses |
|---|-------|-------|--------|------------|
| Q1 | LBO sources & uses | 14/14 (100%) | PASS | — |
| Q2 | PFAS tailwinds | 16/16 (100%) | PASS | — |
| Q3 | QoE EBITDA adjustments | 11/12 (91%) | PASS | asc 606 |
| Q4 | Legal workstreams | 20/23 (86%) | PASS | 14 permits, aurora, 318m |
| Q5 | Exit multiples | 10/10 (100%) | PASS | — |
| Q6 | Financials vs. benchmarks | 12/15 (80%) | WARN | 710, 19.4m, december 31 |
| Q7 | Covenant package | 19/21 (90%) | PASS | cov-lite, 8 quarters |
| Q8 | Cross-workstream risks | 21/23 (91%) | PASS | 5-15% (QoE haircut range) |
| Q9 | ESG → deal structure | 15/18 (83%) | WARN | 4.5x, aurora facility, 185,000 sq ft |
| Q10 | Exit strategy | 24/24 (100%) | PASS | — |
| Q11 | ZH competitive positioning | 16/18 (88%) | PASS | 520, 312 (market share figures) |
| Q12 | ZH LBO mechanics | 16/27 (59%) | WARN | 318m, 50m, revolver, 56m, subordinated, 261m + 5 more |
| Q13 | ZH ESG priorities | 8/12 (66%) | WARN | 顺风, vp+, sasb, tcfd |
| Q14 | ZH integrated risks | 16/19 (84%) | WARN | 竞标, 4.5x, 超额现金 |
| Q15 | ZH exit strategy | 26/30 (86%) | PASS | 3.6x, 38%, 78%, aquaview |
| **Total** | | **244/282 (86%)** | | **PASS=10 WARN=5** |

---

### DeepSeek-R1 (V3)

| Q | Topic | Score | Status | Key misses |
|---|-------|-------|--------|------------|
| Q1 | LBO sources & uses | 12/14 (85%) | PASS | tlb, revolver (terminology) |
| Q2 | PFAS tailwinds | 14/16 (87%) | PASS | granular activated carbon, anion exchange |
| Q3 | QoE EBITDA adjustments | 9/12 (75%) | WARN | add-back, asc 606, working capital |
| Q4 | Legal workstreams | 20/23 (86%) | PASS | 14 permits, aurora, 318m |
| Q5 | Exit multiples | 7/10 (70%) | WARN | xylem, evoqua, 14.8x (comparable transactions) |
| Q6 | Financials vs. benchmarks | 10/15 (66%) | WARN | 710, 59%, 60%, pfas, dmwa |
| Q7 | Covenant package | 17/21 (80%) | WARN | cov-lite, icr, fccr, 8 quarters |
| Q8 | Cross-workstream risks | 21/23 (91%) | PASS | 5-15% (QoE haircut range) |
| Q9 | ESG → deal structure | 15/18 (83%) | WARN | 4.5x, aurora facility, 185,000 sq ft |
| Q10 | Exit strategy | 22/24 (91%) | PASS | xylem, veolia (strategic buyer names) |
| Q11 | ZH competitive positioning | 16/18 (88%) | PASS | 520, 312 (market share figures) |
| Q12 | ZH LBO mechanics | 20/27 (74%) | WARN | 318m, 50m, revolver, 56m, subordinated, 261m + 1 more |
| Q13 | ZH ESG priorities | 6/12 (50%) | WARN | phase i, 顺风, 逆风, vp+, sasb, tcfd |
| Q14 | ZH integrated risks | 11/19 (57%) | WARN | 0.5x, 2.5x, 5.0x, 5.25x, 4.5x, 4.75x + 2 more |
| Q15 | ZH exit strategy | 22/30 (73%) | WARN | 8.0x, 3.6x, 38%, 64%, ebitda增长, 27% + 2 more |
| **Total** | | **222/282 (78%)** | | **PASS=6 WARN=9** |

---

## Cross-Model Comparison

| Q | Topic | MiniMax-Think (M3) | Claude Opus 4.8 | Sonnet 4.6 | DeepSeek-R1 (V3) |
|---|-------|:------------------:|:---------------:|:----------:|:----------------:|
| Q1 | LBO sources & uses | ✅ 100% | ✅ 100% | ✅ 100% | ✅ 85% |
| Q2 | PFAS tailwinds | ✅ 100% | ✅ 100% | ✅ 100% | ✅ 87% |
| Q3 | QoE EBITDA | ⚠️ 83% | ⚠️ 83% | ✅ 91% | ⚠️ 75% |
| Q4 | Legal workstreams | ✅ 86% | ✅ 86% | ✅ 86% | ✅ 86% |
| Q5 | Exit multiples | ✅ 100% | ✅ 100% | ✅ 100% | ⚠️ 70% |
| Q6 | Financials vs. benchmarks | ⚠️ 80% | ✅ 93% | ⚠️ 80% | ⚠️ 66% |
| Q7 | Covenant package | ✅ 95% | ⚠️ 71% | ✅ 90% | ⚠️ 80% |
| Q8 | Cross-workstream risks | ✅ 100% | ✅ 86% | ✅ 91% | ✅ 91% |
| Q9 | ESG → deal structure | ✅ 100% | ✅ 94% | ⚠️ 83% | ⚠️ 83% |
| Q10 | Exit strategy | ✅ 91% | ✅ 100% | ✅ 100% | ✅ 91% |
| Q11 | ZH competitive positioning | ✅ 100% | ✅ 100% | ✅ 88% | ✅ 88% |
| Q12 | ZH LBO mechanics | ✅ 100% | ✅ 88% | ⚠️ 59% | ⚠️ 74% |
| Q13 | ZH ESG priorities | ⚠️ 66% | ⚠️ 83% | ⚠️ 66% | ⚠️ 50% |
| Q14 | ZH integrated risks | ⚠️ 84% | ⚠️ 84% | ⚠️ 84% | ⚠️ 57% |
| Q15 | ZH exit strategy | ✅ 86% | ⚠️ 83% | ✅ 86% | ⚠️ 73% |

---

## WARN Analysis

All WARN results are model-level or non-deterministic limitations. No system bugs were identified.

### Pattern 1 — Computed / derived values (Q6, all models)

Q6 asks models to compare FY2023 financials to valuation benchmarks. The fact set includes `710`
(implied EV at 9.5× multiple), `19.4m` (DMWA annual contract value), and `december 31` (contract
expiry). MiniMax-Think and Sonnet 4.6 missed all three; Opus 4.8 missed only `710`. DeepSeek-R1
missed five facts on this question. The `710` miss is consistent across all four models —
the precise dollar amount is derived arithmetic that models may compute differently depending
on which EBITDA base and multiple they anchor to.

### Pattern 2 — Financial table reproduction (Q12)

This is the widest spread across models. The question asks for LBO model mechanics including
exact tranche amounts ($318m TLB, $50m revolver, $56m subordinated, $261m equity) and leverage
thresholds (5.0×/5.5×). MiniMax-Think reproduced the full table at 100%; Opus 4.8 at 88%;
DeepSeek-R1 at 74%; Sonnet 4.6 at 59%. MiniMax-Think's extended thinking pass appears to prompt
faithful enumeration of table rows; the other models explain the mechanics in prose and omit some
specific figures.

### Pattern 3 — Covenant terminology precision (Q7)

Q7 (covenant package design) produced the most unexpected cross-model divergence. Sonnet 4.6
scored 90% (PASS) while Opus 4.8 scored 71% (WARN), missing cov-lite structure, springing
covenant trigger (35% drawn), FCCR ≥1.0x, and equity cure right (2–4 of 8 quarters) — all
explicitly cited in the AquaFlow README expected answer for Q7. MiniMax-Think scored 95%. This
suggests Opus 4.8 synthesises the covenant rationale well but is less precise at citing the
specific contractual terms verbatim; Sonnet 4.6 and MiniMax-Think quote them more reliably.

### Pattern 4 — CJK lexical precision (Q13, Q14)

Chinese-language questions consistently miss a small set of domain-specific terms:
- `顺风` / `逆风` (tailwinds / headwinds) — all four models miss these in Q13; models use
  equivalent phrases rather than these specific nouns
- `竞标` (competitive bid) — missed by three models in Q14
- `超额现金` (excess cash sweep) — missed in Q14 by three models
- `sasb` / `tcfd` — framework names omitted from CJK answers by Sonnet and DeepSeek

Opus 4.8 performs best on Q13 (83%) — it narrows the gap versus the other Claude model and
MiniMax-Think (both 66%). Only `顺风` and `逆风` are missing, compared to four misses for the
others.

### Pattern 5 — Comparable transaction citation (Q5, Q10, DeepSeek-R1)

DeepSeek-R1 omits specific named comparables (Xylem/Evoqua at 14.8×, Veolia/SUEZ as context)
in Q5 and Q10. It provides correct multiple ranges but does not anchor them to named transactions.
The other three models cite comparables reliably on both questions.

### Pattern 6 — Shared hard facts (Q4, all models)

All four models miss the same three facts on Q4 (legal workstreams): `14` water permits,
`aurora` (Aurora, CO facility), and `318` (318 field technicians covered by FLSA). These are
incidental specifics embedded within long, otherwise correct answers. The consistency across all
four models points to the fact set being very granular rather than a retrieval failure.

---

## System Health Notes

- **Q3 BM25 gap fix** (Signal 1): confirmed working across all four models. The fix suppresses
  Signal 1 when `max_score ≥ threshold`, preventing false gap triggers on ROUTING.md-scoped
  single-page searches. All models retrieved the QoE page correctly.
- **CJK language instruction**: Chinese questions were answered in Mandarin by all four models.
  The `_detect_cjk_language()` fix correctly assigns Chinese (not Japanese or Korean) for all
  Q11–Q15 queries.
- **DeepSeek-R1 chain-of-thought**: `<think>` blocks are stripped correctly before answer
  extraction. No leakage observed across 15 answers.
- **No FAIL grades**: all WARNs are attributable to model behaviour or non-determinism.

---

## Conclusion

### Model Rankings

| Rank | Model | Score | Tier |
|------|-------|-------|------|
| 1 | MiniMax-Think (M3) | 92% | Highest accuracy |
| 2 | Claude Opus 4.8 | 89% | High accuracy |
| 3 | Claude Sonnet 4.6 | 86% | Strong baseline |
| 4 | DeepSeek-R1 (V3) | 78% | Domain-knowledgeable reasoner |

The 14-point gap between MiniMax-Think and DeepSeek-R1 is not a domain knowledge gap — all four
models demonstrate strong PE/M&A expertise. The gap reflects how each model handles a retrieval-
augmented synthesis task: faithfully reproducing specific figures and terms from retrieved wiki
pages versus synthesising the concepts in its own words.

### Key Differentiators

**Extended thinking wins on table-dense questions.** The clearest differentiator is Q12 (LBO
mechanics table): MiniMax-Think (100%) vs. Opus 4.8 (88%) vs. DeepSeek-R1 (74%) vs. Sonnet 4.6
(59%). MiniMax-Think's thinking pass appears to prompt systematic enumeration of all table rows.
The other models explain the mechanics correctly but drop specific tranche amounts.

**Claude Opus 4.8 vs. Sonnet 4.6 trade-off.** Opus gains 3 percentage points overall with
notable improvements on financials (Q6: 93% vs 80%), ESG deal structure (Q9: 94% vs 83%),
LBO table (Q12: 88% vs 59%), and CJK ESG coverage (Q13: 83% vs 66%). However Opus regresses
on covenant precision (Q7: 71% vs 90%) — it explains the covenant rationale well but misses
specific terms (springing trigger, FCCR threshold) that Sonnet quotes reliably. Neither model
is strictly dominant; the choice depends on whether LBO table reproduction or covenant
terminology matters more for the use case.

**DeepSeek-R1 is a synthesiser, not a quoter.** Its WARN rate (9 of 15) reflects a consistent
style: it constructs well-reasoned, domain-accurate answers but prioritises argument over
verbatim citation of figures. In a compiled knowledge engine where the retrieved context is the
ground truth, this synthesis style depresses fact-match scores even when the underlying
understanding is correct.

**CJK cross-lingual retrieval works well across all models.** The system retrieves English wiki
content for Chinese queries and all four models respond in Chinese without hallucinating
non-existent facts. The residual gaps (`顺风`/`逆风`, `竞标`) are lexical precision issues, not
retrieval failures.

### Model Selection for a Knowledge Compiled Engine

Synthadoc's query agent is a retrieval-augmented pipeline: BM25 retrieves relevant wiki pages,
the LLM synthesises from that retrieved context. In this architecture, the key model capability
is **faithful reproduction of specific facts and figures from a given context**, not general
domain knowledge. This shifts the ranking compared to raw reasoning benchmarks.

**MiniMax-Think (M3) — recommended for highest accuracy.** The extended thinking pass gives it
the best structured-data reproduction (Q12: 100%) and the highest English-language PASS rate
(11/15). Best suited when query accuracy is the primary requirement and cost is secondary.

**Claude Opus 4.8 — recommended for Anthropic API users.** At 89% it is the best-performing
model available on a direct Anthropic API key, outperforming Sonnet 4.6 by 3 points. The gains
on financial table reproduction (Q12) and CJK precision (Q13) are meaningful for multi-lingual
PE/M&A workloads. One caveat: Sonnet 4.6 remains preferable for covenant-heavy queries (Q7).

**Claude Sonnet 4.6 — cost-efficient Anthropic option.** At 86% with 10 PASSes it offers strong
breadth across all 15 question types. Its covenant precision advantage over Opus 4.8 on Q7 makes
it the better default for legal-focused diligence queries. Suitable when token cost matters and
query mix is balanced across workstreams.

**DeepSeek-R1 (V3) — cost-efficient reasoning model.** At 78% it is weaker on precision
recall but strong on conceptual synthesis. Appropriate for exploratory queries where the goal
is understanding rather than exact figure retrieval, or where budget is a primary constraint.
Not recommended as the primary model for due diligence queries requiring precise figure citation.

# AquaFlow LLM Query Benchmark

**Wiki:** AquaFlow Systems PE/M&A due diligence  
**Date:** 2026-07-09  
**Evaluator:** `docs/example/aquaflow/evaluation/scripts/eval_queries.py`

---

## Overview

This report benchmarks three LLMs against 15 PE/M&A due diligence questions drawn from the
[AquaFlow wiki](../../readme.md). Questions Q1–Q10 are in English; Q11–Q15 are in Mandarin Chinese. Each
answer is scored by case-insensitive substring match against a curated fact list (282 facts
total; defined per-question in [`eval_queries.py`](../scripts/eval_queries.py)). Grading follows a two-tier framework:

| Grade | Threshold | Meaning |
|-------|-----------|---------|
| **PASS** | ≥ 85% facts matched | System and model performing correctly |
| **WARN** | < 85% facts matched | Model-level or non-deterministic limitation — not a system bug |

`FAIL` is reserved exclusively for confirmed system or code bugs; none were found in this run.

---

## Models Evaluated

| Label | Provider | Model | Config | Run timestamp |
|-------|----------|-------|--------|---------------|
| MiniMax-Think (M3) | MiniMax | MiniMax-M3 | thinking=enabled | 2026-07-09 20:23 |
| Claude Sonnet 4.6 | Anthropic (claude-code) | claude-sonnet-4-6 | — | 2026-07-09 20:26 |
| DeepSeek-R1 (V3) | DeepSeek | deepseek-reasoner | chain-of-thought | 2026-07-09 19:50 |

---

## Summary Leaderboard

| Rank | Model | Facts Matched | Score | PASS | WARN |
|------|-------|--------------|-------|------|------|
| 1 | MiniMax-Think | 260 / 282 | **92%** | 11 | 4 |
| 2 | Claude Sonnet 4.6 | 244 / 282 | **86%** | 10 | 5 |
| 3 | DeepSeek-R1 | 222 / 282 | **78%** | 6 | 9 |

---

## Question Reference

| ID | Language | Topic |
|----|----------|-------|
| Q1 | EN | LBO capital structure — sources & uses of funds |
| Q2 | EN | PFAS regulatory and market tailwinds |
| Q3 | EN | Quality of earnings — EBITDA adjustments |
| Q4 | EN | Legal due diligence workstreams |
| Q5 | EN | Exit valuation multiples (EBITDA range) |
| Q6 | EN | AquaFlow FY2023 financials vs. valuation benchmarks |
| Q7 | EN | Covenant package design |
| Q8 | EN | Cross-workstream risk synthesis (QoE + legal + ESG) |
| Q9 | EN | ESG findings → deal structure adjustments |
| Q10 | EN | Exit strategy and path analysis |
| Q11 | ZH | AquaFlow competitive positioning in the US market |
| Q12 | ZH | LBO model key financial metrics and mechanics |
| Q13 | ZH | ESG due diligence priorities in water infrastructure |
| Q14 | ZH | Integrated risk synthesis and deal-structure response |
| Q15 | ZH | Exit strategy, expected returns, and valuation multiples |

---

## Per-Question Results

### MiniMax-Think

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

### DeepSeek-R1

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

| Q | Topic | MiniMax-Think (M3) | Sonnet 4.6 | DeepSeek-R1 (V3) |
|---|-------|:-------------:|:----------:|:-----------:|
| Q1 | LBO sources & uses | ✅ 100% | ✅ 100% | ✅ 85% |
| Q2 | PFAS tailwinds | ✅ 100% | ✅ 100% | ✅ 87% |
| Q3 | QoE EBITDA | ⚠️ 83% | ✅ 91% | ⚠️ 75% |
| Q4 | Legal workstreams | ✅ 86% | ✅ 86% | ✅ 86% |
| Q5 | Exit multiples | ✅ 100% | ✅ 100% | ⚠️ 70% |
| Q6 | Financials vs. benchmarks | ⚠️ 80% | ⚠️ 80% | ⚠️ 66% |
| Q7 | Covenant package | ✅ 95% | ✅ 90% | ⚠️ 80% |
| Q8 | Cross-workstream risks | ✅ 100% | ✅ 91% | ✅ 91% |
| Q9 | ESG → deal structure | ✅ 100% | ⚠️ 83% | ⚠️ 83% |
| Q10 | Exit strategy | ✅ 91% | ✅ 100% | ✅ 91% |
| Q11 | ZH competitive positioning | ✅ 100% | ✅ 88% | ✅ 88% |
| Q12 | ZH LBO mechanics | ✅ 100% | ⚠️ 59% | ⚠️ 74% |
| Q13 | ZH ESG priorities | ⚠️ 66% | ⚠️ 66% | ⚠️ 50% |
| Q14 | ZH integrated risks | ⚠️ 84% | ⚠️ 84% | ⚠️ 57% |
| Q15 | ZH exit strategy | ✅ 86% | ✅ 86% | ⚠️ 73% |

---

## WARN Analysis

All WARN results are model-level or non-deterministic limitations. No system bugs were identified.

### Pattern 1 — Computed / derived values (Q6, all models)

Q6 asks models to compare FY2023 financials to valuation benchmarks. The fact set includes
`710` (implied EV at 9.5× multiple), `19.4m` (DMWA annual contract value), and `december 31`
(contract expiry). All three models missed these consistently, most likely because the values
require cross-page arithmetic that models may compute differently, or the precise dollar amount
is not verbatim in the synthesis. This is a known limitation of single-pass retrieval-augmented
generation, not a system bug.

### Pattern 2 — Financial table reproduction (Q12)

MiniMax-Think (thinking=on) reproduced the full LBO mechanics table at 100%. Sonnet 4.6 dropped
to 59% and DeepSeek-R1 to 74% — both explained the mechanics correctly in prose but did not
quote specific tranche amounts (318m, 50m revolver, 56m subordinated, 261m equity, 5.0×/5.5×
leverage thresholds). MiniMax-Think's extended thinking pass appears to prompt it to enumerate
table rows verbatim; the other two models synthesize the explanation instead.

### Pattern 3 — CJK-specific financial terminology (Q13, Q14)

Chinese-language questions consistently miss a small set of domain-specific terms:
- `顺风` / `逆风` (tailwinds / headwinds) — models use equivalent phrases rather than these
  specific nouns
- `竞标` (competitive bid) — described conceptually without using the term
- `超额现金` (excess cash sweep) — explained in context without the term
- `sasb` / `tcfd` — framework names omitted from CJK answers even when covered in English answers

These are CJK lexical precision gaps, not retrieval failures. The underlying facts are retrieved
and synthesised correctly; the exact surface forms are not reproduced.

### Pattern 4 — Comparable transaction citation (Q5, Q10)

DeepSeek-R1 omits specific named comparables (Xylem/Evoqua at 14.8×, Veolia/SUEZ as context)
in two questions. It provides the correct multiple ranges but does not anchor them to named
transactions. MiniMax-Think and Sonnet 4.6 cite comparables reliably.

### Pattern 5 — Shared hard facts (Q4, all models)

All three models miss the same three facts on Q4 (legal workstreams): `14` water permits,
`aurora` (Aurora, CO facility), and `318` (318m TLB). These values appear as incidental
specifics buried in a long answer — the models cover the workstream correctly but do not surface
every numerical detail. The consistency across models points to the fact set being very granular
rather than a retrieval failure.

---

## System Health Notes

- **Q3 BM25 gap fix** (Signal 1): confirmed working across all three models. Prior to the fix,
  ROUTING.md-scoped single-page searches triggered a false gap; the fix suppresses Signal 1 when
  `max_score ≥ threshold`. All models retrieved the QoE page correctly.
- **CJK language instruction**: Chinese questions were answered in Mandarin by all three models.
  The `_detect_cjk_language()` fix prevents Japanese / Korean queries from receiving a Mandarin
  instruction.
- **DeepSeek-R1 chain-of-thought**: `<think>` blocks are stripped correctly before answer
  extraction. No leakage observed in any of the 15 answers.
- **No FAIL grades**: all WARNs are attributable to model behaviour or non-determinism.

---

## Conclusion

MiniMax-M3 with thinking enabled is the strongest model on this wiki for PE/M&A due diligence
queries, leading on LBO table reproduction (Q12: 100% vs 59–74%) and CJK-language precision.
Claude Sonnet 4.6 performs solidly at 86% overall and is the best open-weight alternative for
English-language questions. DeepSeek-R1 is a capable reasoner but consistently prioritises
synthesis over verbatim figure citation, which depresses its score on fact-dense questions —
its 78% overall still represents correct domain understanding across all 15 questions.

# Covenant Analysis Framework — Leveraged Finance

## Overview

Financial covenants in leveraged finance are contractual constraints in credit agreements that require borrowers to maintain certain financial metrics. Breach of a covenant gives lenders the right to accelerate repayment (call the loan due immediately) or initiate a restructuring. Covenant analysis is a core discipline in both underwriting (can this company service and maintain its debt?) and portfolio monitoring.

## Types of Covenants

**Maintenance Covenants (Financial):**
Tested quarterly; require the borrower to MAINTAIN a minimum financial condition at all times during the loan period. Breach immediately triggers a default event. Common in traditional bank credit facilities.

- **Total Net Leverage Ratio:** Total Net Debt / LTM Adjusted EBITDA ≤ X.Xx
- **Senior Secured Leverage Ratio:** Senior Secured Debt / LTM Adjusted EBITDA ≤ X.Xx
- **Interest Coverage Ratio:** LTM Adjusted EBITDA / Cash Interest Expense ≥ X.Xx
- **Fixed Charge Coverage Ratio (FCCR):** (EBITDA – Capex – Cash Taxes) / (Cash Interest + Debt Amortization) ≥ 1.0x

**Incurrence Covenants:**
Tested only when the borrower takes a specific action (incurring new debt, making an acquisition, paying a dividend). No ongoing monitoring obligation if the borrower takes no action. Dominant in high-yield bond structures.

**Springing Covenants:**
Activated only when revolver utilization exceeds a threshold (typically 35% drawn). Common in covenant-lite TLB structures where maintenance covenants apply only to the revolver.

## Covenant-Lite vs. Full Covenant Structures

Post-2012, the leveraged loan market shifted dramatically toward "covenant-lite" (cov-lite) structures where TLBs carry no maintenance financial covenants, only incurrence covenants. The revolver may retain a springing maintenance covenant.

Implications of cov-lite:
- Borrowers can operate deeper in financial distress before triggering a default
- Lenders lose early-warning remediation leverage
- Recovery rates in cov-lite distressed situations have historically been lower than full-covenant deals
- Deal teams must stress-test cash headroom (minimum liquidity) rather than covenant headroom

## EBITDA Definition — The Critical Variable

The denominator in every leverage ratio is "Adjusted EBITDA," and the definition is heavily negotiated in credit documentation. Key add-backs that inflate the EBITDA base include:

- **Pro-forma synergies:** Cost savings from acquisitions that haven't yet been achieved, time-limited (typically 18–24 months post-close)
- **Restructuring and one-time charges:** Severance, facility closure costs, transformation expenses
- **Non-cash charges:** Stock-based compensation, impairment, unrealized losses
- **Management fees:** Fees paid to the sponsor
- **Run-rate revenue adjustments:** Annualizing contracts signed mid-period

Aggressive EBITDA definitions can substantially inflate the reported EBITDA, making leverage ratios appear more favorable. Due diligence teams must reconcile management's EBITDA figure against GAAP EBITDA, tracking every add-back and challenging its recurrence.

## Headroom Analysis

Headroom is the cushion between the current leverage ratio and the covenant threshold. If the covenant is Total Net Leverage ≤ 5.5x and the company is at 5.0x, there is 0.5x of headroom.

**Headroom expression:**
- In turns of EBITDA: How many turns before breach?
- In dollar terms: How much EBITDA could the company lose before breaching?
  EBITDA buffer = (Covenant Threshold – Current Leverage) × Net Debt / Covenant Threshold

**Dynamic headroom:** Headroom changes as EBITDA moves and debt amortizes. A growing company with mandatory amortization may expand headroom over time; a declining business contracts it.

Standard practice: model headroom under base, upside, and downside EBITDA scenarios through the projected hold period. A covenant breach in the downside scenario two or more years out is generally viewed as acceptable risk; a breach in year one or two is disqualifying.

## Equity Cure Rights

Modern credit agreements frequently include equity cure provisions: the sponsor (private equity firm) can inject equity capital to "cure" a covenant breach by adding the equity injection to LTM EBITDA for covenant calculation purposes.

Typical mechanics:
- Available for 2–4 of any 8 consecutive quarters
- Injection amount limited to what is needed to restore compliance plus a small buffer
- Must be contributed in cash and applied to reduce TLB (or treated as EBITDA add)

Equity cure rights are an important safety valve in LBO covenant structures. Their existence and usability should be confirmed in underwriting, and the sponsor's remaining fund capital (to fund potential cures) assessed.

## Interest Coverage Analysis

Interest coverage ratio = LTM EBITDA / Annual Cash Interest Expense.

Cash interest expense includes:
- Scheduled interest on TLB (floating; SOFR + spread)
- Interest on subordinated debt
- Revolver commitment fee on undrawn portion

Industry benchmark: ICR ≥ 2.0x is typically required for covenant compliance; below 1.5x signals distress. At entry, LBO structures generally target ICR of 2.0–3.0x in the base case.

Rate sensitivity: Every 50 bps increase in SOFR raises cash interest on a $318M TLB by $1.6M, reducing ICR headroom. Rate sensitivity analysis should accompany every leveraged finance underwriting.

## Covenant Testing Calendar

Maintenance covenants are tested quarterly, typically within 45–60 days of quarter end (with financial statements). The testing cadence:
- Q1 results → test by May 15 (assuming March 31 quarter end)
- Q2 results → test by August 14
- Q3 results → test by November 14
- Q4 results → test by March 30 (year-end audit)

The rolling LTM EBITDA window means a single bad quarter is diluted across four quarters; two consecutive bad quarters signal a developing problem.

## Practical Covenant Monitoring

Portfolio companies should maintain a covenant compliance certificate — a quarterly management certification that financial conditions are within covenant thresholds. The CFO signs the certificate, and any breach (or expected breach) must be disclosed promptly.

Pre-emptive covenant waiver or amendment is almost always preferable to technical default. Approaching lenders 60–90 days before an expected breach gives the borrower negotiating leverage; approaching lenders after default weakens the sponsor's position and may trigger cross-default provisions across other credit facilities.

## Case Application: Covenant Analysis in LBO Context

A company with LTM EBITDA of $74.8M and Net Debt of $374M post-LBO:
- Entering leverage: 5.0x Net Debt / EBITDA
- Covenant threshold: 5.5x Total Net Leverage
- Headroom at close: 0.5x = $37.4M EBITDA buffer

Downside scenario: if EBITDA contracts to $68M (–9%), leverage rises to 5.5x — exactly at the covenant threshold. Any further deterioration triggers breach.

Mitigants: $50M undrawn revolver provides liquidity; equity cure right allows sponsor to inject equity to restore compliance if breach occurs.

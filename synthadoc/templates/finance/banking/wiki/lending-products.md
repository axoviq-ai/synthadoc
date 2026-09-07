---
title: Lending Products
status: draft
confidence: low
type: concept
sources: []
---

# Lending Products

Index of all lending products offered. Populate by ingesting product sheets from `raw_sources/products/`.

Each lending product page captures:

- **Product identity** — name, product code, target customer (personal / business), approval date
- **Loan terms** — amount range, term, interest rate type (fixed / ARM / variable), current rate and APR range
- **Underwriting standards** — maximum LTV, minimum credit score, maximum DTI (front-end / back-end), income documentation, collateral and guaranty requirements
- **Fees** — origination fee, prepayment penalty, late fee, annual fee
- **Regulatory applicability** — TILA/Reg Z, RESPA, HMDA, CRA classification, SBA program designation
- **Disclosure forms** — Loan Estimate, Closing Disclosure, HELOC disclosure, Truth in Lending statement

**How to add a lending product:**

1. Copy `raw_sources/products/template-product-sheet.md` and rename it after the product
2. Complete the Lending Product Terms section
3. Run `synthadoc ingest raw_sources/products/<product>.md -w <wiki>`
4. Re-ingest whenever rates, fees, or terms change

Cross-link to [[deposit-products]], [[credit-risk]], and [[regulatory-compliance]].

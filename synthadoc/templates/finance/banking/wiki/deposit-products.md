---
title: Deposit Products
status: draft
confidence: low
type: concept
sources: []
---

# Deposit Products

Specifications for each deposit account type. Populate by ingesting product disclosure documents and Truth in Savings disclosures from `raw_sources/products/`.

Each deposit product page captures:

- **Product identity** — account name, product code, target customer (personal / business), account type (DDA / savings / MMA / CD / IRA)
- **Interest and APY** — current APY, interest calculation method (daily balance / average daily balance), payment frequency, minimum balance to earn interest
- **Fee schedule** — monthly maintenance fee, minimum balance waiver threshold, excess transaction fee (Reg D), overdraft and NSF fees, wire transfer fees
- **FDIC insurance** — coverage category and amount ($250,000 standard; tagged by ownership category)
- **Regulatory applicability** — Reg DD (Truth in Savings disclosure), Reg E (electronic fund transfer coverage for DDA), Reg D (transaction limits for savings/MMA — note: the Fed suspended the 6-transaction limit in 2020 but many banks retain it)
- **Product features** — overdraft protection link, debit card eligibility, ATM network access, mobile deposit limits, online banking features

**How to add a deposit product:**

1. Copy `raw_sources/products/template-product-sheet.md` and rename it after the product
2. Complete the Deposit Product section
3. Run `synthadoc ingest raw_sources/products/<product>.md -w <wiki>`

Cross-link to [[credit-risk]], [[lending-products]], [[regulatory-compliance]], and [[bsa-aml]].

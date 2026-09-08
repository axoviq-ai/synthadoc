# Property Intake: [Address or Alias]

> **How to use this form**
>
> 1. Copy this file and rename it after your property (e.g. `oak-street-house.md`)
> 2. Fill in every field — leave a field blank or write `N/A` if it does not apply
> 3. Run: `synthadoc ingest raw_sources/properties/oak-street-house.md -w <wiki>`
>
> Fields labelled *(calculated)* can be derived — fill them in or leave blank
> and query the wiki to compute them later.
>
> Standard references: Fannie Mae URAR (Form 1004) for physical description;
> NCREIF / standard CRE practice for investment metrics (NOI, cap rate, GRM,
> cash-on-cash, DSCR).

---

## Property Summary

- **Alias:** (short name used in this wiki, e.g. "Oak Street House")
- **Type:** (SFH Detached / Condo / Townhouse / Duplex / Small Multifamily ≤4 units)
- **Street Address:**
- **City / State / ZIP:**
- **Submarket / Neighbourhood:**
- **Year Built:**
- **Gross Living Area:** sqft
- **Lot Size:** sqft — (N/A for condo)
- **Bedrooms / Full Baths / Half Baths:** / /
- **Condition:** (Excellent / Good / Average / Fair / Poor)
- **HOA Name:** (N/A for SFH)
- **HOA Monthly Fee:** $ — (N/A for SFH)
- **HOA Includes:** (e.g. water, exterior maintenance, master insurance — N/A for SFH)

---

## Acquisition

- **Purchase Price:** $
- **Purchase Date:** YYYY-MM-DD
- **Closing Costs:** $
- **Total Acquisition Cost:** $ *(calculated: purchase price + closing costs)*

---

## Financing

- **Loan Amount:** $
- **LTV Ratio:** % *(calculated: loan ÷ purchase price)*
- **Loan Type:** (Conventional / FHA / VA / Non-QM / Cash)
- **Interest Rate:** % — (Fixed 30-yr / Fixed 15-yr / ARM — specify)
- **Monthly Principal & Interest (P&I):** $
- **Monthly PITI (P&I + tax escrow + insurance escrow):** $
- **Cash Invested:** $ *(calculated: down payment + closing costs)*

---

## Income

- **Current Monthly Rent:** $
- **Market Rent (est.):** $ /month — (source: Zillow / Rentometer / agent comp)
- **Occupancy Status:** (Occupied / Vacant)
- **Lease Start Date:** YYYY-MM-DD
- **Lease Expiry:** YYYY-MM-DD
- **Vacancy Allowance:** % — (typically 5–8% for residential)

---

## Annual Operating Expenses

- **Property Tax:** $
- **Homeowner's Insurance:** $
- **HOA Fees (annual):** $ — (N/A for SFH)
- **Property Management:** $ — (typically 8–12% of gross rent; $0 if self-managed)
- **Maintenance Reserve:** $ — (typically 0.5–1% of property value/year)
- **CapEx Reserve:** $ — (typically 0.5% of property value/year)
- **Other Expenses:** $ — (describe:                    )
- **Total Annual Operating Expenses:** $ *(calculated: sum of above)*

---

## Performance Metrics

*(All calculated — fill in or leave blank to derive via query)*

- **Gross Annual Rent (GAR):** $ — (monthly rent × 12)
- **Effective Gross Income (EGI):** $ — (GAR × (1 − vacancy %))
- **Net Operating Income (NOI):** $ — (EGI − total operating expenses)
- **Cap Rate:** % — (NOI ÷ purchase price × 100)
- **Gross Rent Multiplier (GRM):** × — (purchase price ÷ GAR)
- **Annual Debt Service:** $ — (monthly P&I × 12)
- **Pre-Tax Cash Flow:** $ — (NOI − annual debt service; negative = cash-flow negative)
- **Cash-on-Cash Return:** % — (pre-tax cash flow ÷ cash invested × 100)
- **Debt Service Coverage Ratio (DSCR):** — (NOI ÷ annual debt service; <1.0 = cash-flow negative)

---

## Current Valuation

- **Estimated Current Value:** $
- **Valuation Source:** (Zillow / Redfin / Formal Appraisal / Agent CMA / Other)
- **Valuation Date:** YYYY-MM-DD
- **Unrealized Gain / Loss:** $ *(calculated: estimated value − total acquisition cost)*
- **Unrealized Return:** % *(calculated: unrealized gain ÷ total acquisition cost × 100)*

---

## Investment Thesis

- **Why Acquired:**
- **Target Hold Period:** years
- **Exit Strategy:** (Sale / 1031 Exchange / Cash-out Refinance / Long-term Hold / Bequest)
- **Value-Add Opportunities:**
- **Key Risks:**
- **Notes:**

---
title: Freedom to Operate
status: draft
confidence: low
type: concept
sources: []
---

# Freedom to Operate

FTO analysis records assessing whether a product or process infringes active third-party patents. Each FTO record captures:

- **Analysis identity** — FTO reference number, product or feature analyzed, date of analysis, counsel who performed the search and opinion
- **Technology area** — the technical function or feature examined
- **Search scope** — patent databases searched (USPTO, EPO, WIPO, others); keyword and classification codes used
- **Key references found** — third-party patents identified as potentially relevant, with status (active / expired / pending)
- **Claim analysis** — for each potentially blocking patent, an element-by-element analysis of the claims against the product; conclusion (reads on / does not read on / uncertain)
- **Overall opinion** — FTO conclusion: Clear / Risk identified / Unable to determine; explanation
- **Recommended actions** — design-around options, licensing approach, or invalidity arguments if risk is identified
- **Reliance limitations** — scope of the opinion; what the FTO does not cover; when a refreshed opinion is recommended

**How to populate:**

1. Ingest FTO opinion letters from outside IP counsel:
   ```
   synthadoc ingest docs/ip/fto/ --batch -w <wiki>
   ```
2. Ingest individual FTO opinion for a new product:
   ```
   synthadoc ingest docs/ip/fto/<product>-fto-<year>.pdf -w <wiki>
   ```

Cross-link to [[patent-portfolio]] for our own patents relevant to the analysis, [[ip-strategy]] for FTO policy, and [[patent-prosecution]] if any identified risk patents are being challenged.

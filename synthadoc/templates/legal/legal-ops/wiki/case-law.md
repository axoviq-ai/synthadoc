---
title: Case Law
status: draft
confidence: low
type: concept
sources: []
---

# Case Law

Annotated library of judicial decisions and regulatory rulings relevant to the organization's legal practice areas. Each case brief records:

- **Citation** — full citation (court, year, reporter), docket number, jurisdiction
- **Court** — level (trial / appellate / supreme) and circuit or division
- **Decision date**: 
- **Holding** — the court's ruling in one or two sentences; what question of law it resolves
- **Key reasoning** — the legal test or standard the court applied; key factors in the analysis
- **Relevance to our matters** — how this ruling applies to active or potential matters (link to [[matters]] or [[litigation]])
- **Subsequent history** — whether the case was affirmed, reversed, or distinguished; string citation
- **Practice area tags** — contract, employment, IP, regulatory, product liability, etc.

**How to populate:**

1. Ingest decisions directly from Westlaw / Lexis exports or court websites:
   ```
   synthadoc ingest docs/legal/caselaw/<citation>.pdf -w <wiki>
   ```
2. Ingest a landmark decision directly from a court website:
   ```
   synthadoc ingest "https://www.supremecourt.gov/opinions/slipopinion/<term>/<docket>" -w <wiki>
   ```
3. For Cornell LII summaries:
   ```
   synthadoc ingest "https://www.law.cornell.edu/supremecourt/text/<year>/<number>" -w <wiki>
   ```

Cross-link to [[litigation]] for cases directly bearing on active disputes and [[regulatory-guidance]] for agency interpretations.

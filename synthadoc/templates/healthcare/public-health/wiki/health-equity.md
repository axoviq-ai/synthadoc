---
title: Health Equity
status: draft
confidence: low
type: concept
sources: []
---

# Health Equity

Documentation of health disparities and equity-focused analyses. Each equity record captures:

- **Health issue** — the condition or outcome where disparities are documented (link to [[disease-burden]])
- **Disparity population** — the demographic group experiencing worse outcomes (race/ethnicity, income, geography, insurance status, language, disability status, gender identity)
- **Disparity magnitude** — quantified gap (rate ratio, risk difference, mortality gap, screening rate gap); source and year
- **Social determinants involved** — the SDOH factors that drive or mediate the disparity (housing, food security, education, employment, neighborhood environment, healthcare access)
- **Contributing health system factors** — access barriers (insurance, transportation, language), implicit bias, care quality differences
- **Evidence-based interventions** — what the Community Preventive Services Task Force or WHO recommends to address this disparity (link to [[public-health-interventions]])
- **Equity metrics tracked locally** — what our program or organization measures to track progress on reducing the gap

**How to populate:**

1. Ingest CDC health disparities data:
   ```
   synthadoc ingest "https://www.cdc.gov/healthequity/index.htm" -w <wiki>
   ```
2. Ingest Healthy People 2030 health equity framework:
   ```
   synthadoc ingest "https://health.gov/healthypeople/priority-areas/health-equity" -w <wiki>
   ```
3. Ingest local community health needs assessment:
   ```
   synthadoc ingest docs/public-health/chna-<year>.pdf -w <wiki>
   ```

Cross-link to [[disease-burden]] for burden data by population, [[surveillance]] for tracking systems, and [[health-programs]] for equity-focused interventions.

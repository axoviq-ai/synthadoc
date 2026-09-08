---
title: Control Plans
status: draft
confidence: low
type: concept
sources: []
---

# Control Plans

Manufacturing control plans documenting how critical-to-quality (CTQ) characteristics are controlled at each process step. Each control plan captures:

- **Control plan identity** — document number, revision level, effective date, part number and name, production stage (prototype / pre-launch / production)
- **Process step** — the manufacturing operation (machining, assembly, welding, heat treat, final inspection, etc.)
- **Product characteristic** — the CTQ or critical product characteristic being controlled at this step; drawing dimension or specification reference
- **Process characteristic** — the critical input variable (temperature, feed rate, torque, pressure) that controls the product characteristic
- **Specification** — nominal value, upper and lower tolerance limits; units
- **Control method** — how the characteristic is controlled (SPC, attribute inspection, process parameter monitoring, 100% inspection, CPK maintenance)
- **Reaction plan** — what the operator does if the characteristic is out of control: stop production, quarantine parts, call supervisor, initiate NCR (link to [[nonconformances]])
- **Sample size and frequency** — how many parts are measured and how often

**How to populate:**

1. Ingest AIAG-format control plan spreadsheets:
   ```
   synthadoc ingest docs/manufacturing/control-plans/ --batch -w <wiki>
   ```
2. Ingest AIAG FMEA and control plan reference manual:
   ```
   synthadoc ingest "https://www.knowllence.com/en/blog-design-manufacturing/control-plan-apqp.html" -w <wiki>
   ```

Cross-link to [[process-specifications]] for the process parameters, [[inspection-procedures]] for the inspection methods, [[gauges]] for the measurement equipment, and [[nonconformances]] for the reaction plan escalation path.

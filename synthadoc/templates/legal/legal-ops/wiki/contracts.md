---
title: Contracts
status: draft
confidence: low
type: concept
sources: []
---

# Contracts

Repository of executed contracts. Each contract page records:

- **Agreement identity** — contract title, agreement type (MSA, SOW, NDA, lease, license, amendment), unique contract ID or reference number
- **Parties** — full legal names of each party; notice addresses
- **Term** — effective date, expiry date, auto-renewal clause and notice period required to terminate
- **Key obligations** — what each party is required to do; performance standards or SLAs
- **Payment terms** — price, invoicing cadence, payment period, late-payment interest, pricing adjustment mechanism
- **Governing law & dispute resolution** — jurisdiction, governing law, escalation path (negotiation → mediation → arbitration / litigation)
- **Change-of-control provisions** — assignment rights; whether the agreement terminates or requires consent on a change of control
- **Renewal & expiry flags** — flag any contract with a renewal deadline within 90 days

**How to populate:**

1. Ingest contract PDFs directly:
   ```
   synthadoc ingest docs/contracts/<contract-name>.pdf -w <wiki>
   ```
2. For a folder of contracts:
   ```
   synthadoc ingest docs/contracts/ --batch -w <wiki>
   ```

Cross-link to [[matters]] for the associated legal matter, [[outside-counsel]] for the managing firm, and [[contract-templates]] for the master form used.

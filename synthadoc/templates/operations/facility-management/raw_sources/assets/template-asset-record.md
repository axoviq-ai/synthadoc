---
# Copyright (c) 2026 William Johnason / axoviq.com. All rights reserved.
---
# Asset Record — Template

Use this form to document a facility asset. Copy this file, rename it
`<asset-id>-<short-name>.md` (e.g. `HVAC-042-rooftop-unit-3.md`), complete
all fields, then ingest:

    synthadoc ingest raw_sources/assets/<asset-id>-<short-name>.md -w <wiki>

---

## Asset Identity

- **Asset ID**: 
- **Asset name / description**: 
- **Asset type**: _(HVAC / Electrical / Plumbing / Fire Suppression / Elevator / Lighting / Security / Production Equipment / IT Infrastructure / Other)_
- **Building**: 
- **Floor / Area / Room**: 
- **Asset tag / barcode**: 

## Specifications

- **Manufacturer**: 
- **Model number**: 
- **Serial number**: 
- **Capacity / rating**: _(e.g. 10-ton, 200A, 5HP)_

## Lifecycle

- **Installation date**: 
- **Warranty expiry**: 
- **Expected useful life**: _(years)_
- **Replacement cost** (estimated): $
- **Current condition**: _(Excellent / Good / Fair / Poor / Critical)_

## Maintenance

- **PM schedule**: _(Monthly / Quarterly / Annual — or "See CMMS")_
- **Last PM date**: 
- **Next PM due**: 
- **Maintenance vendor / contract**: 
- **CMMS asset ID**: 

## Regulatory & Compliance

- **Permit / inspection required**: Yes / No
- **Last inspection date**: 
- **Next inspection due**: 
- **Applicable regulation or code**: 

## Notes

_(Known issues, failure history, upgrade plans, parts stocked.)_

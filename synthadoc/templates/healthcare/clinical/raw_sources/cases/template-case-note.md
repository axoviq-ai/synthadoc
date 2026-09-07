---
# Copyright (c) 2026 William Johnason / axoviq.com. All rights reserved.
---
# Clinical Case Note — Template

Use this form to document a de-identified clinical case for educational or
reference purposes. Copy this file, rename it `<case-id>-<keyword>.md`,
complete all fields, then ingest:

    synthadoc ingest raw_sources/cases/<case-id>-<keyword>.md -w <wiki>

**Privacy:** Remove all direct identifiers before ingest. Do not record name,
date of birth, MRN, SSN, full ZIP code, or any 18 HIPAA identifiers.

---

## Case Identity

- **Case ID**: `CASE-YYYY-NNN`
- **Setting**: _(Inpatient / Outpatient / Emergency / ICU / Other)_
- **Specialty**: 
- **Date (approximate — year/month is sufficient)**: 

## Chief Complaint

_(Patient's presenting complaint in their own words, or clinical framing if documenting for teaching purposes.)_

## History of Present Illness

_(Duration, onset, character, associated symptoms, modifying factors, relevant prior episodes.)_

## Relevant Medical / Surgical History

_(Pertinent past diagnoses, surgeries, hospitalizations — not an exhaustive list.)_

## Medications at Presentation

| Medication | Dose | Frequency | Route |
|------------|------|-----------|-------|
| | | | |

## Allergies

_(Drug allergies with reaction type; NKDA if none.)_

## Key Examination Findings

_(Vital signs, relevant physical exam findings — focus on what was abnormal or diagnostic.)_

## Diagnostic Results

| Test | Result | Reference / Normal |
|------|--------|--------------------|
| | | |
| | | |

## Working Diagnoses

1. _(Primary diagnosis with ICD-10 code if known)_
2. _(Secondary / differential)_

## Treatment Course

_(Key interventions: medications started, procedures performed, consultations, monitoring plan.)_

## Outcome

_(Clinical response, disposition — discharge / transfer / continued admission. Do not include identifiable outcome dates.)_

## Learning Points

- _(Key clinical lesson or teaching point this case illustrates)_
- 

## References / Guidelines Used

_(Clinical guidelines, literature that informed the management — link to [[clinical-guidelines]] or [[treatment-protocols]])_

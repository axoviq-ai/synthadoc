---
title: Specifications
status: draft
confidence: low
type: concept
sources: []
---

# Specifications

Technical specifications for materials, products, and workmanship standards for all development projects. Organized by CSI MasterFormat divisions. Populate by ingesting project specifications.

Each specification record captures:

- **Division and section** — CSI MasterFormat division (00–33) and section number (e.g. 03 30 00 Cast-in-Place Concrete, 07 21 00 Thermal Insulation, 09 91 23 Interior Painting)
- **Scope** — what the specification section covers, materials included, excluded work
- **Approved products and manufacturers** — basis-of-design product, approved equals, substitution request procedure
- **Performance requirements** — minimum standards (compressive strength, R-value, fire rating, LEED/WELL credits targeted)
- **Installation requirements** — surface preparation, application method, tolerances, quality of workmanship standards
- **Testing and inspection** — required tests, frequency, acceptance criteria, reporting format
- **Submittals required** — product data, shop drawings, samples, operations and maintenance data

**How to populate:**

1. Ingest your project specifications:
   ```
   synthadoc ingest docs/specifications/ --batch -w <wiki>
   ```

Cross-link to [[design-documents]], [[contractors]], and [[inspections]].

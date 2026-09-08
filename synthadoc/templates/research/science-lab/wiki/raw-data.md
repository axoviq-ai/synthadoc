---
title: Raw Data
status: draft
confidence: low
type: concept
sources: []
---

# Raw Data

Raw data catalog and data management records. Populate by ingesting data management plans and dataset manifests.

Each raw data record captures:

- **Dataset identity** — dataset name, collection date, experimenter, linked experiment (link to [[experiments]]), instrument used (link to [[instruments]])
- **Data format** — file format (CSV / TIFF / HDF5 / FastQ / .raw), file size, number of files, naming convention
- **Storage location** — primary storage path, backup location, backup schedule, retention period
- **Data quality** — QC metrics applied, acceptance criteria, failed/flagged samples
- **Metadata** — metadata fields recorded per sample (sample ID, condition, timepoint, replicate number, batch), metadata file location
- **Access** — access restrictions, sharing plan (public / restricted / embargoed until publication)
- **FAIR compliance** — findable (DOI or identifier), accessible (repository), interoperable (standard format), reusable (license)

**How to populate:**

1. Ingest your data management plan:
   ```
   synthadoc ingest docs/data-management-plan.pdf -w <wiki>
   ```

Cross-link to [[experiments]], [[findings]], and [[publications]].

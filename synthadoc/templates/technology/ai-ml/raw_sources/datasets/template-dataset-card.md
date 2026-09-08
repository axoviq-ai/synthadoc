# Dataset Card: [Dataset Name] v[Version]

> **How to use this form**
>
> This template follows the **HuggingFace Dataset Card format + W3C DCAT-2** --
> the community-standard format for documenting ML datasets used by the Hugging Face Hub
> and compatible with the W3C Data Catalog Vocabulary.
> If you already have dataset documentation in another format, skip this form and ingest it directly.
>
> Reference: [HuggingFace Dataset Cards](https://huggingface.co/docs/hub/datasets-cards)
>
> 1. Copy this file and rename it (e.g. `customer-support-tickets-v3.md`)
> 2. Fill in all sections before using this dataset in any experiment or model training run
> 3. Run: `synthadoc ingest raw_sources/datasets/<filename>.md -w <wiki>`

---

## Dataset Identity

- **Dataset name:**
- **Version:**
- **Created by:**
- **Creation date:** YYYY-MM-DD
- **License:** (CC-BY-4.0 / CC-BY-NC / research-only / proprietary / other)
- **Storage location:** (S3 path / HuggingFace Hub slug / internal data lake path)

---

## Dataset Summary

*(What is this dataset? What is it for? Two to four sentences covering: what the data contains,
why it was created, and what makes it distinctive.)*

---

## Supported Tasks

*(List the ML tasks this dataset is appropriate for.)*

- (e.g. Text classification / Named entity recognition / Question answering / Regression)
-

---

## Languages

*(If the dataset contains natural language text — list all languages present, with approximate
proportion if mixed.)*

- (e.g. English ~80%, Spanish ~20%)

---

## Data Sources

- **Original source(s):** (web scrape / internal system / licensed dataset / annotation platform / synthetic)
- **Collection method:** (how was the raw data gathered?)
- **Collection date range:** YYYY-MM-DD to YYYY-MM-DD
- **Sampling strategy:** (how were examples selected from the broader source population?)

---

## Dataset Structure

**Row count:** (total; train / val / test splits)

| Split | Count | Notes |
|-------|-------|-------|
| Train | | |
| Validation | | |
| Test | | |

**Features / columns:**

| Field | Type | Description | Example value |
|-------|------|-------------|---------------|
| | | | |
| | | | |

---

## Data Collection Process

- **Annotation process:** (human annotators / automatic labelling / crowdsourced / expert-only)
- **Annotation guidelines:** (brief description or link)
- **Inter-annotator agreement:** (Cohen's kappa / Fleiss' kappa / % agreement — value and what it means)
- **Quality control:** (how were low-quality annotations detected and removed?)

---

## Preprocessing

*(Describe all transformations applied to the raw source data before this dataset was finalised.)*

- Text cleaning: (lowercasing, punctuation removal, etc.)
- Deduplication: (method and deduplication rate)
- Filtering: (rules used to exclude examples)
- Normalisation / feature engineering: (if tabular)

---

## Known Issues and Limitations

- **Missing data:** (fields with high null rates; explanation)
- **Class imbalance:** (label distribution; minority class %)
- **Potential contamination:** (any risk of train/test leakage with known benchmarks?)
- **Ethical concerns:** (privacy risk, demographic bias, potentially harmful content)
- **Geographic / demographic representation:** (which populations are over- or under-represented?)

---

## Citation

If this dataset is published or should be cited in papers:

```
@dataset{<citekey>,
  title = {<Dataset Name>},
  author = {<Authors>},
  year = {<Year>},
  url = {<URL>}
}
```

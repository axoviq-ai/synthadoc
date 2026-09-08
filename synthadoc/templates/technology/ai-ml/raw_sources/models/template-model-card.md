# Model Card: [Model Name] v[Version]

> **How to use this form**
>
> This template follows the **Google Model Cards** standard (Mitchell et al. 2019,
> "Model Cards for Model Reporting") -- the industry standard for transparent,
> structured documentation of machine learning models.
> If you already have model documentation in another format, skip this form and ingest it directly.
>
> Reference: [Model Cards for Model Reporting](https://modelcards.withgoogle.com/about)
>
> 1. Copy this file and rename it (e.g. `customer-churn-classifier-v2.md`)
> 2. Fill in all sections; update the card whenever the model is retrained or re-evaluated
> 3. Run: `synthadoc ingest raw_sources/models/<filename>.md -w <wiki>`
>
> Model cards are a transparency artifact — fill one out for every model promoted to production.

---

## Model Identity

- **Model name:**
- **Version:** (semantic version or git hash)
- **Model type:** (e.g. binary classifier / multi-class classifier / regression / generative / ranking)
- **Framework:** (PyTorch / TensorFlow / scikit-learn / XGBoost / other)
- **Training date:** YYYY-MM-DD
- **Owner team:**
- **Primary contact:**
- **MLflow / W&B model URL:**

---

## Intended Use

**Primary use cases:**
*(What tasks is this model designed for? Be specific about input format and output interpretation.)*
-

**Intended users:**
*(Who is meant to use this model or its outputs — data scientists, product features, end users?)*
-

**Out-of-scope uses:**
*(Explicitly list tasks or populations this model should NOT be applied to.)*
-

---

## Model Description

- **Architecture:** (e.g. "4-layer transformer encoder, 110M parameters")
- **Input format:** (e.g. "tokenised text, max 512 tokens" / "tabular: N features, all numeric")
- **Output format:** (e.g. "probability score 0–1" / "class label from set {A, B, C}")
- **Key hyperparameters:**
  - Learning rate:
  - Batch size:
  - Epochs / steps:
  - Regularisation:

---

## Training Data

- **Dataset(s) used:** (link to [[datasets]])
- **Dataset size:** (total examples; train/val/test split)
- **Date range of training data:** YYYY-MM-DD to YYYY-MM-DD
- **Preprocessing steps:** (tokenisation, normalisation, feature engineering, deduplication)
- **Known data biases:** (geographic, demographic, temporal, or sampling biases in the training data)

---

## Evaluation Results

*Include primary metrics across the full test set AND subgroup breakdowns where fairness matters.*

| Metric | Value | Dataset | Notes |
|--------|-------|---------|-------|
| | | Full test set | |
| | | Subgroup: | |
| | | Subgroup: | |

- **Evaluation methodology:** (link to [[evaluation-methodology]])
- **Comparison to baseline:** (model being replaced, delta on primary metric)

---

## Limitations

**Known failure modes:**
*(Cases where the model underperforms, produces wrong outputs, or is unreliable.)*
-

**Edge cases:**
*(Inputs that are technically valid but produce unreliable outputs.)*
-

**Degradation conditions:**
*(Conditions under which model performance degrades — data drift, distribution shift, etc.)*
-

---

## Ethical Considerations

- **Fairness analysis:** (were subgroup performance gaps analysed? what were the findings?)
- **Potential harms:** (what harm could result if the model produces a wrong output?)
- **Bias mitigation measures applied:** (resampling, fairness constraints, post-hoc calibration, etc.)
- **Human oversight requirement:** (is a human in the loop before the model output affects a user?)

---

## Deployment Details

- **Serving infrastructure:** (link to [[serving-infrastructure]])
- **Inference latency SLO:** (e.g. P99 < 200 ms)
- **Monitoring approach:** (what metrics are tracked post-deployment; alert thresholds)
- **Model refresh cadence:** (how often is this model retrained — triggered / scheduled / manual)

---

## Version History

| Version | Date | Change Summary |
|---------|------|---------------|
| | | Initial production release |
| | | |

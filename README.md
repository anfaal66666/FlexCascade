# Caselaw Hierarchy Project

This repository is now **R-first**.

The main project implements a hierarchy-aware issuer classification pipeline for `HFforLegal/case-law`:

- Stage 1: `document -> state`
- Stage 2: `document -> issuer` within the predicted state
- Fallback: global `document -> issuer` when state confidence is low

Supported model families:

- `svm`
- `random_forest`
- `xgboost`

Python is used only for one support task:

- exporting the Hugging Face dataset into a flat file that the R pipeline reads

## Dataset target

The current project pipeline is designed for `HFforLegal/case-law`, whose dataset card lists:

- `state`
- `issuer`
- `document`
- `title`
- `citation`
- `docket_number`
- `timestamp`

Reference: https://huggingface.co/datasets/HFforLegal/case-law

## Install R Dependencies

```bash
Rscript scripts/install_r_dependencies.R
python3 -m pip install datasets pandas
```

The Python install is only for `scripts/export_hf_case_law.py`, which exports the Hugging Face dataset into a flat file for the R pipeline.

## Run experiments

Run a smaller experiment first:

```bash
Rscript run_experiment.R --max-rows 5000 --output-dir results/sample_run
```

Run only specific algorithms:

```bash
Rscript run_experiment.R --algorithms svm xgboost --output-dir results/svm_xgb
```

Run a mixed-model hierarchy from a config file:

```bash
Rscript run_experiment.R --config config/mixed_models.json
```

Run with pre-trained embeddings:

```bash
Rscript run_experiment.R --config config/glove_hybrid.json
```

Outputs:

- `metrics_summary.csv`: side-by-side results for flat and hierarchical systems
- `selected_configs.json`: tuned fallback configuration per algorithm
- `split_summary.json`: dataset split sizes and label counts
- `models/`: serialized `.rds` trained models

## Pipeline summary

The project includes:

- dataset export from Hugging Face via a small Python helper
- dataset loading in R
- cleaning and normalization
- engineered metadata features
- TF-IDF word and bigram features
- average pooled `word2vec` / `GloVe` / `fastText` embeddings from embedding files
- hybrid TF-IDF + embedding features
- flat state classification baseline
- flat issuer classification baseline
- plain hierarchical cascade
- calibrated fallback cascade with optional top-2 routing
- per-model hyperparameter control
- mixed-model hierarchies where Stage 1, Stage 2, and fallback can differ

## Project layout

- `run_experiment.R`: command-line entry point
- `R/io.R`: data export and loading
- `R/features.R`: vocabulary building and sparse feature generation
- `R/models.R`: switchable estimator wrappers
- `R/hierarchy.R`: hierarchical cascade logic
- `R/evaluation.R`: metrics and error analysis
- `R/experiment.R`: end-to-end training and comparison
- `scripts/export_hf_case_law.py`: Python helper for dataset export
- `config/`: example experiment configurations

## Embedding strategies

Supported `embedding.strategy` values:

- `tfidf`
- `word2vec`
- `glove`
- `fasttext`
- `hybrid`

For `word2vec`, `glove`, `fasttext`, and `hybrid`, provide:

- `embedding_path`
- `embedding_dim`

The loader expects a standard text embedding format:

```text
word 0.123 -0.114 ...
```

## Hyperparameter control

All model families can be tuned through config:

- `models.svm`
- `models.random_forest`
- `models.xgboost`

Examples:

- SVM: `cost`, `type`, `epsilon`, `bias`
- Random Forest: `ntree`, `mtry`, `nodesize`, `maxnodes`, `max_text_features`
- XGBoost: `eta`, `max_depth`, `subsample`, `colsample_bytree`, `min_child_weight`, `gamma`, `lambda`, `alpha`, `nrounds`

## Mixed stage models

Yes, the pipeline now supports different models by stage. Example:

```json
{
  "hierarchy": {
    "stage1_model": "svm",
    "stage2_model": "xgboost",
    "fallback_model": "random_forest"
  }
}
```

## Why this approach

The full CAP corpus is very large, so it should not be committed into a source repository. Instead, this repo now contains a downloader that can fetch:

- top-level metadata files
- specific reporter volume zip archives
- any direct static export path

## Usage

Download jurisdiction metadata:

```bash
python3 scripts/download_caselaw.py --metadata jurisdictions
```

Download a specific reporter volume zip:

```bash
python3 scripts/download_caselaw.py --reporter ark --volume 14
```

Download a direct static export path:

```bash
python3 scripts/download_caselaw.py --url-path ark/14.zip
```

Files are written under `data/caselaw/` by default.

## Full local corpus download

To download the full machine-readable CAP corpus as volume zip archives:

```bash
python3 scripts/download_caselaw_bulk.py
```

This downloads all reporter `zip` files under `data/caselaw_full/` and keeps resumable progress in `data/caselaw_full/download_state.json`.

## Source

CAP’s current documentation says bulk downloads are available from `https://static.case.law/`.

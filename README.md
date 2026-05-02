# Caselaw Hierarchy Project

This repository is now **R-first**.

The main project implements a hierarchy-aware issuer classification pipeline for two supported sources:

- `HFforLegal/case-law`
- `CourtListener` bulk case-law tables joined into the same flat schema

Pipeline shape:

- Stage 1: `document -> state`
- Stage 2: `document -> issuer` within the predicted state
- Fallback: global `document -> issuer` when state confidence is low

Supported model families:

- `svm`
- `random_forest`
- `xgboost`

Python is used only for one support task:

- exporting the Hugging Face dataset into a flat file that the R pipeline reads

## Dataset targets

### HFforLegal/case-law

The Hugging Face dataset provides:

- `state`
- `issuer`
- `document`
- `title`
- `citation`
- `docket_number`
- `timestamp`

Reference: https://huggingface.co/datasets/HFforLegal/case-law

### CourtListener

CourtListener does not expose a single ready training table, so this repo prepares one by joining:

- `opinions`
- `opinion-clusters`
- `dockets`
- `courts`

The preparation step derives:

- `document`: opinion text, aggregated by cluster by default
- `issuer`: court full name
- `state`: derived from court metadata

The prepared output is written to the same flat schema used by the R pipeline:

- `title`
- `citation`
- `docket_number`
- `state`
- `issuer`
- `document`
- `timestamp`

## Install R Dependencies

```bash
Rscript scripts/install_r_dependencies.R
python3 -m pip install datasets pandas
```

The Python install is only for `scripts/export_hf_case_law.py`, which exports the Hugging Face dataset into a flat file for the R pipeline.

For CourtListener preparation, also install:

```bash
python3 -m pip install duckdb pandas
```

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

Run the 10-state subset that includes Illinois:

```bash
Rscript run_experiment.R --config config/ten_states_including_illinois.json
```

Tune fixed parameters on an all-state sample, then train the full all-state models:

```bash
Rscript run_experiment.R --config config/all_states_tuning_20k.json
python3 scripts/build_full_config_from_tuning.py \
  --tuning-dir results/all_states_tuning_20k \
  --base-config config/all_states_full_best.json \
  --output-config config/all_states_full_selected.json
Rscript run_experiment.R --config config/all_states_full_selected.json
```

Run with pre-trained embeddings:

```bash
Rscript run_experiment.R --config config/glove_hybrid.json
```

Run the CourtListener path once the four core bulk files are downloaded:

```bash
Rscript run_experiment.R --config config/courtlistener_top10_fast_svm.json
```

Outputs:

- `metrics_summary.csv`: side-by-side results for flat and hierarchical systems
- `selected_configs.json`: tuned fallback configuration per algorithm
- `split_summary.json`: dataset split sizes and label counts
- `models/`: serialized `.rds` trained models

Model artifact naming:

- global state classifier: `ModelType_Scope_Stage1State_RunName.rds`
- global issuer classifier: `ModelType_Scope_GlobalIssuer_RunName.rds`
- local Stage 2 issuer classifier: `ModelType_State_TwoStageLocalIssuer_RunName.rds`
- full cascade bundle: `Stage1-Stage2-Fallback_Scope_TwoStageCascade_RunName.rds`

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
- `scripts/prepare_courtlistener_dataset.py`: joins CourtListener bulk tables into training format
- `R/features.R`: vocabulary building and sparse feature generation
- `R/models.R`: switchable estimator wrappers
- `R/hierarchy.R`: hierarchical cascade logic
- `R/evaluation.R`: metrics and error analysis
- `R/experiment.R`: end-to-end training and comparison
- `scripts/export_hf_case_law.py`: Python helper for dataset export
- `config/`: example experiment configurations
- `scripts/profile_states.py`: dataset state/issuer profiler

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

## CourtListener bulk download

To download the four core CourtListener files needed for the join:

```bash
python3 scripts/download_courtlistener.py
```

This fetches:

- `courts-*.csv.bz2`
- `dockets-*.csv.bz2`
- `opinion-clusters-*.csv.bz2`
- `opinions-*.csv.bz2`

into `data/courtlistener/` and keeps resumable progress in `data/courtlistener/download_state.json`.

## CourtListener preprocessing

To prepare a flat training table after the download completes:

```bash
python3 scripts/prepare_courtlistener_dataset.py \
  --input-dir data/courtlistener \
  --output data/processed/courtlistener_case_law_full.csv.gz \
  --aggregate-level cluster \
  --require-state
```

Useful options:

- `--states illinois california`
- `--top-n-states 10`
- `--include-states illinois`
- `--max-rows 20000`

The script keeps support for the existing Hugging Face dataset path, so both sources can feed the same R training pipeline.

## Source

CAP’s current documentation says bulk downloads are available from `https://static.case.law/`.

#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(Matrix)
  library(LiblineaR)
  library(randomForest)
  library(xgboost)
})

source("R/utils.R")
source("R/io.R")
source("R/split.R")
source("R/features.R")
source("R/models.R")
source("R/hierarchy.R")
source("R/evaluation.R")
source("R/experiment.R")

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2L) {
  stop("Usage: Rscript scripts/backfill_run_metrics.R <config.json> <result_dir>")
}

config_path <- args[[1L]]
result_dir <- args[[2L]]

config <- deep_merge(default_experiment_config(), jsonlite::read_json(config_path, simplifyVector = FALSE))
config$output_dir <- result_dir

dataset_bundle <- load_case_law_data(config)
frame <- dataset_bundle$frame
issuer_to_state <- dataset_bundle$issuer_to_state
splits <- stratified_split(frame$issuer, seed = config$seed)

feature_algo <- config$comparison_runs[[1L]]$hierarchy$stage1_model
feature_key <- build_feature_cache_key(feature_algo, config)
feature_bundle_path <- file.path(config$feature_cache_dir %||% "data/feature_cache", sprintf("%s.rds", feature_key))
feature_bundle <- readRDS(feature_bundle_path)

registry <- jsonlite::read_json(file.path(result_dir, "model_registry.json"), simplifyVector = TRUE)
selected_configs <- jsonlite::read_json(file.path(result_dir, "selected_configs.json"), simplifyVector = TRUE)

eval_dir <- ensure_dir(file.path(result_dir, "evaluation"))

split_frames <- list(
  train = frame[splits$train],
  validation = frame[splits$validation],
  test = frame[splits$test]
)
split_features <- list(
  train = feature_bundle$x_train,
  validation = feature_bundle$x_val,
  test = feature_bundle$x_test
)

all_rows <- list()

for (run_name in names(registry)) {
  run_info <- registry[[run_name]]
  state_model <- readRDS(file.path(result_dir, "models", run_info$model_files$state_model))
  global_model <- readRDS(file.path(result_dir, "models", run_info$model_files$global_issuer_model))
  cascade <- readRDS(file.path(result_dir, "models", run_info$model_files$cascade))
  fallback_cfg <- selected_configs[[run_name]]

  for (split_name in names(split_frames)) {
    df <- split_frames[[split_name]]
    x <- split_features[[split_name]]
    if (methods::is(x, "Matrix") && !methods::is(x, "dgCMatrix")) {
      x <- methods::as(x, "dgCMatrix")
    }

    state_pred <- predict_classifier(state_model, x)
    flat_pred <- predict_classifier(global_model, x)
    plain_pred <- predict_plain_cascade(cascade, x)
    fallback_pred <- predict_with_fallback(cascade, x, fallback_cfg)

    state_metrics <- evaluate_state_predictions(df$state, state_pred$labels)
    state_metrics$log_loss <- multiclass_log_loss(df$state, state_pred$probabilities, state_model$classes)
    state_metrics$top_3_accuracy <- top_k_accuracy(df$state, state_pred$probabilities, state_model$classes, k = 3L)

    flat_metrics <- evaluate_issuer_predictions(
      truth_issuer = df$issuer,
      truth_state = df$state,
      predicted_issuer = flat_pred$labels,
      predicted_probs = flat_pred$probabilities,
      prob_classes = global_model$classes,
      issuer_to_state = issuer_to_state
    )

    plain_metrics <- evaluate_issuer_predictions(
      truth_issuer = df$issuer,
      truth_state = df$state,
      predicted_issuer = plain_pred$issuers,
      predicted_probs = NULL,
      prob_classes = NULL,
      issuer_to_state = issuer_to_state
    )

    fallback_metrics <- evaluate_issuer_predictions(
      truth_issuer = df$issuer,
      truth_state = df$state,
      predicted_issuer = fallback_pred$issuers,
      predicted_probs = fallback_pred$probabilities,
      prob_classes = cascade$global_issuer_model$classes,
      issuer_to_state = issuer_to_state
    )

    all_rows[[length(all_rows) + 1L]] <- as_result_row(state_metrics, run_name, "flat_state")[, split := split_name]
    all_rows[[length(all_rows) + 1L]] <- as_result_row(flat_metrics, run_name, "flat_issuer")[, split := split_name]
    all_rows[[length(all_rows) + 1L]] <- as_result_row(plain_metrics, run_name, "plain_cascade")[, split := split_name]
    all_rows[[length(all_rows) + 1L]] <- as_result_row(fallback_metrics, run_name, "cascade_with_fallback")[, split := split_name]
  }
}

metrics_by_split <- data.table::rbindlist(all_rows, fill = TRUE)
data.table::fwrite(metrics_by_split, file.path(result_dir, "metrics_by_split.csv"))

cat(sprintf("Wrote %s\n", file.path(result_dir, "metrics_by_split.csv")))

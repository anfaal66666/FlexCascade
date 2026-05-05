run_experiment <- function(config) {
  log_progress("Starting experiment run.")
  ensure_dir(config$output_dir)
  models_dir <- ensure_dir(file.path(config$output_dir, "models"))
  stage2_models_dir <- ensure_dir(file.path(models_dir, "stage2_local_models"))
  feature_cache_dir <- ensure_dir(config$feature_cache_dir %||% "data/feature_cache")
  eval_dir <- ensure_dir(file.path(config$output_dir, "evaluation"))
  predictions_dir <- ensure_dir(file.path(eval_dir, "predictions"))
  confusion_dir <- ensure_dir(file.path(eval_dir, "confusion"))
  class_metrics_dir <- ensure_dir(file.path(eval_dir, "per_class"))
  registry <- list()

  dataset_bundle <- load_case_law_data(config)
  frame <- dataset_bundle$frame
  issuer_to_state <- dataset_bundle$issuer_to_state
  log_progress(sprintf("Loaded dataset with %s rows.", format(nrow(frame), big.mark = ",")))

  splits <- stratified_split(frame$issuer, seed = config$seed)
  train_df <- frame[splits$train]
  val_df <- frame[splits$validation]
  test_df <- frame[splits$test]
  write_json_file(
    list(
      train_rows = nrow(train_df),
      validation_rows = nrow(val_df),
      test_rows = nrow(test_df),
      states = data.table::uniqueN(frame$state),
      issuers = data.table::uniqueN(frame$issuer)
    ),
    file.path(config$output_dir, "split_summary.json")
  )
  log_progress("Wrote split summary.")

  results <- list()
  selected_configs <- list()
  feature_cache <- list()

  comparison_runs <- config$comparison_runs
  if (is.null(comparison_runs) || length(comparison_runs) == 0L) {
    stop("No comparison_runs configured.")
  }

  for (run in comparison_runs) {
    run_name <- run$name %||% paste(run$hierarchy$stage1_model, run$hierarchy$stage2_model, run$hierarchy$fallback_model, sep = "_")
    run_config <- deep_merge(config, run)
    run_scope <- dataset_scope_label(run_config)
    log_progress(sprintf("Run %s: starting.", run_name))

    feature_algo <- run_config$feature_model %||% run_config$hierarchy$stage1_model
    feature_key <- build_feature_cache_key(feature_algo, run_config)
    if (is.null(feature_cache[[feature_key]])) {
      feature_bundle_path <- file.path(feature_cache_dir, sprintf("%s.rds", feature_key))
      if (file.exists(feature_bundle_path)) {
        log_progress(sprintf("Run %s: loading cached feature bundle %s.", run_name, basename(feature_bundle_path)))
        feature_cache[[feature_key]] <- readRDS(feature_bundle_path)
      } else {
        log_progress(sprintf("Run %s: fitting feature pipeline (%s).", run_name, feature_algo))
        feature_pipeline <- fit_feature_pipeline(train_df, feature_algo, run_config)
        saveRDS(feature_pipeline, file.path(models_dir, sprintf("%s_feature_pipeline.rds", canonical_scope_name(run_name))))
        log_progress(sprintf("Run %s: feature pipeline saved.", run_name))
        log_progress(sprintf("Run %s: transforming train/validation/test features.", run_name))
        feature_cache[[feature_key]] <- list(
          pipeline = feature_pipeline,
          x_train = transform_features(train_df, feature_pipeline),
          x_val = transform_features(val_df, feature_pipeline),
          x_test = transform_features(test_df, feature_pipeline)
        )
        saveRDS(feature_cache[[feature_key]], feature_bundle_path)
        log_progress(sprintf("Run %s: feature bundle cached to disk.", run_name))
      }
      write_json_file(
        list(
          run = run_name,
          feature_algorithm = feature_algo,
          feature_cache_key = feature_key,
          train_rows = nrow(feature_cache[[feature_key]]$x_train),
          train_cols = ncol(feature_cache[[feature_key]]$x_train),
          validation_rows = nrow(feature_cache[[feature_key]]$x_val),
          test_rows = nrow(feature_cache[[feature_key]]$x_test)
        ),
        file.path(config$output_dir, sprintf("%s_feature_status.json", canonical_scope_name(run_name)))
      )
      log_progress(sprintf("Run %s: feature matrices ready.", run_name))
    }
    feature_bundle <- feature_cache[[feature_key]]
    feature_pipeline <- feature_bundle$pipeline
    x_train <- feature_bundle$x_train
    x_val <- feature_bundle$x_val
    x_test <- feature_bundle$x_test

    state_algo <- run_config$hierarchy$stage1_model
    stage2_algo <- run_config$hierarchy$stage2_model
    fallback_algo <- run_config$hierarchy$fallback_model

    state_model <- fit_classifier(
      state_algo,
      x_train,
      train_df$state,
      run_config$models[[state_algo]] %||% list(),
      seed = config$seed
    )
    state_model_name <- build_model_artifact_name(state_algo, run_scope, "Stage1State", run_name)
    saveRDS(state_model, file.path(models_dir, paste0(state_model_name, ".rds")))
    log_progress(sprintf("Run %s: saved Stage 1 state model.", run_name))

    state_pred <- predict_classifier(state_model, x_test)
    save_state_evaluation_artifacts(
      output_dir = predictions_dir,
      confusion_dir = confusion_dir,
      class_metrics_dir = class_metrics_dir,
      run_name = run_name,
      system_name = "flat_state",
      test_df = test_df,
      predicted_state = state_pred$labels,
      probabilities = state_pred$probabilities,
      prob_classes = state_model$classes
    )
    results[[length(results) + 1L]] <- as_result_row(
      evaluate_state_predictions(test_df$state, state_pred$labels),
      algorithm = run_name,
      system = "flat_state"
    )
    flush_partial_outputs(config$output_dir, results, selected_configs, registry)
    log_progress(sprintf("Run %s: flat state evaluation saved.", run_name))

    flat_issuer_model <- fit_classifier(
      fallback_algo,
      x_train,
      train_df$issuer,
      run_config$models[[fallback_algo]] %||% list(),
      seed = config$seed
    )
    global_model_name <- build_model_artifact_name(fallback_algo, run_scope, "GlobalIssuer", run_name)
    saveRDS(flat_issuer_model, file.path(models_dir, paste0(global_model_name, ".rds")))
    log_progress(sprintf("Run %s: saved global issuer model.", run_name))

    flat_pred <- predict_classifier(flat_issuer_model, x_test)
    save_issuer_evaluation_artifacts(
      output_dir = predictions_dir,
      confusion_dir = confusion_dir,
      class_metrics_dir = class_metrics_dir,
      run_name = run_name,
      system_name = "flat_issuer",
      test_df = test_df,
      predicted_issuer = flat_pred$labels,
      predicted_state = unname(issuer_to_state[flat_pred$labels]),
      probabilities = flat_pred$probabilities,
      prob_classes = flat_issuer_model$classes
    )
    results[[length(results) + 1L]] <- as_result_row(
      evaluate_issuer_predictions(
        truth_issuer = test_df$issuer,
        truth_state = test_df$state,
        predicted_issuer = flat_pred$labels,
        predicted_probs = flat_pred$probabilities,
        prob_classes = flat_issuer_model$classes,
        issuer_to_state = issuer_to_state
      ),
      algorithm = run_name,
      system = "flat_issuer"
    )
    flush_partial_outputs(config$output_dir, results, selected_configs, registry)
    log_progress(sprintf("Run %s: flat issuer evaluation saved.", run_name))

    cascade <- fit_hierarchical_cascade(
      hierarchy_config = run_config$hierarchy,
      model_configs = run_config$models,
      x_train = x_train,
      train_df = train_df,
      issuer_to_state = issuer_to_state,
      seed = config$seed
    )
    cascade$feature_pipeline <- feature_pipeline
    cascade_name <- build_cascade_artifact_name(run_config$hierarchy, run_scope, "TwoStageCascade", run_name)
    saveRDS(cascade, file.path(models_dir, paste0(cascade_name, ".rds")))
    local_artifacts <- save_stage2_local_models(cascade, stage2_models_dir, run_scope, stage2_algo, run_name)
    log_progress(sprintf("Run %s: saved cascade bundle and %s local stage-2 models.", run_name, length(local_artifacts)))

    plain_pred <- predict_plain_cascade(cascade, x_test)
    save_issuer_evaluation_artifacts(
      output_dir = predictions_dir,
      confusion_dir = confusion_dir,
      class_metrics_dir = class_metrics_dir,
      run_name = run_name,
      system_name = "plain_cascade",
      test_df = test_df,
      predicted_issuer = plain_pred$issuers,
      predicted_state = plain_pred$states,
      probabilities = NULL,
      prob_classes = NULL
    )
    results[[length(results) + 1L]] <- as_result_row(
      evaluate_issuer_predictions(
        truth_issuer = test_df$issuer,
        truth_state = test_df$state,
        predicted_issuer = plain_pred$issuers,
        predicted_probs = NULL,
        prob_classes = NULL,
        issuer_to_state = issuer_to_state
      ),
      algorithm = run_name,
      system = "plain_cascade"
    )
    flush_partial_outputs(config$output_dir, results, selected_configs, registry)
    log_progress(sprintf("Run %s: plain cascade evaluation saved.", run_name))

    best_config <- tune_cascade_config(cascade, x_val, val_df, run_config$tuning)
    selected_configs[[run_name]] <- best_config
    registry[[run_name]] <- list(
      scope = run_scope,
      hierarchy = run_config$hierarchy,
      model_files = list(
        state_model = paste0(state_model_name, ".rds"),
        global_issuer_model = paste0(global_model_name, ".rds"),
        cascade = paste0(cascade_name, ".rds"),
        stage2_local_models = unname(local_artifacts)
      ),
      model_params = run_config$models
    )
    flush_partial_outputs(config$output_dir, results, selected_configs, registry)
    log_progress(sprintf("Run %s: fallback config selected.", run_name))

    fallback_pred <- predict_with_fallback(cascade, x_test, best_config)
    save_issuer_evaluation_artifacts(
      output_dir = predictions_dir,
      confusion_dir = confusion_dir,
      class_metrics_dir = class_metrics_dir,
      run_name = run_name,
      system_name = "cascade_with_fallback",
      test_df = test_df,
      predicted_issuer = fallback_pred$issuers,
      predicted_state = fallback_pred$states,
      probabilities = fallback_pred$probabilities,
      prob_classes = cascade$global_issuer_model$classes
    )
    results[[length(results) + 1L]] <- as_result_row(
      evaluate_issuer_predictions(
        truth_issuer = test_df$issuer,
        truth_state = test_df$state,
        predicted_issuer = fallback_pred$issuers,
        predicted_probs = fallback_pred$probabilities,
        prob_classes = cascade$global_issuer_model$classes,
        issuer_to_state = issuer_to_state
      ),
      algorithm = run_name,
      system = "cascade_with_fallback"
    )
    flush_partial_outputs(config$output_dir, results, selected_configs, registry)
    log_progress(sprintf("Run %s: cascade with fallback evaluation saved.", run_name))
  }

  results_table <- flush_partial_outputs(config$output_dir, results, selected_configs, registry)
  log_progress("Experiment run complete.")

  results_table
}

as_result_row <- function(metrics, algorithm, system) {
  data.table::as.data.table(c(metrics, list(algorithm = algorithm, system = system)))
}

save_stage2_local_models <- function(cascade, output_dir, run_name, stage2_model_type = NULL, model_run_name = NULL) {
  if (is.null(cascade$local_models) || length(cascade$local_models) == 0L) {
    return(character())
  }

  output_files <- character()
  for (state_name in names(cascade$local_models)) {
    model_object <- cascade$local_models[[state_name]]
    model_name_type <- stage2_model_type %||% model_object$algorithm
    output_filename <- paste0(
      build_model_artifact_name(model_name_type, state_name, "TwoStageLocalIssuer", model_run_name %||% run_name),
      ".rds"
    )
    output_path <- file.path(output_dir, output_filename)
    saveRDS(model_object, output_path)
    output_files[[state_name]] <- output_filename
  }

  output_files
}

dataset_scope_label <- function(config) {
  if (!is.null(config$state_subset) && length(config$state_subset) > 0L) {
    return(sprintf("%dStates", length(unique(unlist(config$state_subset)))))
  }
  if (!is.null(config$top_n_states)) {
    return(sprintf("Top%dStates", as.integer(config$top_n_states)))
  }
  "AllStates"
}

build_model_artifact_name <- function(model_type, scope, pipeline_type, run_name = NULL) {
  parts <- c(canonical_model_name(model_type), canonical_scope_name(scope), pipeline_type)
  if (!is.null(run_name) && nzchar(run_name)) {
    parts <- c(parts, canonical_scope_name(run_name))
  }
  paste(parts, collapse = "_")
}

build_cascade_artifact_name <- function(hierarchy, scope, pipeline_type, run_name = NULL) {
  model_block <- paste(
    canonical_model_name(hierarchy$stage1_model),
    canonical_model_name(hierarchy$stage2_model),
    canonical_model_name(hierarchy$fallback_model),
    sep = "-"
  )
  parts <- c(model_block, canonical_scope_name(scope), pipeline_type)
  if (!is.null(run_name) && nzchar(run_name)) {
    parts <- c(parts, canonical_scope_name(run_name))
  }
  paste(parts, collapse = "_")
}

canonical_model_name <- function(model_type) {
  gsub("[^A-Za-z0-9]+", "", tools::toTitleCase(gsub("_", " ", model_type)))
}

canonical_scope_name <- function(scope) {
  safe <- gsub("[^A-Za-z0-9]+", "_", normalize_text(scope))
  gsub("^_+|_+$", "", safe)
}

build_feature_cache_key <- function(feature_algo, config) {
  settings <- feature_settings_for_model(feature_algo, config)
  paste(
    dataset_scope_label(config),
    config$split %||% "us",
    config$seed %||% 42L,
    config$embedding$strategy %||% "tfidf",
    settings$max_features %||% "default",
    settings$max_doc_tokens %||% "default",
    config$embedding$min_df %||% "default",
    isTRUE(config$embedding$use_bigrams),
    config$max_rows %||% "full",
    config$min_issuer_count %||% 1L,
    sep = "__"
  )
}

flush_partial_outputs <- function(output_dir, results, selected_configs, registry) {
  results_table <- data.table::rbindlist(results, fill = TRUE)
  data.table::fwrite(results_table, file.path(output_dir, "metrics_summary.csv"))
  write_json_file(selected_configs, file.path(output_dir, "selected_configs.json"))
  write_json_file(registry, file.path(output_dir, "model_registry.json"))
  results_table
}

log_progress <- function(message) {
  timestamp <- format(Sys.time(), "%Y-%m-%d %H:%M:%S")
  cat(sprintf("[%s] %s\n", timestamp, message))
  flush.console()
}

save_state_evaluation_artifacts <- function(output_dir, confusion_dir, class_metrics_dir, run_name, system_name, test_df, predicted_state, probabilities, prob_classes) {
  prediction_table <- data.table::data.table(
    row_id = seq_len(nrow(test_df)),
    truth_state = test_df$state,
    predicted_state = predicted_state,
    correct = test_df$state == predicted_state,
    top_3_states = if (!is.null(probabilities)) top_k_labels(probabilities, prob_classes, k = 3L) else NA_character_
  )
  data.table::fwrite(prediction_table, file.path(output_dir, sprintf("%s__%s_predictions.csv", run_name, system_name)))
  data.table::fwrite(
    confusion_table(test_df$state, predicted_state),
    file.path(confusion_dir, sprintf("%s__%s_confusion.csv", run_name, system_name))
  )
  data.table::fwrite(
    per_class_metrics(test_df$state, predicted_state),
    file.path(class_metrics_dir, sprintf("%s__%s_per_class.csv", run_name, system_name))
  )
}

save_issuer_evaluation_artifacts <- function(output_dir, confusion_dir, class_metrics_dir, run_name, system_name, test_df, predicted_issuer, predicted_state, probabilities, prob_classes) {
  prediction_table <- data.table::data.table(
    row_id = seq_len(nrow(test_df)),
    truth_state = test_df$state,
    truth_issuer = test_df$issuer,
    predicted_state = predicted_state,
    predicted_issuer = predicted_issuer,
    state_correct = test_df$state == predicted_state,
    issuer_correct = test_df$issuer == predicted_issuer,
    top_3_issuers = if (!is.null(probabilities)) top_k_labels(probabilities, prob_classes, k = 3L) else NA_character_
  )
  data.table::fwrite(prediction_table, file.path(output_dir, sprintf("%s__%s_predictions.csv", run_name, system_name)))
  data.table::fwrite(
    confusion_table(test_df$issuer, predicted_issuer),
    file.path(confusion_dir, sprintf("%s__%s_confusion.csv", run_name, system_name))
  )
  data.table::fwrite(
    per_class_metrics(test_df$issuer, predicted_issuer),
    file.path(class_metrics_dir, sprintf("%s__%s_per_class.csv", run_name, system_name))
  )
}

run_experiment <- function(config) {
  ensure_dir(config$output_dir)
  models_dir <- ensure_dir(file.path(config$output_dir, "models"))

  dataset_bundle <- load_case_law_data(config)
  frame <- dataset_bundle$frame
  issuer_to_state <- dataset_bundle$issuer_to_state

  splits <- stratified_split(frame$issuer, seed = config$seed)
  train_df <- frame[splits$train]
  val_df <- frame[splits$validation]
  test_df <- frame[splits$test]

  results <- list()
  selected_configs <- list()

  comparison_runs <- config$comparison_runs
  if (is.null(comparison_runs) || length(comparison_runs) == 0L) {
    stop("No comparison_runs configured.")
  }

  for (run in comparison_runs) {
    run_name <- run$name %||% paste(run$hierarchy$stage1_model, run$hierarchy$stage2_model, run$hierarchy$fallback_model, sep = "_")
    run_config <- deep_merge(config, run)

    feature_algo <- run_config$feature_model %||% run_config$hierarchy$stage1_model
    feature_pipeline <- fit_feature_pipeline(train_df, feature_algo, run_config)
    x_train <- transform_features(train_df, feature_pipeline)
    x_val <- transform_features(val_df, feature_pipeline)
    x_test <- transform_features(test_df, feature_pipeline)

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
    saveRDS(state_model, file.path(models_dir, sprintf("%s_state_model.rds", run_name)))

    state_pred <- predict_classifier(state_model, x_test)
    results[[length(results) + 1L]] <- as_result_row(
      evaluate_state_predictions(test_df$state, state_pred$labels),
      algorithm = run_name,
      system = "flat_state"
    )

    flat_issuer_model <- fit_classifier(
      fallback_algo,
      x_train,
      train_df$issuer,
      run_config$models[[fallback_algo]] %||% list(),
      seed = config$seed
    )
    saveRDS(flat_issuer_model, file.path(models_dir, sprintf("%s_flat_issuer_model.rds", run_name)))

    flat_pred <- predict_classifier(flat_issuer_model, x_test)
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

    cascade <- fit_hierarchical_cascade(
      hierarchy_config = run_config$hierarchy,
      model_configs = run_config$models,
      x_train = x_train,
      train_df = train_df,
      issuer_to_state = issuer_to_state,
      seed = config$seed
    )
    cascade$feature_pipeline <- feature_pipeline
    saveRDS(cascade, file.path(models_dir, sprintf("%s_hierarchical_cascade.rds", run_name)))

    plain_pred <- predict_plain_cascade(cascade, x_test)
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

    best_config <- tune_cascade_config(cascade, x_val, val_df, run_config$tuning)
    selected_configs[[run_name]] <- best_config

    fallback_pred <- predict_with_fallback(cascade, x_test, best_config)
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
  }

  results_table <- data.table::rbindlist(results, fill = TRUE)
  data.table::fwrite(results_table, file.path(config$output_dir, "metrics_summary.csv"))
  write_json_file(selected_configs, file.path(config$output_dir, "selected_configs.json"))
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

  results_table
}

as_result_row <- function(metrics, algorithm, system) {
  data.table::as.data.table(c(metrics, list(algorithm = algorithm, system = system)))
}

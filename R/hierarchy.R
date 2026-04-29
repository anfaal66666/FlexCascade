fit_hierarchical_cascade <- function(hierarchy_config, model_configs, x_train, train_df, issuer_to_state, seed = 42L) {
  state_algo <- hierarchy_config$stage1_model
  stage2_algo <- hierarchy_config$stage2_model
  fallback_algo <- hierarchy_config$fallback_model

  state_model <- fit_classifier(state_algo, x_train, train_df$state, model_configs[[state_algo]] %||% list(), seed = seed)
  global_issuer_model <- fit_classifier(fallback_algo, x_train, train_df$issuer, model_configs[[fallback_algo]] %||% list(), seed = seed)

  local_models <- list()
  for (state_name in unique(train_df$state)) {
    state_rows <- which(train_df$state == state_name)
    local_models[[state_name]] <- fit_classifier(
      stage2_algo,
      x_train[state_rows, , drop = FALSE],
      train_df$issuer[state_rows],
      model_configs[[stage2_algo]] %||% list(),
      seed = seed
    )
  }

  list(
    hierarchy = hierarchy_config,
    issuer_to_state = issuer_to_state,
    state_model = state_model,
    global_issuer_model = global_issuer_model,
    local_models = local_models
  )
}

predict_plain_cascade <- function(cascade, x_test) {
  state_pred <- predict_classifier(cascade$state_model, x_test)
  predicted_states <- state_pred$labels
  predicted_issuers <- character(nrow(x_test))

  for (i in seq_len(nrow(x_test))) {
    state_name <- predicted_states[[i]]
    local_model <- cascade$local_models[[state_name]]
    local_pred <- predict_classifier(local_model, x_test[i, , drop = FALSE])
    predicted_issuers[[i]] <- local_pred$labels[[1L]]
  }

  list(
    states = predicted_states,
    issuers = predicted_issuers
  )
}

predict_with_fallback <- function(cascade, x_test, config) {
  state_pred <- predict_classifier(cascade$state_model, x_test)
  global_pred <- predict_classifier(cascade$global_issuer_model, x_test)

  state_probs <- state_pred$probabilities
  issuer_classes <- cascade$global_issuer_model$classes
  predicted_issuers <- character(nrow(x_test))
  predicted_states <- character(nrow(x_test))
  final_probs <- matrix(0, nrow = nrow(x_test), ncol = length(issuer_classes))
  colnames(final_probs) <- issuer_classes

  for (i in seq_len(nrow(x_test))) {
    row_state_probs <- state_probs[i, ]
    top_state_idx <- order(row_state_probs, decreasing = TRUE)
    best_state <- colnames(state_probs)[top_state_idx[1L]]
    predicted_states[[i]] <- best_state

    if (row_state_probs[top_state_idx[1L]] >= config$confidence_threshold) {
      local_pred <- predict_classifier(
        cascade$local_models[[best_state]],
        x_test[i, , drop = FALSE]
      )
      final_probs[i, ] <- embed_local_probabilities(local_pred$probabilities, issuer_classes)
      predicted_issuers[[i]] <- local_pred$labels[[1L]]
      next
    }

    if (config$top_k_states <= 1L) {
      final_probs[i, ] <- global_pred$probabilities[i, ]
      predicted_issuers[[i]] <- global_pred$labels[[i]]
      next
    }

    use_states <- colnames(state_probs)[top_state_idx[seq_len(min(config$top_k_states, ncol(state_probs)))]]
    combined <- global_pred$probabilities[i, ] * config$global_weight
    weight_sum <- config$global_weight

    for (state_name in use_states) {
      local_pred <- predict_classifier(
        cascade$local_models[[state_name]],
        x_test[i, , drop = FALSE]
      )
      local_probs <- embed_local_probabilities(local_pred$probabilities, issuer_classes)
      state_weight <- row_state_probs[state_name]
      combined <- combined + local_probs * state_weight
      weight_sum <- weight_sum + state_weight
    }

    combined <- combined / weight_sum
    final_probs[i, ] <- combined
    predicted_issuers[[i]] <- issuer_classes[[which.max(combined)]]
  }

  list(
    states = predicted_states,
    issuers = predicted_issuers,
    probabilities = final_probs
  )
}

embed_local_probabilities <- function(local_probabilities, global_classes) {
  if (is.null(dim(local_probabilities))) {
    local_probabilities <- matrix(local_probabilities, nrow = 1L)
  }
  embedded <- numeric(length(global_classes))
  names(embedded) <- global_classes
  local_classes <- colnames(local_probabilities)
  embedded[local_classes] <- local_probabilities[1L, ]
  embedded
}

tune_cascade_config <- function(cascade, x_val, val_df, tuning_config) {
  candidate_thresholds <- tuning_config$confidence_thresholds %||% c(0.55, 0.65, 0.75, 0.85)
  candidate_top_k <- tuning_config$top_k_states %||% c(1L, 2L)
  candidate_global_weights <- tuning_config$global_weights %||% c(0.25, 0.35, 0.5)

  best <- list(
    macro_f1 = -Inf,
    config = list(confidence_threshold = 0.75, top_k_states = 1L, global_weight = 0.35)
  )

  for (threshold in candidate_thresholds) {
    for (top_k in candidate_top_k) {
      weight_values <- if (top_k <= 1L) 0.35 else candidate_global_weights
      for (global_weight in weight_values) {
        config <- list(
          confidence_threshold = threshold,
          top_k_states = top_k,
          global_weight = global_weight
        )
        pred <- predict_with_fallback(cascade, x_val, config)
        metrics <- evaluate_issuer_predictions(
          truth_issuer = val_df$issuer,
          truth_state = val_df$state,
          predicted_issuer = pred$issuers,
          predicted_probs = pred$probabilities,
          prob_classes = cascade$global_issuer_model$classes,
          issuer_to_state = cascade$issuer_to_state
        )
        if (metrics$macro_f1 > best$macro_f1) {
          best <- list(macro_f1 = metrics$macro_f1, config = config)
        }
      }
    }
  }

  best$config
}

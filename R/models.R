fit_classifier <- function(algorithm, x, y, model_config = list(), seed = 42L) {
  labels <- factor(y)
  if (length(levels(labels)) == 1L) {
    return(list(
      algorithm = "constant",
      classes = levels(labels),
      label = levels(labels)[1L]
    ))
  }

  if (algorithm == "svm") {
    model <- suppressWarnings(
      LiblineaR::LiblineaR(
        data = x,
        target = labels,
        type = model_config$type %||% 0L,
        cost = model_config$cost %||% 1.0,
        bias = model_config$bias %||% TRUE,
        epsilon = model_config$epsilon %||% 0.01
      )
    )
    return(list(algorithm = algorithm, model = model, classes = levels(labels)))
  }

  if (algorithm == "random_forest") {
    feature_order <- order(Matrix::colSums(abs(x)), decreasing = TRUE)
    keep <- feature_order[seq_len(min(length(feature_order), model_config$max_text_features %||% 250L))]
    dense_x <- as.matrix(x[, keep, drop = FALSE])
    colnames(dense_x) <- paste0("f", keep)
    model <- randomForest::randomForest(
      x = as.data.frame(dense_x),
      y = labels,
      ntree = model_config$ntree %||% 300L,
      mtry = model_config$mtry %||% floor(sqrt(ncol(dense_x))),
      nodesize = model_config$nodesize %||% 1L,
      maxnodes = model_config$maxnodes %||% NULL
    )
    return(list(
      algorithm = algorithm,
      model = model,
      classes = levels(labels),
      feature_index = keep,
      feature_names = colnames(dense_x)
    ))
  }

  if (algorithm == "xgboost") {
    class_levels <- levels(labels)
    y_int <- as.integer(labels) - 1L
    dtrain <- xgboost::xgb.DMatrix(data = x, label = y_int)
    params <- list(
      objective = model_config$objective %||% "multi:softprob",
      eval_metric = model_config$eval_metric %||% "mlogloss",
      num_class = length(class_levels),
      eta = model_config$eta %||% 0.15,
      max_depth = model_config$max_depth %||% 8L,
      subsample = model_config$subsample %||% 0.8,
      colsample_bytree = model_config$colsample_bytree %||% 0.8,
      min_child_weight = model_config$min_child_weight %||% 1.0,
      gamma = model_config$gamma %||% 0.0,
      lambda = model_config$lambda %||% 1.0,
      alpha = model_config$alpha %||% 0.0
    )
    if (!is.null(model_config$max_leaves)) params$max_leaves <- model_config$max_leaves
    if (!is.null(model_config$tree_method)) params$tree_method <- model_config$tree_method
    model <- xgboost::xgb.train(
      params = params,
      data = dtrain,
      nrounds = model_config$nrounds %||% 160L,
      verbose = 0
    )
    return(list(algorithm = algorithm, model = model, classes = class_levels))
  }

  stop("Unsupported algorithm: ", algorithm)
}

predict_classifier <- function(model_object, x) {
  if (model_object$algorithm == "constant") {
    probs <- matrix(1, nrow = nrow(x), ncol = 1L)
    colnames(probs) <- model_object$classes
    return(list(labels = rep(model_object$label, nrow(x)), probabilities = probs))
  }

  if (model_object$algorithm == "svm") {
    pred <- suppressWarnings(
      predict(model_object$model, x, proba = TRUE, decisionValues = TRUE)
    )
    probs <- pred$probabilities
    probs <- align_probability_columns(probs, model_object$classes)
    return(list(labels = as.character(pred$predictions), probabilities = probs))
  }

  if (model_object$algorithm == "random_forest") {
    dense_x <- as.matrix(x[, model_object$feature_index, drop = FALSE])
    colnames(dense_x) <- model_object$feature_names
    probs <- predict(model_object$model, as.data.frame(dense_x), type = "prob")
    probs <- align_probability_columns(probs, model_object$classes)
    labels <- colnames(probs)[max.col(probs, ties.method = "first")]
    return(list(labels = labels, probabilities = probs))
  }

  if (model_object$algorithm == "xgboost") {
    dtest <- xgboost::xgb.DMatrix(data = x)
    raw_probs <- predict(model_object$model, dtest)
    probs <- matrix(raw_probs, ncol = length(model_object$classes), byrow = TRUE)
    colnames(probs) <- model_object$classes
    labels <- colnames(probs)[max.col(probs, ties.method = "first")]
    return(list(labels = labels, probabilities = probs))
  }

  stop("Unsupported algorithm: ", model_object$algorithm)
}

align_probability_columns <- function(probabilities, class_levels) {
  if (is.null(dim(probabilities))) {
    probabilities <- matrix(probabilities, ncol = length(class_levels))
  }
  output <- matrix(0, nrow = nrow(probabilities), ncol = length(class_levels))
  colnames(output) <- class_levels
  present <- intersect(colnames(probabilities), class_levels)
  output[, present] <- probabilities[, present, drop = FALSE]
  output
}

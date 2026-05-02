macro_f1_score <- function(truth, predicted) {
  classes <- sort(unique(c(truth, predicted)))
  f1_values <- numeric(length(classes))

  for (i in seq_along(classes)) {
    class_name <- classes[[i]]
    tp <- sum(truth == class_name & predicted == class_name)
    fp <- sum(truth != class_name & predicted == class_name)
    fn <- sum(truth == class_name & predicted != class_name)

    precision <- if ((tp + fp) == 0) 0 else tp / (tp + fp)
    recall <- if ((tp + fn) == 0) 0 else tp / (tp + fn)
    f1_values[[i]] <- if ((precision + recall) == 0) 0 else 2 * precision * recall / (precision + recall)
  }

  mean(f1_values)
}

macro_precision_score <- function(truth, predicted) {
  classes <- sort(unique(c(truth, predicted)))
  precision_values <- numeric(length(classes))

  for (i in seq_along(classes)) {
    class_name <- classes[[i]]
    tp <- sum(truth == class_name & predicted == class_name)
    fp <- sum(truth != class_name & predicted == class_name)
    precision_values[[i]] <- if ((tp + fp) == 0) 0 else tp / (tp + fp)
  }

  mean(precision_values)
}

macro_recall_score <- function(truth, predicted) {
  classes <- sort(unique(c(truth, predicted)))
  recall_values <- numeric(length(classes))

  for (i in seq_along(classes)) {
    class_name <- classes[[i]]
    tp <- sum(truth == class_name & predicted == class_name)
    fn <- sum(truth == class_name & predicted != class_name)
    recall_values[[i]] <- if ((tp + fn) == 0) 0 else tp / (tp + fn)
  }

  mean(recall_values)
}

weighted_f1_score <- function(truth, predicted) {
  classes <- sort(unique(c(truth, predicted)))
  supports <- vapply(classes, function(class_name) sum(truth == class_name), numeric(1L))
  if (sum(supports) == 0) {
    return(NA_real_)
  }

  f1_values <- vapply(classes, function(class_name) {
    tp <- sum(truth == class_name & predicted == class_name)
    fp <- sum(truth != class_name & predicted == class_name)
    fn <- sum(truth == class_name & predicted != class_name)
    precision <- if ((tp + fp) == 0) 0 else tp / (tp + fp)
    recall <- if ((tp + fn) == 0) 0 else tp / (tp + fn)
    if ((precision + recall) == 0) 0 else 2 * precision * recall / (precision + recall)
  }, numeric(1L))

  sum(f1_values * supports) / sum(supports)
}

balanced_accuracy_score <- function(truth, predicted) {
  macro_recall_score(truth, predicted)
}

per_class_metrics <- function(truth, predicted) {
  classes <- sort(unique(c(truth, predicted)))
  rows <- vector("list", length(classes))

  for (i in seq_along(classes)) {
    class_name <- classes[[i]]
    tp <- sum(truth == class_name & predicted == class_name)
    fp <- sum(truth != class_name & predicted == class_name)
    fn <- sum(truth == class_name & predicted != class_name)
    support <- sum(truth == class_name)

    precision <- if ((tp + fp) == 0) 0 else tp / (tp + fp)
    recall <- if ((tp + fn) == 0) 0 else tp / (tp + fn)
    f1 <- if ((precision + recall) == 0) 0 else 2 * precision * recall / (precision + recall)

    rows[[i]] <- data.table::data.table(
      class = class_name,
      support = support,
      tp = tp,
      fp = fp,
      fn = fn,
      precision = precision,
      recall = recall,
      f1 = f1
    )
  }

  data.table::rbindlist(rows)
}

confusion_table <- function(truth, predicted) {
  counts <- as.data.frame.matrix(table(truth = truth, predicted = predicted))
  counts$truth <- rownames(counts)
  data.table::melt(
    data.table::as.data.table(counts),
    id.vars = "truth",
    variable.name = "predicted",
    value.name = "count"
  )
}

multiclass_log_loss <- function(truth, probabilities, prob_classes, eps = 1e-15) {
  if (is.null(probabilities) || is.null(prob_classes)) {
    return(NA_real_)
  }
  truth_index <- match(truth, prob_classes)
  if (anyNA(truth_index)) {
    return(NA_real_)
  }
  clipped <- pmin(pmax(probabilities, eps), 1 - eps)
  row_probs <- clipped[cbind(seq_along(truth_index), truth_index)]
  -mean(log(row_probs))
}

top_k_accuracy <- function(truth, probabilities, prob_classes, k = 3L) {
  if (is.null(probabilities)) {
    return(NA_real_)
  }
  top_k <- t(apply(probabilities, 1L, function(row) {
    prob_classes[order(row, decreasing = TRUE)[seq_len(min(k, length(row)))]]
  }))
  mean(vapply(seq_along(truth), function(i) truth[[i]] %in% top_k[i, ], logical(1L)))
}

top_k_labels <- function(probabilities, prob_classes, k = 3L) {
  if (is.null(probabilities)) {
    return(rep(NA_character_, 0L))
  }
  top_k <- t(apply(probabilities, 1L, function(row) {
    prob_classes[order(row, decreasing = TRUE)[seq_len(min(k, length(row)))]]
  }))
  apply(top_k, 1L, paste, collapse = " | ")
}

evaluate_issuer_predictions <- function(truth_issuer, truth_state, predicted_issuer, predicted_probs, prob_classes, issuer_to_state) {
  predicted_state <- unname(issuer_to_state[predicted_issuer])
  wrong_issuer <- predicted_issuer != truth_issuer
  correct_state <- predicted_state == truth_state

  list(
    accuracy = mean(predicted_issuer == truth_issuer),
    macro_f1 = macro_f1_score(truth_issuer, predicted_issuer),
    weighted_f1 = weighted_f1_score(truth_issuer, predicted_issuer),
    macro_precision = macro_precision_score(truth_issuer, predicted_issuer),
    macro_recall = macro_recall_score(truth_issuer, predicted_issuer),
    balanced_accuracy = balanced_accuracy_score(truth_issuer, predicted_issuer),
    log_loss = multiclass_log_loss(truth_issuer, predicted_probs, prob_classes),
    top_3_accuracy = top_k_accuracy(truth_issuer, predicted_probs, prob_classes, k = 3L),
    wrong_issuer_correct_state = sum(wrong_issuer & correct_state, na.rm = TRUE),
    wrong_state_wrong_issuer = sum(wrong_issuer & !correct_state, na.rm = TRUE)
  )
}

evaluate_state_predictions <- function(truth_state, predicted_state) {
  list(
    accuracy = mean(predicted_state == truth_state),
    macro_f1 = macro_f1_score(truth_state, predicted_state),
    weighted_f1 = weighted_f1_score(truth_state, predicted_state),
    macro_precision = macro_precision_score(truth_state, predicted_state),
    macro_recall = macro_recall_score(truth_state, predicted_state),
    balanced_accuracy = balanced_accuracy_score(truth_state, predicted_state),
    log_loss = NA_real_,
    top_3_accuracy = NA_real_,
    wrong_issuer_correct_state = NA_integer_,
    wrong_state_wrong_issuer = sum(predicted_state != truth_state)
  )
}

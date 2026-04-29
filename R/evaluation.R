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

top_k_accuracy <- function(truth, probabilities, prob_classes, k = 3L) {
  if (is.null(probabilities)) {
    return(NA_real_)
  }
  top_k <- t(apply(probabilities, 1L, function(row) {
    prob_classes[order(row, decreasing = TRUE)[seq_len(min(k, length(row)))]]
  }))
  mean(vapply(seq_along(truth), function(i) truth[[i]] %in% top_k[i, ], logical(1L)))
}

evaluate_issuer_predictions <- function(truth_issuer, truth_state, predicted_issuer, predicted_probs, prob_classes, issuer_to_state) {
  predicted_state <- unname(issuer_to_state[predicted_issuer])
  wrong_issuer <- predicted_issuer != truth_issuer
  correct_state <- predicted_state == truth_state

  list(
    accuracy = mean(predicted_issuer == truth_issuer),
    macro_f1 = macro_f1_score(truth_issuer, predicted_issuer),
    top_3_accuracy = top_k_accuracy(truth_issuer, predicted_probs, prob_classes, k = 3L),
    wrong_issuer_correct_state = sum(wrong_issuer & correct_state, na.rm = TRUE),
    wrong_state_wrong_issuer = sum(wrong_issuer & !correct_state, na.rm = TRUE)
  )
}

evaluate_state_predictions <- function(truth_state, predicted_state) {
  list(
    accuracy = mean(predicted_state == truth_state),
    macro_f1 = macro_f1_score(truth_state, predicted_state),
    top_3_accuracy = NA_real_,
    wrong_issuer_correct_state = NA_integer_,
    wrong_state_wrong_issuer = sum(predicted_state != truth_state)
  )
}

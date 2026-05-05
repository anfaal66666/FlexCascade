#!/usr/bin/env Rscript
# Test Suite: Validate models and pipeline end-to-end

library(data.table)
library(randomForest)

cat("═══════════════════════════════════════════════════════════════\n")
cat("FLEXCASCADE MODEL TEST SUITE\n")
cat("═══════════════════════════════════════════════════════════════\n\n")

test_results <- list()
passed <- 0
failed <- 0

# Test 1: Model files exist
cat("[TEST 1] Model files exist... ")
model_paths <- c(
  "results/r_run_baseline_20260502/models/random_forest_flat_state_global.rds",
  "results/r_run_baseline_20260502/models/svm_GlobalState_Stage1State_cascade_run.rds"
)

all_exist <- all(file.exists(model_paths))
if (all_exist) {
  cat("✅ PASS\n")
  passed <- passed + 1
  test_results$model_files_exist <- "PASS"
} else {
  cat("❌ FAIL\n")
  failed <- failed + 1
  test_results$model_files_exist <- "FAIL"
  for (path in model_paths) {
    if (!file.exists(path)) cat(sprintf("  Missing: %s\n", path))
  }
}

# Test 2: Load best model
cat("[TEST 2] Load best model (Random Forest)... ")
tryCatch({
  rf_model <- readRDS("results/r_run_baseline_20260502/models/random_forest_flat_state_global.rds")
  if (class(rf_model)[1] == "randomForest" && !is.null(rf_model$forest)) {
    cat("✅ PASS\n")
    passed <- passed + 1
    test_results$load_rf_model <- "PASS"
  } else {
    cat("❌ FAIL (Invalid model object)\n")
    failed <- failed + 1
    test_results$load_rf_model <- "FAIL"
  }
}, error = function(e) {
  cat(sprintf("❌ FAIL (%s)\n", e$message))
  failed <<- failed + 1
  test_results$load_rf_model <<- "FAIL"
})

# Test 3: Check model classes
cat("[TEST 3] Model classes match training... ")
expected_classes <- c("alabama", "arizona", "california", "florida", "georgia",
                      "illinois", "michigan", "new_york", "north_carolina", "ohio",
                      "pennsylvania", "texas")
if (exists("rf_model")) {
  actual_classes <- levels(rf_model$forest$y)
  if (length(setdiff(expected_classes, actual_classes)) == 0) {
    cat("✅ PASS\n")
    passed <- passed + 1
    test_results$model_classes <- "PASS"
  } else {
    cat("❌ FAIL (Missing classes)\n")
    failed <- failed + 1
    test_results$model_classes <- "FAIL"
    cat(sprintf("  Expected: %d classes\n", length(expected_classes)))
    cat(sprintf("  Got: %d classes\n", length(actual_classes)))
  }
} else {
  cat("⚠️  SKIP (Model not loaded)\n")
  test_results$model_classes <- "SKIP"
}

# Test 4: Dataset files exist
cat("[TEST 4] Required dataset files exist... ")
dataset_files <- c(
  "data/processed/courtlistener_training.csv.gz",
  "results/r_run_baseline_20260502/split_summary.json",
  "results/r_run_baseline_20260502/metrics_summary.csv"
)

all_files_exist <- all(file.exists(dataset_files))
if (all_files_exist) {
  cat("✅ PASS\n")
  passed <- passed + 1
  test_results$dataset_files <- "PASS"
} else {
  cat("❌ FAIL\n")
  failed <- failed + 1
  test_results$dataset_files <- "FAIL"
  for (f in dataset_files) {
    if (!file.exists(f)) cat(sprintf("  Missing: %s\n", f))
  }
}

# Test 5: Load and validate dataset
cat("[TEST 5] Load and validate dataset... ")
tryCatch({
  dataset <- read.csv(gzfile("data/processed/courtlistener_training.csv.gz"))

  # Check required columns
  required_cols <- c("id", "title", "docket_number", "state", "issuer", "document", "timestamp")
  missing_cols <- setdiff(required_cols, names(dataset))

  if (length(missing_cols) == 0 && nrow(dataset) > 0) {
    cat("✅ PASS\n")
    passed <- passed + 1
    test_results$load_dataset <- "PASS"
    cat(sprintf("  Loaded: %d rows × %d columns\n", nrow(dataset), ncol(dataset)))
  } else {
    cat("❌ FAIL\n")
    failed <- failed + 1
    test_results$load_dataset <- "FAIL"
    if (length(missing_cols) > 0) {
      cat(sprintf("  Missing columns: %s\n", paste(missing_cols, collapse = ", ")))
    }
  }
}, error = function(e) {
  cat(sprintf("❌ FAIL (%s)\n", e$message))
  failed <<- failed + 1
  test_results$load_dataset <<- "FAIL"
})

# Test 6: Dataset completeness
cat("[TEST 6] Dataset field completeness... ")
if (exists("dataset")) {
  completeness_check <- all(
    !is.na(dataset$document),
    !is.na(dataset$state),
    !is.na(dataset$issuer),
    dataset$state != "",
    dataset$issuer != ""
  )

  if (completeness_check) {
    cat("✅ PASS\n")
    passed <- passed + 1
    test_results$data_completeness <- "PASS"
  } else {
    cat("⚠️  WARNING (Some missing values)\n")
    test_results$data_completeness <- "WARNING"
    missing_docs <- sum(is.na(dataset$document) | dataset$document == "")
    missing_state <- sum(is.na(dataset$state) | dataset$state == "")
    missing_issuer <- sum(is.na(dataset$issuer) | dataset$issuer == "")
    cat(sprintf("  Missing documents: %d\n", missing_docs))
    cat(sprintf("  Missing states: %d\n", missing_state))
    cat(sprintf("  Missing issuers: %d\n", missing_issuer))
  }
} else {
  cat("⚠️  SKIP (Dataset not loaded)\n")
  test_results$data_completeness <- "SKIP"
}

# Test 7: Metrics files exist and valid
cat("[TEST 7] Metrics files valid... ")
tryCatch({
  metrics <- read.csv("results/r_run_baseline_20260502/metrics_summary.csv")

  if (nrow(metrics) >= 12 && "accuracy" %in% names(metrics)) {
    cat("✅ PASS\n")
    passed <- passed + 1
    test_results$metrics_valid <- "PASS"
    cat(sprintf("  Loaded: %d model configurations\n", nrow(metrics)))

    # Check accuracy ranges
    min_acc <- min(metrics$accuracy, na.rm = TRUE)
    max_acc <- max(metrics$accuracy, na.rm = TRUE)
    if (min_acc >= 0 && max_acc <= 1) {
      cat(sprintf("  Accuracy range: %.2f%% - %.2f%%\n", 100*min_acc, 100*max_acc))
    }
  } else {
    cat("❌ FAIL\n")
    failed <- failed + 1
    test_results$metrics_valid <- "FAIL"
  }
}, error = function(e) {
  cat(sprintf("❌ FAIL (%s)\n", e$message))
  failed <<- failed + 1
  test_results$metrics_valid <<- "FAIL"
})

# Test 8: Best model achieves expected accuracy
cat("[TEST 8] Best model accuracy >= 97%... ")
if (exists("metrics")) {
  best_accuracy <- max(metrics$accuracy, na.rm = TRUE)

  if (best_accuracy >= 0.97) {
    cat("✅ PASS\n")
    passed <- passed + 1
    test_results$accuracy_threshold <- "PASS"
    cat(sprintf("  Best accuracy: %.2f%%\n", 100 * best_accuracy))
  } else {
    cat("❌ FAIL\n")
    failed <- failed + 1
    test_results$accuracy_threshold <- "FAIL"
    cat(sprintf("  Best accuracy: %.2f%% (expected >= 97%%)\n", 100 * best_accuracy))
  }
} else {
  cat("⚠️  SKIP (Metrics not loaded)\n")
  test_results$accuracy_threshold <- "SKIP"
}

# Test 9: Sample prediction
cat("[TEST 9] Sample prediction works... ")
if (exists("rf_model") && exists("dataset")) {
  tryCatch({
    # Create simple feature matrix (random for now)
    sample_features <- matrix(rnorm(12000), nrow = 1, ncol = 12000)

    prediction <- predict(rf_model, as.data.frame(sample_features))

    if (!is.na(prediction[1]) && prediction[1] %in% levels(rf_model$forest$y)) {
      cat("✅ PASS\n")
      passed <- passed + 1
      test_results$sample_prediction <- "PASS"
      cat(sprintf("  Predicted class: %s\n", as.character(prediction[1])))
    } else {
      cat("❌ FAIL (Invalid prediction)\n")
      failed <- failed + 1
      test_results$sample_prediction <- "FAIL"
    }
  }, error = function(e) {
    cat(sprintf("❌ FAIL (%s)\n", e$message))
    failed <<- failed + 1
    test_results$sample_prediction <<- "FAIL"
  })
} else {
  cat("⚠️  SKIP (Model or data not loaded)\n")
  test_results$sample_prediction <- "SKIP"
}

# Test 10: Documentation files exist
cat("[TEST 10] Documentation files exist... ")
doc_files <- c(
  "MODEL_TRAINING_REPORT.md",
  "MODEL_EVALUATION_REPORT.md",
  "DEPLOYMENT_GUIDE.md",
  "results/README.md"
)

all_docs_exist <- all(file.exists(doc_files))
if (all_docs_exist) {
  cat("✅ PASS\n")
  passed <- passed + 1
  test_results$documentation <- "PASS"
} else {
  cat("⚠️  WARNING (Some docs missing)\n")
  test_results$documentation <- "WARNING"
  for (doc in doc_files) {
    if (!file.exists(doc)) cat(sprintf("  Missing: %s\n", doc))
  }
}

# Summary
cat("\n")
cat("═══════════════════════════════════════════════════════════════\n")
cat("TEST RESULTS SUMMARY\n")
cat("═══════════════════════════════════════════════════════════════\n\n")

for (test_name in names(test_results)) {
  status <- test_results[[test_name]]
  symbol <- if (status == "PASS") "✅" else if (status == "FAIL") "❌" else "⚠️"
  cat(sprintf("%s %-40s %s\n", symbol, test_name, status))
}

cat("\n")
cat(sprintf("Passed:  %d / 10\n", passed))
cat(sprintf("Failed:  %d / 10\n", failed))
cat(sprintf("Skipped: %d / 10\n", 10 - passed - failed))

# Final verdict
if (failed == 0) {
  cat("\n✅ ALL TESTS PASSED - Ready for production!\n")
  exit_code <- 0
} else if (failed <= 2) {
  cat("\n⚠️  SOME TESTS FAILED - Review above\n")
  exit_code <- 1
} else {
  cat("\n❌ CRITICAL FAILURES - Do not deploy\n")
  exit_code <- 2
}

# Save results
test_summary <- data.frame(
  Test = names(test_results),
  Result = unlist(test_results)
)
write.csv(test_summary, "results/test_results.csv", row.names = FALSE)

cat("\nTest results saved to: results/test_results.csv\n")
quit(status = exit_code)

#!/usr/bin/env Rscript
# Benchmark Script: Compare new model/data against baseline

library(data.table)
library(ggplot2)

cat("[BENCHMARK] Starting comparison...\n")

# Parse arguments
args <- commandArgs(trailingOnly = TRUE)
baseline_metrics <- "results/r_run_baseline_20260502/metrics_summary.csv"
new_metrics <- "results/r_run/metrics_summary.csv"
output_dir <- "results/benchmarks"

if (length(args) >= 1) baseline_metrics <- args[1]
if (length(args) >= 2) new_metrics <- args[2]
if (length(args) >= 3) output_dir <- args[3]

dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

# Load metrics
cat(sprintf("[BENCHMARK] Loading baseline from: %s\n", baseline_metrics))
baseline <- as.data.table(read.csv(baseline_metrics))

cat(sprintf("[BENCHMARK] Loading new metrics from: %s\n", new_metrics))
if (!file.exists(new_metrics)) {
  cat(sprintf("[ERROR] New metrics file not found: %s\n", new_metrics))
  quit(status = 1)
}
new <- as.data.table(read.csv(new_metrics))

# Comparison function
compare_models <- function(baseline_dt, new_dt, metric = "accuracy") {
  # Extract best performing model from each
  baseline_best <- baseline_dt[which.max(accuracy)]
  new_best <- new_dt[which.max(accuracy)]

  comparison <- data.frame(
    Metric = c("Accuracy", "Macro F1", "Weighted F1", "Macro Precision", "Macro Recall"),
    Baseline = c(
      sprintf("%.2f%%", 100 * baseline_best$accuracy),
      sprintf("%.3f", baseline_best$macro_f1),
      sprintf("%.3f", baseline_best$weighted_f1),
      sprintf("%.3f", baseline_best$macro_precision),
      sprintf("%.3f", baseline_best$macro_recall)
    ),
    New = c(
      sprintf("%.2f%%", 100 * new_best$accuracy),
      sprintf("%.3f", new_best$macro_f1),
      sprintf("%.3f", new_best$weighted_f1),
      sprintf("%.3f", new_best$macro_precision),
      sprintf("%.3f", new_best$macro_recall)
    ),
    Difference = c(
      sprintf("%+.2f pp", 100 * (new_best$accuracy - baseline_best$accuracy)),
      sprintf("%+.3f", new_best$macro_f1 - baseline_best$macro_f1),
      sprintf("%+.3f", new_best$weighted_f1 - baseline_best$weighted_f1),
      sprintf("%+.3f", new_best$macro_precision - baseline_best$macro_precision),
      sprintf("%+.3f", new_best$macro_recall - baseline_best$macro_recall)
    )
  )

  return(list(comparison = comparison, baseline_best = baseline_best, new_best = new_best))
}

comparison_result <- compare_models(baseline, new)
comparison_table <- comparison_result$comparison
baseline_best <- comparison_result$baseline_best
new_best <- comparison_result$new_best

# Print results
cat("\n")
cat("═══════════════════════════════════════════════════════════════\n")
cat("BENCHMARK COMPARISON RESULTS\n")
cat("═══════════════════════════════════════════════════════════════\n\n")
print(comparison_table)

# Verdict
accuracy_diff <- 100 * (new_best$accuracy - baseline_best$accuracy)
if (accuracy_diff > 1) {
  verdict <- "✅ IMPROVEMENT - New model is better!"
  status_color <- "green"
} else if (accuracy_diff > -1) {
  verdict <- "⚠️  SIMILAR - Within 1% of baseline"
  status_color <- "yellow"
} else if (accuracy_diff > -3) {
  verdict <- "⚠️  DEGRADATION - Slight decline (< 3%)"
  status_color <- "orange"
} else {
  verdict <- "❌ SIGNIFICANT DECLINE - > 3% worse"
  status_color <- "red"
}

cat("\n")
cat(sprintf("Verdict: %s\n", verdict))
cat(sprintf("Accuracy Difference: %+.2f percentage points\n", accuracy_diff))

# Detailed comparison by approach
cat("\n\nDETAILED COMPARISON BY APPROACH:\n")
cat("─────────────────────────────────────────────────────────────\n")

approaches <- unique(baseline$system)
detailed_comparison <- list()

for (approach in approaches) {
  baseline_row <- baseline[system == approach & algorithm == baseline_best$algorithm]
  new_row <- new[system == approach & algorithm == new_best$algorithm]

  if (nrow(baseline_row) > 0 && nrow(new_row) > 0) {
    diff <- 100 * (new_row$accuracy[1] - baseline_row$accuracy[1])
    detailed_comparison[[approach]] <- data.frame(
      Approach = approach,
      Baseline_Acc = sprintf("%.2f%%", 100 * baseline_row$accuracy[1]),
      New_Acc = sprintf("%.2f%%", 100 * new_row$accuracy[1]),
      Difference = sprintf("%+.2f pp", diff),
      Status = ifelse(diff > 0, "✅", ifelse(diff > -1, "⚠️", "❌"))
    )
  }
}

detailed_df <- do.call(rbind, detailed_comparison)
rownames(detailed_df) <- NULL
print(detailed_df)

# Per-algorithm comparison
cat("\n\nPER-ALGORITHM COMPARISON:\n")
cat("─────────────────────────────────────────────────────────────\n")

algorithms <- unique(baseline$algorithm)
algo_comparison <- list()

for (algo in algorithms) {
  baseline_algo <- baseline[algorithm == algo]
  new_algo <- new[algorithm == algo]

  if (nrow(baseline_algo) > 0) {
    best_baseline <- baseline_algo[which.max(accuracy)]
    best_new <- if (nrow(new_algo) > 0) new_algo[which.max(accuracy)] else NA

    if (!is.na(best_new$accuracy[1])) {
      diff <- 100 * (best_new$accuracy[1] - best_baseline$accuracy[1])
      algo_comparison[[algo]] <- data.frame(
        Algorithm = algo,
        Baseline = sprintf("%.2f%%", 100 * best_baseline$accuracy[1]),
        New = sprintf("%.2f%%", best_new$accuracy[1] * 100),
        Difference = sprintf("%+.2f pp", diff)
      )
    }
  }
}

algo_df <- do.call(rbind, algo_comparison)
rownames(algo_df) <- NULL
print(algo_df)

# Data quality checks
cat("\n\nDATA QUALITY CHECKS:\n")
cat("─────────────────────────────────────────────────────────────\n")

quality_checks <- list(
  Missing_Values = list(
    baseline = sum(is.na(baseline)),
    new = sum(is.na(new)),
    status = if (sum(is.na(new)) <= sum(is.na(baseline))) "✅" else "⚠️"
  ),
  Total_Models = list(
    baseline = nrow(baseline),
    new = nrow(new),
    status = if (nrow(new) >= nrow(baseline)) "✅" else "⚠️"
  ),
  Metric_Coverage = list(
    baseline = sum(!is.na(baseline$accuracy)),
    new = sum(!is.na(new$accuracy)),
    status = if (sum(!is.na(new$accuracy)) == nrow(new)) "✅" else "⚠️"
  )
)

for (check in names(quality_checks)) {
  ch <- quality_checks[[check]]
  cat(sprintf("%s:\n", check))
  cat(sprintf("  Baseline: %s (%s)\n", ch$baseline, ch$status))
  cat(sprintf("  New: %s\n", ch$new))
}

# Export results
cat("\n\nEXPORTING RESULTS...\n")

# Save comparison table
write.csv(comparison_table,
          file.path(output_dir, "comparison_summary.csv"),
          row.names = FALSE)

write.csv(detailed_df,
          file.path(output_dir, "detailed_comparison.csv"),
          row.names = FALSE)

write.csv(algo_df,
          file.path(output_dir, "algorithm_comparison.csv"),
          row.names = FALSE)

# Create visualization
p <- ggplot(data.frame(
  Model = c("Baseline", "New"),
  Accuracy = c(baseline_best$accuracy, new_best$accuracy)
), aes(x = Model, y = 100 * Accuracy, fill = Model)) +
  geom_bar(stat = "identity") +
  geom_text(aes(label = sprintf("%.2f%%", 100 * Accuracy)),
            vjust = -0.5, size = 5) +
  ylim(0, 100) +
  labs(title = "Baseline vs New Model Accuracy",
       y = "Accuracy (%)",
       x = "") +
  theme_minimal() +
  theme(legend.position = "none")

ggsave(file.path(output_dir, "accuracy_comparison.png"), p, width = 8, height = 6)

# Generate report
report <- sprintf(
  "BENCHMARK REPORT
Generated: %s

SUMMARY
═══════════════════════════════════════════════════════════════

Best Baseline Model:  %s (%s)
Best New Model:       %s (%s)
Accuracy Difference:  %+.2f pp

VERDICT: %s

METRICS COMPARISON
─────────────────────────────────────────────────────────────
%s
%s
%s

DETAILED RESULTS
─────────────────────────────────────────────────────────────
Baseline: %s
New: %s

STATUS
─────────────────────────────────────────────────────────────
✅ Benchmark complete - see %s for detailed results

Files saved:
  - comparison_summary.csv
  - detailed_comparison.csv
  - algorithm_comparison.csv
  - accuracy_comparison.png
  - benchmark_report.txt
",
  Sys.time(),
  baseline_best$algorithm, sprintf("%.2f%%", 100 * baseline_best$accuracy),
  new_best$algorithm, sprintf("%.2f%%", 100 * new_best$accuracy),
  accuracy_diff,
  verdict,
  sprintf("Accuracy:    %.2f%% → %.2f%% (%+.2f pp)",
          100 * baseline_best$accuracy, 100 * new_best$accuracy, accuracy_diff),
  sprintf("Macro F1:    %.3f → %.3f (%+.3f)",
          baseline_best$macro_f1, new_best$macro_f1,
          new_best$macro_f1 - baseline_best$macro_f1),
  sprintf("Weighted F1: %.3f → %.3f (%+.3f)",
          baseline_best$weighted_f1, new_best$weighted_f1,
          new_best$weighted_f1 - baseline_best$weighted_f1),
  baseline_metrics,
  new_metrics,
  output_dir
)

writeLines(report, file.path(output_dir, "benchmark_report.txt"))

cat(sprintf("\n✅ Benchmark complete!\n"))
cat(sprintf("Results saved to: %s\n", output_dir))

#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(data.table)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2L) {
  stop("Usage: Rscript scripts/build_comparison_table.R <output.csv> <result_dir_1> [result_dir_2 ...]")
}

output_path <- args[[1L]]
result_dirs <- args[-1L]

tables <- list()
for (dir_path in result_dirs) {
  metrics_path <- file.path(dir_path, "metrics_by_split.csv")
  if (!file.exists(metrics_path)) {
    next
  }
  dt <- fread(metrics_path)
  dt[, result_dir := basename(dir_path)]
  tables[[length(tables) + 1L]] <- dt
}

combined <- rbindlist(tables, fill = TRUE)
fwrite(combined, output_path)
cat(sprintf("Wrote %s\n", output_path))

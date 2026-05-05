repos <- "https://cloud.r-project.org"
packages <- c("data.table", "jsonlite", "Matrix", "randomForest", "e1071", "LiblineaR", "xgboost")
missing <- packages[!vapply(packages, requireNamespace, logical(1L), quietly = TRUE)]
if (length(missing) > 0L) {
  install.packages(missing, repos = repos)
}
cat("R dependencies are ready.\n")

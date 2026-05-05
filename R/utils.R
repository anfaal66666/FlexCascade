`%||%` <- function(lhs, rhs) {
  if (is.null(lhs) || length(lhs) == 0) {
    return(rhs)
  }
  lhs
}

ensure_dir <- function(path) {
  dir.create(path, recursive = TRUE, showWarnings = FALSE)
  invisible(path)
}

normalize_text <- function(x) {
  x <- ifelse(is.na(x), "", as.character(x))
  x <- gsub("[[:space:]]+", " ", x, perl = TRUE)
  trimws(x)
}

clean_text <- function(x) {
  x <- tolower(normalize_text(x))
  x <- gsub("[^[:alnum:][:space:]]+", " ", x, perl = TRUE)
  x <- gsub("[[:space:]]+", " ", x, perl = TRUE)
  trimws(x)
}

write_json_file <- function(object, path) {
  jsonlite::write_json(object, path = path, auto_unbox = TRUE, pretty = TRUE)
}

parse_cli_args <- function(args) {
  config <- list(
    algorithms = c("svm", "random_forest", "xgboost"),
    output_dir = "results/r_run",
    cache_dir = "data/hf_cache",
    processed_dir = "data/processed",
    feature_cache_dir = "data/feature_cache",
    python_cmd = "/opt/anaconda3/bin/python",
    dataset_source = "hf_case_law",
    courtlistener_dir = "data/courtlistener",
    split = "us",
    max_rows = 5000L,
    seed = 42L,
    min_issuer_count = 5L,
    config_file = NULL,
    state_subset = NULL,
    top_n_states = NULL,
    include_states = NULL
  )

  i <- 1L
  while (i <= length(args)) {
    key <- args[[i]]
    value <- if (i < length(args)) args[[i + 1L]] else NULL

    if (key == "--algorithms") {
      values <- character()
      j <- i + 1L
      while (j <= length(args) && !startsWith(args[[j]], "--")) {
        values <- c(values, args[[j]])
        j <- j + 1L
      }
      config$algorithms <- values
      i <- j - 1L
    } else if (key == "--output-dir") {
      config$output_dir <- value
      i <- i + 1L
    } else if (key == "--cache-dir") {
      config$cache_dir <- value
      i <- i + 1L
    } else if (key == "--processed-dir") {
      config$processed_dir <- value
      i <- i + 1L
    } else if (key == "--feature-cache-dir") {
      config$feature_cache_dir <- value
      i <- i + 1L
    } else if (key == "--python-cmd") {
      config$python_cmd <- value
      i <- i + 1L
    } else if (key == "--dataset-source") {
      config$dataset_source <- value
      i <- i + 1L
    } else if (key == "--courtlistener-dir") {
      config$courtlistener_dir <- value
      i <- i + 1L
    } else if (key == "--split") {
      config$split <- value
      i <- i + 1L
    } else if (key == "--max-rows") {
      config$max_rows <- as.integer(value)
      i <- i + 1L
    } else if (key == "--seed") {
      config$seed <- as.integer(value)
      i <- i + 1L
    } else if (key == "--min-issuer-count") {
      config$min_issuer_count <- as.integer(value)
      i <- i + 1L
    } else if (key == "--config") {
      config$config_file <- value
      i <- i + 1L
    } else if (key == "--help") {
      cat(
        paste(
          "Usage:",
          "Rscript run_experiment.R [--algorithms svm random_forest xgboost]",
          "[--output-dir results/r_run]",
          "[--cache-dir data/hf_cache]",
          "[--processed-dir data/processed]",
          "[--python-cmd /opt/anaconda3/bin/python]",
          "[--dataset-source hf_case_law|courtlistener]",
          "[--courtlistener-dir data/courtlistener]",
          "[--split us]",
          "[--max-rows 5000]",
          "[--seed 42]",
          "[--min-issuer-count 5]",
          "[--config config/default_experiment.json]",
          sep = "\n"
        )
      )
      quit(save = "no", status = 0L)
    }
    i <- i + 1L
  }
  config
}

deep_merge <- function(base, override) {
  if (!is.list(override)) {
    return(override)
  }
  result <- base
  for (name in names(override)) {
    if (is.list(result[[name]]) && is.list(override[[name]])) {
      result[[name]] <- deep_merge(result[[name]], override[[name]])
    } else {
      result[[name]] <- override[[name]]
    }
  }
  result
}

default_experiment_config <- function() {
  list(
    output_dir = "results/r_run",
    cache_dir = "data/hf_cache",
    processed_dir = "data/processed",
    feature_cache_dir = "data/feature_cache",
    python_cmd = "/opt/anaconda3/bin/python",
    dataset = list(
      source = "hf_case_law",
      prepared_path = NULL,
      courtlistener_dir = "data/courtlistener",
      courtlistener_aggregate_level = "cluster",
      courtlistener_require_state = TRUE,
      sample_fraction = NULL
    ),
    split = "us",
    max_rows = 5000L,
    seed = 42L,
    min_issuer_count = 5L,
    state_subset = NULL,
    top_n_states = NULL,
    include_states = NULL,
    embedding = list(
      strategy = "tfidf",
      max_features = NULL,
      min_df = 2L,
      max_doc_tokens = NULL,
      use_bigrams = TRUE,
      embedding_path = NULL,
      embedding_dim = 300L,
      hybrid_weight = 0.5
    ),
    hierarchy = list(
      stage1_model = "svm",
      stage2_model = "svm",
      fallback_model = "svm"
    ),
    tuning = list(
      confidence_thresholds = c(0.55, 0.65, 0.75, 0.85),
      top_k_states = c(1L, 2L),
      global_weights = c(0.25, 0.35, 0.5)
    ),
    models = list(
      svm = list(
        type = 0L,
        cost = 1.0,
        bias = TRUE
      ),
      random_forest = list(
        ntree = 300L,
        max_text_features = 250L
      ),
      xgboost = list(
        objective = "multi:softprob",
        eval_metric = "mlogloss",
        eta = 0.15,
        max_depth = 8L,
        subsample = 0.8,
        colsample_bytree = 0.8,
        nrounds = 160L
      )
    ),
    comparison_runs = NULL
  )
}

resolve_config <- function(cli_config) {
  config <- default_experiment_config()
  config$output_dir <- cli_config$output_dir
  config$cache_dir <- cli_config$cache_dir
  config$processed_dir <- cli_config$processed_dir
  config$feature_cache_dir <- cli_config$feature_cache_dir
  config$python_cmd <- cli_config$python_cmd
  config$dataset$source <- cli_config$dataset_source
  config$dataset$courtlistener_dir <- cli_config$courtlistener_dir
  config$split <- cli_config$split
  config$max_rows <- cli_config$max_rows
  config$seed <- cli_config$seed
  config$min_issuer_count <- cli_config$min_issuer_count
  config$state_subset <- cli_config$state_subset
  config$top_n_states <- cli_config$top_n_states
  config$include_states <- cli_config$include_states

  if (!is.null(cli_config$config_file)) {
    file_config <- jsonlite::read_json(cli_config$config_file, simplifyVector = FALSE)
    config <- deep_merge(config, file_config)
  } else {
    config$comparison_runs <- lapply(cli_config$algorithms, function(algo) {
      list(
        name = algo,
        hierarchy = list(
          stage1_model = algo,
          stage2_model = algo,
          fallback_model = algo
        )
      )
    })
  }

  config
}

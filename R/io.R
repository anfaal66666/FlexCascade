build_processed_dataset_path <- function(config, prefix) {
  ensure_dir(config$processed_dir)
  sample_tag <- if (is.null(config$max_rows)) "full" else paste0("n", config$max_rows)
  state_tag <- "allstates"
  if (!is.null(config$state_subset) && length(config$state_subset) > 0L) {
    state_tag <- paste0("states", length(config$state_subset))
  } else if (!is.null(config$top_n_states)) {
    state_tag <- paste0("top", config$top_n_states)
  }
  file.path(
    config$processed_dir,
    sprintf("%s_%s_%s_seed%s.csv.gz", prefix, sample_tag, state_tag, config$seed)
  )
}

ensure_hf_case_law_export <- function(config) {
  output_path <- build_processed_dataset_path(config, "hf_case_law")

  if (!file.exists(output_path)) {
    cmd <- c(
      "scripts/export_hf_case_law.py",
      "--output", output_path,
      "--cache-dir", config$cache_dir,
      "--split", config$split,
      "--seed", as.character(config$seed)
    )
    if (!is.null(config$max_rows)) {
      cmd <- c(cmd, "--max-rows", as.character(config$max_rows))
    }
    if (!is.null(config$state_subset) && length(config$state_subset) > 0L) {
      cmd <- c(cmd, "--states", unlist(config$state_subset))
    }
    status <- system2(config$python_cmd %||% "python3", cmd)
    if (!identical(status, 0L)) {
      stop("Python export helper failed.")
    }
  }

  output_path
}

ensure_courtlistener_export <- function(config) {
  prepared_path <- config$dataset$prepared_path %||% build_processed_dataset_path(config, "courtlistener_case_law")
  if (file.exists(prepared_path)) {
    return(prepared_path)
  }

  cmd <- c(
    "scripts/prepare_courtlistener_dataset.py",
    "--input-dir", config$dataset$courtlistener_dir %||% "data/courtlistener",
    "--output", prepared_path,
    "--seed", as.character(config$seed),
    "--aggregate-level", config$dataset$courtlistener_aggregate_level %||% "cluster"
  )
  if (!is.null(config$dataset$sample_fraction)) {
    cmd <- c(cmd, "--sample-frac", as.character(config$dataset$sample_fraction))
  }
  if (!is.null(config$max_rows)) {
    cmd <- c(cmd, "--max-rows", as.character(config$max_rows))
  }
  if (!is.null(config$state_subset) && length(config$state_subset) > 0L) {
    cmd <- c(cmd, "--states", unlist(config$state_subset))
  } else if (!is.null(config$top_n_states)) {
    cmd <- c(cmd, "--top-n-states", as.character(config$top_n_states))
    include_states <- config$include_states %||% character()
    if (length(include_states) > 0L) {
      cmd <- c(cmd, "--include-states", unlist(include_states))
    }
  }
  if (isTRUE(config$dataset$courtlistener_require_state %||% TRUE)) {
    cmd <- c(cmd, "--require-state")
  }
  status <- system2(config$python_cmd %||% "python3", cmd)
  if (!identical(status, 0L)) {
    stop("CourtListener preparation helper failed.")
  }
  prepared_path
}

read_prepared_table <- function(path) {
  if (grepl("\\.gz$", path)) {
    data.table::as.data.table(
      utils::read.csv(gzfile(path), stringsAsFactors = FALSE)
    )
  } else {
    data.table::fread(path, encoding = "UTF-8")
  }
}

prepare_common_frame <- function(frame, config) {
  required <- c("title", "citation", "docket_number", "state", "issuer", "document", "timestamp")
  missing <- setdiff(required, names(frame))
  if (length(missing) > 0L) {
    stop("Missing required columns: ", paste(missing, collapse = ", "))
  }

  frame[, title := normalize_text(title)]
  frame[, citation := normalize_text(citation)]
  frame[, docket_number := normalize_text(docket_number)]
  frame[, state := normalize_text(state)]
  frame[, issuer := normalize_text(issuer)]
  frame[, document := normalize_text(document)]
  frame[, timestamp := as.POSIXct(timestamp, tz = "UTC")]
  frame <- frame[document != "" & state != "" & issuer != "" & !is.na(timestamp)]

  if (!is.null(config$state_subset) && length(config$state_subset) > 0L) {
    state_subset <- unique(normalize_text(unlist(config$state_subset)))
    frame <- frame[state %in% state_subset]
  } else if (!is.null(config$top_n_states)) {
    state_counts <- frame[, .N, by = state][order(-N)]
    top_states <- state_counts[seq_len(min(config$top_n_states, .N)), state]
    required_states <- unique(normalize_text(unlist(config$include_states %||% character())))
    chosen_states <- unique(c(top_states, required_states))
    frame <- frame[state %in% chosen_states]
  }

  issuer_counts <- frame[, .N, by = issuer]
  keep_issuers <- issuer_counts[N >= config$min_issuer_count, issuer]
  frame <- frame[issuer %in% keep_issuers]

  frame[, year := as.integer(format(timestamp, "%Y"))]
  frame[, document_length := nchar(document)]
  frame[, title_length := nchar(title)]
  frame[, citation_present := as.integer(citation != "")]
  frame[, docket_present := as.integer(docket_number != "")]
  frame[, uppercase_ratio := uppercase_ratio(document)]
  frame[, digit_ratio := digit_ratio(document)]
  frame[, punctuation_ratio := punctuation_ratio(document)]
  frame[, model_text := paste(
    ifelse(title == "", "", paste("title", title)),
    ifelse(citation == "", "", paste("citation", citation)),
    ifelse(docket_number == "", "", paste("docket", docket_number)),
    paste("document", document)
  )]

  issuer_state <- unique(frame[, .(issuer, state)])
  inconsistent <- issuer_state[, .N, by = issuer][N > 1L]
  if (nrow(inconsistent) > 0L) {
    stop("Issuer to state mapping is inconsistent for some issuers.")
  }

  list(
    frame = frame,
    issuer_to_state = setNames(issuer_state$state, issuer_state$issuer)
  )
}

load_case_law_data <- function(config) {
  dataset_source <- config$dataset$source %||% "hf_case_law"
  if (identical(dataset_source, "hf_case_law")) {
    export_path <- ensure_hf_case_law_export(config)
  } else if (identical(dataset_source, "courtlistener")) {
    export_path <- ensure_courtlistener_export(config)
  } else {
    stop("Unsupported dataset source: ", dataset_source)
  }

  prepare_common_frame(read_prepared_table(export_path), config)
}

uppercase_ratio <- function(text_vec) {
  vapply(text_vec, function(text) {
    chars <- strsplit(text, "", fixed = TRUE)[[1L]]
    if (length(chars) == 0L) {
      return(0)
    }
    letters <- grepl("[A-Za-z]", chars)
    if (!any(letters)) {
      return(0)
    }
    sum(grepl("[A-Z]", chars)) / sum(letters)
  }, numeric(1L))
}

digit_ratio <- function(text_vec) {
  vapply(text_vec, function(text) {
    if (!nzchar(text)) {
      return(0)
    }
    chars <- strsplit(text, "", fixed = TRUE)[[1L]]
    sum(grepl("[0-9]", chars)) / length(chars)
  }, numeric(1L))
}

punctuation_ratio <- function(text_vec) {
  vapply(text_vec, function(text) {
    if (!nzchar(text)) {
      return(0)
    }
    chars <- strsplit(text, "", fixed = TRUE)[[1L]]
    sum(grepl("[[:punct:]]", chars)) / length(chars)
  }, numeric(1L))
}

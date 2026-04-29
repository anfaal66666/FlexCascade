ensure_case_law_export <- function(config) {
  ensure_dir(config$processed_dir)
  sample_tag <- if (is.null(config$max_rows)) "full" else paste0("n", config$max_rows)
  output_path <- file.path(
    config$processed_dir,
    sprintf("hf_case_law_%s_seed%s.csv.gz", sample_tag, config$seed)
  )

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
    status <- system2("python3", cmd)
    if (!identical(status, 0L)) {
      stop("Python export helper failed.")
    }
  }

  output_path
}

load_case_law_data <- function(config) {
  export_path <- ensure_case_law_export(config)
  if (grepl("\\.gz$", export_path)) {
    frame <- data.table::as.data.table(
      utils::read.csv(gzfile(export_path), stringsAsFactors = FALSE)
    )
  } else {
    frame <- data.table::fread(export_path, encoding = "UTF-8")
  }

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

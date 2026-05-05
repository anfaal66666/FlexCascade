NUMERIC_COLUMNS <- c(
  "year",
  "document_length",
  "title_length",
  "citation_present",
  "docket_present",
  "uppercase_ratio",
  "digit_ratio",
  "punctuation_ratio"
)

feature_settings_for_model <- function(algorithm, config) {
  defaults <- list(
    svm = list(max_features = 12000L, max_doc_tokens = 1500L),
    random_forest = list(max_features = 400L, max_doc_tokens = 800L),
    xgboost = list(max_features = 6000L, max_doc_tokens = 1200L)
  )
  settings <- defaults[[algorithm]] %||% list(max_features = 6000L, max_doc_tokens = 1200L)
  if (!is.null(config$embedding$max_features)) {
    settings$max_features <- as.integer(config$embedding$max_features)
  }
  if (!is.null(config$embedding$max_doc_tokens)) {
    settings$max_doc_tokens <- as.integer(config$embedding$max_doc_tokens)
  }
  settings
}

fit_feature_pipeline <- function(train_df, algorithm, config) {
  strategy <- config$embedding$strategy %||% "tfidf"
  settings <- feature_settings_for_model(algorithm, config)

  numeric_stats <- fit_numeric_scaler(train_df[, ..NUMERIC_COLUMNS])
  text_clean <- vapply(train_df$model_text, clean_text, character(1L))

  if (strategy == "tfidf") {
    tfidf <- fit_tfidf_vectorizer(
      text_clean,
      max_features = settings$max_features,
      min_df = config$embedding$min_df %||% 2L,
      max_doc_tokens = settings$max_doc_tokens,
      use_bigrams = isTRUE(config$embedding$use_bigrams)
    )
    return(list(strategy = strategy, tfidf = tfidf, numeric_stats = numeric_stats))
  }

  if (strategy %in% c("word2vec", "glove", "fasttext")) {
    embeddings <- load_embedding_matrix(
      embedding_path = config$embedding$embedding_path,
      embedding_dim = config$embedding$embedding_dim %||% 300L
    )
    return(list(strategy = strategy, embeddings = embeddings, numeric_stats = numeric_stats))
  }

  if (strategy == "hybrid") {
    tfidf <- fit_tfidf_vectorizer(
      text_clean,
      max_features = settings$max_features,
      min_df = config$embedding$min_df %||% 2L,
      max_doc_tokens = settings$max_doc_tokens,
      use_bigrams = isTRUE(config$embedding$use_bigrams)
    )
    embeddings <- load_embedding_matrix(
      embedding_path = config$embedding$embedding_path,
      embedding_dim = config$embedding$embedding_dim %||% 300L
    )
    return(list(
      strategy = strategy,
      tfidf = tfidf,
      embeddings = embeddings,
      numeric_stats = numeric_stats,
      hybrid_weight = config$embedding$hybrid_weight %||% 0.5
    ))
  }

  stop("Unsupported embedding strategy: ", strategy)
}

transform_features <- function(frame, pipeline) {
  clean_docs <- vapply(frame$model_text, clean_text, character(1L))
  numeric_matrix <- transform_numeric_scaler(frame[, ..NUMERIC_COLUMNS], pipeline$numeric_stats)

  if (pipeline$strategy == "tfidf") {
    text_matrix <- transform_tfidf(clean_docs, pipeline$tfidf)
    return(cbind(text_matrix, numeric_matrix))
  }

  if (pipeline$strategy %in% c("word2vec", "glove", "fasttext")) {
    embed_matrix <- transform_avg_embeddings(clean_docs, pipeline$embeddings)
    return(cbind(embed_matrix, numeric_matrix))
  }

  if (pipeline$strategy == "hybrid") {
    tfidf_matrix <- transform_tfidf(clean_docs, pipeline$tfidf)
    embed_matrix <- transform_avg_embeddings(clean_docs, pipeline$embeddings)
    if (!is.null(pipeline$hybrid_weight)) {
      tfidf_matrix <- tfidf_matrix * pipeline$hybrid_weight
      embed_matrix <- embed_matrix * (1 - pipeline$hybrid_weight)
    }
    return(cbind(tfidf_matrix, embed_matrix, numeric_matrix))
  }

  stop("Unsupported strategy in transform_features: ", pipeline$strategy)
}

fit_tfidf_vectorizer <- function(text_clean, max_features, min_df, max_doc_tokens, use_bigrams) {
  doc_tokens <- lapply(text_clean, tokenize_ngrams, max_doc_tokens = max_doc_tokens, use_bigrams = use_bigrams)
  vocab <- build_vocabulary(doc_tokens, max_features = max_features, min_df = min_df)
  text_matrix <- build_sparse_matrix(doc_tokens, vocab$terms)
  idf <- compute_idf(text_matrix)
  list(vocabulary = vocab$terms, idf = idf, max_doc_tokens = max_doc_tokens, use_bigrams = use_bigrams)
}

transform_tfidf <- function(text_clean, tfidf) {
  doc_tokens <- lapply(
    text_clean,
    tokenize_ngrams,
    max_doc_tokens = tfidf$max_doc_tokens,
    use_bigrams = tfidf$use_bigrams
  )
  text_matrix <- build_sparse_matrix(doc_tokens, tfidf$vocabulary)
  apply_tfidf(text_matrix, tfidf$idf)
}

tokenize_ngrams <- function(text, max_doc_tokens = 1500L, use_bigrams = TRUE) {
  if (!nzchar(text)) {
    return(character())
  }
  tokens <- unlist(strsplit(text, " ", fixed = TRUE), use.names = FALSE)
  tokens <- tokens[nzchar(tokens)]
  if (length(tokens) > max_doc_tokens) {
    tokens <- tokens[seq_len(max_doc_tokens)]
  }
  if (!use_bigrams || length(tokens) <= 1L) {
    return(tokens)
  }
  bigrams <- paste(tokens[-length(tokens)], tokens[-1L], sep = "_")
  c(tokens, bigrams)
}

tokenize_words <- function(text) {
  if (!nzchar(text)) {
    return(character())
  }
  tokens <- unlist(strsplit(text, " ", fixed = TRUE), use.names = FALSE)
  tokens[nzchar(tokens)]
}

build_vocabulary <- function(doc_tokens, max_features = 10000L, min_df = 2L) {
  term_df <- new.env(hash = TRUE, parent = emptyenv())
  term_tf <- new.env(hash = TRUE, parent = emptyenv())

  for (tokens in doc_tokens) {
    if (length(tokens) == 0L) next
    unique_tokens <- unique(tokens)
    for (term in unique_tokens) {
      term_df[[term]] <- (term_df[[term]] %||% 0L) + 1L
    }
    token_counts <- table(tokens)
    for (term in names(token_counts)) {
      term_tf[[term]] <- (term_tf[[term]] %||% 0L) + unname(token_counts[[term]])
    }
  }

  terms <- ls(term_df, all.names = TRUE)
  df_values <- vapply(terms, function(term) term_df[[term]], integer(1L))
  tf_values <- vapply(terms, function(term) term_tf[[term]], numeric(1L))
  keep <- df_values >= min_df
  terms <- terms[keep]
  tf_values <- tf_values[keep]
  if (length(terms) == 0L) stop("No terms survived vocabulary filtering.")
  order_idx <- order(tf_values, decreasing = TRUE)
  terms <- terms[order_idx]
  if (length(terms) > max_features) terms <- terms[seq_len(max_features)]
  list(terms = terms)
}

build_sparse_matrix <- function(doc_tokens, vocabulary) {
  term_index <- setNames(seq_along(vocabulary), vocabulary)
  i_idx <- integer()
  j_idx <- integer()
  x_val <- numeric()

  for (row_id in seq_along(doc_tokens)) {
    tokens <- doc_tokens[[row_id]]
    if (length(tokens) == 0L) next
    counts <- table(tokens)
    matched <- term_index[names(counts)]
    keep <- !is.na(matched)
    if (!any(keep)) next
    i_idx <- c(i_idx, rep.int(row_id, sum(keep)))
    j_idx <- c(j_idx, as.integer(matched[keep]))
    x_val <- c(x_val, as.numeric(counts[keep]))
  }

  Matrix::sparseMatrix(i = i_idx, j = j_idx, x = x_val, dims = c(length(doc_tokens), length(vocabulary)))
}

compute_idf <- function(count_matrix) {
  doc_freq <- Matrix::colSums(count_matrix > 0)
  log((nrow(count_matrix) + 1) / (doc_freq + 1)) + 1
}

apply_tfidf <- function(count_matrix, idf) {
  weighted <- count_matrix %*% Matrix::Diagonal(x = idf)
  row_norms <- sqrt(Matrix::rowSums(weighted ^ 2))
  row_norms[row_norms == 0] <- 1
  weighted / row_norms
}

load_embedding_matrix <- function(embedding_path, embedding_dim = 300L, max_terms = 500000L) {
  if (is.null(embedding_path) || !file.exists(embedding_path)) {
    stop("Embedding strategy requires a valid embedding_path.")
  }

  con <- file(embedding_path, open = "r")
  on.exit(close(con), add = TRUE)

  words <- character()
  rows <- list()
  line_count <- 0L
  repeat {
    line <- readLines(con, n = 1L, warn = FALSE)
    if (length(line) == 0L) break
    line_count <- line_count + 1L
    parts <- strsplit(line, "[[:space:]]+")[[1L]]
    if (length(parts) < (embedding_dim + 1L)) next
    word <- parts[[1L]]
    vec <- suppressWarnings(as.numeric(parts[2:(embedding_dim + 1L)]))
    if (anyNA(vec)) next
    words <- c(words, word)
    rows[[length(rows) + 1L]] <- vec
    if (length(words) >= max_terms) break
  }

  matrix_values <- do.call(rbind, rows)
  rownames(matrix_values) <- words
  list(matrix = matrix_values, dim = embedding_dim)
}

transform_avg_embeddings <- function(text_clean, embeddings) {
  token_lists <- lapply(text_clean, tokenize_words)
  mat <- matrix(0, nrow = length(token_lists), ncol = embeddings$dim)
  colnames(mat) <- paste0("emb_", seq_len(embeddings$dim))

  for (i in seq_along(token_lists)) {
    tokens <- token_lists[[i]]
    if (length(tokens) == 0L) next
    matched <- tokens[tokens %in% rownames(embeddings$matrix)]
    if (length(matched) == 0L) next
    vecs <- embeddings$matrix[matched, , drop = FALSE]
    mat[i, ] <- colMeans(vecs)
  }

  Matrix::Matrix(mat, sparse = TRUE)
}

fit_numeric_scaler <- function(frame) {
  means <- vapply(frame, mean, numeric(1L), na.rm = TRUE)
  sds <- vapply(frame, sd, numeric(1L), na.rm = TRUE)
  sds[sds == 0 | is.na(sds)] <- 1
  list(means = means, sds = sds)
}

transform_numeric_scaler <- function(frame, stats) {
  scaled <- sweep(as.matrix(frame), 2L, stats$means, "-")
  scaled <- sweep(scaled, 2L, stats$sds, "/")
  Matrix::Matrix(scaled, sparse = TRUE)
}

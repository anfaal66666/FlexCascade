stratified_split <- function(labels, train_frac = 0.6, val_frac = 0.2, seed = 42L) {
  set.seed(seed)
  label_groups <- split(seq_along(labels), labels)

  train_idx <- integer()
  val_idx <- integer()
  test_idx <- integer()

  for (group in label_groups) {
    group <- sample(group)
    n <- length(group)
    n_train <- max(1L, floor(n * train_frac))
    n_val <- max(1L, floor(n * val_frac))
    if (n_train + n_val >= n) {
      n_val <- max(1L, n - n_train - 1L)
    }
    if (n_train + n_val >= n) {
      n_train <- max(1L, n - 2L)
    }

    train_idx <- c(train_idx, group[seq_len(n_train)])
    val_start <- n_train + 1L
    val_end <- min(n, n_train + n_val)
    if (val_start <= val_end) {
      val_idx <- c(val_idx, group[val_start:val_end])
    }
    if (val_end < n) {
      test_idx <- c(test_idx, group[(val_end + 1L):n])
    }
  }

  list(
    train = sort(unique(train_idx)),
    validation = sort(unique(val_idx)),
    test = sort(unique(test_idx))
  )
}
